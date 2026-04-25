"""
camera.py — OpenCV + MediaPipe (gaze) + InsightFace (recognition) + YOLOv8 (phone)

Architecture:
  MediaPipe Face Landmarker  : face detection every frame, gaze analysis (attentive / sideways)
  InsightFace buffalo_sc     : 512-dim face embedding for recognition (every 2 s)
  YOLOv8 nano                : phone / object detection (every ~15 frames, exam mode only)
"""

import base64
import os
import threading
import time
from typing import Callable, Optional

import cv2
import mediapipe as mp
import numpy as np

# ── MediaPipe aliases ─────────────────────────────────────────────────────────
_BaseOptions        = mp.tasks.BaseOptions
_FaceLandmarker     = mp.tasks.vision.FaceLandmarker
_FaceLandmarkerOpts = mp.tasks.vision.FaceLandmarkerOptions
_RunningMode        = mp.tasks.vision.RunningMode
_MpImage            = mp.Image
_ImageFormat        = mp.ImageFormat

MODEL_PATH    = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
FACE_NAME_TTL = 6.0   # seconds a recognised name stays visible after last match


def _make_landmarker(num_faces: int = 30) -> _FaceLandmarker:
    opts = _FaceLandmarkerOpts(
        base_options=_BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=_RunningMode.IMAGE,
        num_faces=num_faces,
        min_face_detection_confidence=0.3,
        min_face_presence_confidence=0.3,
        min_tracking_confidence=0.3,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    return _FaceLandmarker.create_from_options(opts)


# ── Lazy model loaders ────────────────────────────────────────────────────────

_deepface_ready = False
_deepface_lock  = threading.Lock()


def _warm_deepface():
    """Pre-load the ArcFace model so the first recognition call is fast."""
    global _deepface_ready
    if not _deepface_ready:
        with _deepface_lock:
            if not _deepface_ready:
                from deepface import DeepFace
                DeepFace.build_model("ArcFace")
                _deepface_ready = True
                print("[DeepFace] ArcFace loaded")


_yolo_model = None
_yolo_lock  = threading.Lock()


def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        with _yolo_lock:
            if _yolo_model is None:
                from ultralytics import YOLO
                _yolo_model = YOLO("yolov8n.pt")
                print("[YOLO] yolov8n loaded")
    return _yolo_model


# ── Landmark gaze helpers (MediaPipe) ─────────────────────────────────────────

def _is_looking_sideways(landmarks) -> bool:
    """True when horizontal head rotation exceeds ~16°."""
    nose  = landmarks[1]
    l_eye = landmarks[33]
    r_eye = landmarks[263]
    face_w = abs(r_eye.x - l_eye.x)
    if face_w < 0.01:
        return False
    eye_mid = (l_eye.x + r_eye.x) / 2.0
    return bool(abs(nose.x - eye_mid) / face_w > 0.27)


def _is_attentive(landmarks) -> bool:
    """True when face is roughly forward-facing."""
    nose  = landmarks[1]
    l_eye = landmarks[33]
    r_eye = landmarks[263]
    face_w = abs(r_eye.x - l_eye.x)
    if face_w < 0.01:
        return False
    eye_mid = (l_eye.x + r_eye.x) / 2.0
    return bool(abs(nose.x - eye_mid) / face_w < 0.18)


def _detect_uniform(frame: np.ndarray, x1: int, x2: int, y2: int,
                    h: int, w: int) -> Optional[bool]:
    """Detect white uniform by analysing the clothing region below the face box."""
    cloth_y1 = y2 + 5
    cloth_y2 = min(h, y2 + 130)
    cloth_x1 = max(0, x1 - 10)
    cloth_x2 = min(w, x2 + 10)
    if (cloth_y2 - cloth_y1) < 20 or (cloth_x2 - cloth_x1) < 20:
        return None
    region = frame[cloth_y1:cloth_y2, cloth_x1:cloth_x2]
    if region.size == 0:
        return None
    hsv        = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(hsv, np.array([0, 0, 160]), np.array([180, 50, 255]))
    return bool(np.count_nonzero(white_mask) / white_mask.size >= 0.30)


# ── Camera processor ──────────────────────────────────────────────────────────

class CameraProcessor:
    def __init__(self):
        self._cap:    Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._lock    = threading.Lock()
        self._running = False
        self._frame:  Optional[np.ndarray] = None

        self._exam_mode  = False
        self._frame_count = 0

        # Sticky name cache: face_idx → {name, ts}
        self._face_name_map: dict = {}

        # YOLO phone detection: set of face indices where a phone was found
        self._phone_face_indices: set = set()
        self._last_phone_alert: float = 0.0
        _YOLO_INTERVAL = 15          # run YOLO once every N frames
        self._YOLO_INTERVAL = _YOLO_INTERVAL

        # YOLO person tracking
        self._tracked_persons: dict = {}    # track_id → (x1,y1,x2,y2)
        self._locked_id: Optional[int] = None
        self._PERSON_TRACK_INTERVAL = 20    # run tracking every N frames
        self._frame_wh: tuple = (640, 480)  # (w,h) of last processed frame

        self._face_info: list = []

        # Callbacks set by app.py
        # on_recognition(face_data_list) → set of matched face_idx
        #   face_data_list: [(face_idx, embedding, attentive, sideways), ...]
        self.on_recognition:  Optional[Callable] = None
        self.on_phone_suspect: Optional[Callable] = None
        self.on_unknown_face:  Optional[Callable] = None
        self.on_uniform:       Optional[Callable] = None

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def exam_mode(self) -> bool:
        return self._exam_mode

    @exam_mode.setter
    def exam_mode(self, value: bool):
        self._exam_mode = value
        if not value:
            self._phone_face_indices.clear()
            with self._lock:
                self._face_name_map.clear()

    @property
    def recognized_faces(self) -> list:
        with self._lock:
            return list(self._face_info)

    def set_face_name(self, face_idx: int, name: Optional[str]):
        with self._lock:
            self._face_name_map[face_idx] = {"name": name, "ts": time.time()}

    def _get_face_name(self, face_idx: int) -> str:
        with self._lock:
            entry = self._face_name_map.get(face_idx)
        if entry and (time.time() - entry["ts"]) < FACE_NAME_TTL:
            return entry["name"] or "Unknown"
        return "Unknown"

    def _prune_face_names(self, num_faces: int):
        now = time.time()
        with self._lock:
            stale = [
                k for k, v in self._face_name_map.items()
                if k >= num_faces and (now - v["ts"]) > FACE_NAME_TTL
            ]
            for k in stale:
                del self._face_name_map[k]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)
        self._cap     = cap
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def start_from_file(self, path: str) -> bool:
        """Start processing frames from a video file instead of a live camera."""
        if self._running:
            self.stop()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return False
        self._cap     = cap
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop_file, args=(path,), daemon=True
        )
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        self._phone_face_indices.clear()
        time.sleep(0.15)
        if self._cap:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._frame = None

    # ── Main loops ────────────────────────────────────────────────────────────

    def _loop(self):
        landmarker     = _make_landmarker(num_faces=8)
        last_recog     = 0.0
        recog_interval = 5.0

        try:
            while self._running:
                ret, frame = self._cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                self._frame_count += 1

                t_iter = time.time()

                # Person tracking (every N frames, only when useful)
                if (self._frame_count % self._PERSON_TRACK_INTERVAL == 0
                        and (self._exam_mode or self._locked_id is not None)):
                    try:
                        self._update_person_tracking(frame)
                    except Exception as e:
                        print(f"[camera] person track error: {e}")

                try:
                    annotated, faces = self._process_frame(frame.copy(), landmarker)
                except Exception as e:
                    print(f"[camera] _process_frame error: {e}")
                    time.sleep(0.05)
                    continue

                with self._lock:
                    self._frame     = annotated
                    self._face_info = faces

                now = time.time()

                # YOLO phone detection (exam mode, throttled)
                if (self._exam_mode
                        and self._frame_count % self._YOLO_INTERVAL == 0
                        and faces):
                    try:
                        self._update_phone_detection(frame, faces)
                        self._check_phone_alerts(now)
                    except Exception as e:
                        print(f"[camera] YOLO phone error: {e}")

                # InsightFace recognition
                if (now - last_recog) >= recog_interval and faces:
                    try:
                        self._handle_recognition(frame, faces, now)
                    except Exception as e:
                        print(f"[camera] recognition error: {e}")
                    last_recog = now

                elapsed = time.time() - t_iter
                time.sleep(max(0.0, 0.066 - elapsed))
        except Exception as e:
            print(f"[camera] loop fatal error: {e}")
        finally:
            landmarker.close()

    def _loop_file(self, path: str):
        """Process every frame of a video file, then stop automatically."""
        landmarker     = _make_landmarker(num_faces=8)
        last_recog     = 0.0
        recog_interval = 5.0
        fps            = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_delay    = 1.0 / fps

        try:
            while self._running:
                t_iter = time.time()   # track iteration start for accurate pacing

                ret, frame = self._cap.read()
                if not ret:
                    break   # end of file

                self._frame_count += 1

                # Person tracking (every N frames, only when useful)
                if (self._frame_count % self._PERSON_TRACK_INTERVAL == 0
                        and (self._exam_mode or self._locked_id is not None)):
                    try:
                        self._update_person_tracking(frame)
                    except Exception as e:
                        print(f"[camera] person track error: {e}")

                try:
                    annotated, faces = self._process_frame(frame.copy(), landmarker)
                except Exception as e:
                    print(f"[camera] _process_frame error: {e}")
                    time.sleep(0.05)
                    continue

                with self._lock:
                    self._frame     = annotated
                    self._face_info = faces

                now = time.time()

                if (self._exam_mode
                        and self._frame_count % self._YOLO_INTERVAL == 0
                        and faces):
                    try:
                        self._update_phone_detection(frame, faces)
                        self._check_phone_alerts(now)
                    except Exception as e:
                        print(f"[camera] YOLO phone error: {e}")

                if (now - last_recog) >= recog_interval and faces:
                    try:
                        self._handle_recognition(frame, faces, now)
                    except Exception as e:
                        print(f"[camera] recognition error: {e}")
                    last_recog = now

                # Sleep only the remaining time to maintain 1x playback speed
                elapsed = time.time() - t_iter
                time.sleep(max(0.0, frame_delay - elapsed))
        except Exception as e:
            print(f"[camera] file loop error: {e}")
        finally:
            landmarker.close()
            self._running = False
            print("[camera] Video file processing complete")

    # ── YOLOv8 phone detection ────────────────────────────────────────────────

    def _update_phone_detection(self, frame: np.ndarray, faces: list):
        """Run YOLOv8 to find cell phones and map each phone to the nearest face."""
        yolo    = _get_yolo()
        results = yolo(frame, classes=[67], verbose=False, conf=0.4)  # 67 = cell phone

        phone_boxes = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                phone_boxes.append((x1, y1, x2, y2))

        new_phone_faces: set = set()
        for px1, py1, px2, py2 in phone_boxes:
            pcx, pcy    = (px1 + px2) // 2, (py1 + py2) // 2
            best_idx    = None
            best_dist   = float("inf")
            for idx, f in enumerate(faces):
                fx1, fy1, fx2, fy2 = f["bbox"]
                fcx, fcy = (fx1 + fx2) // 2, (fy1 + fy2) // 2
                dist = ((pcx - fcx) ** 2 + (pcy - fcy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_idx  = idx
            if best_idx is not None:
                new_phone_faces.add(best_idx)

        self._phone_face_indices = new_phone_faces

    def _check_phone_alerts(self, now: float):
        """Fire on_phone_suspect for each face where a phone was detected."""
        if not self._phone_face_indices:
            return
        if (now - self._last_phone_alert) <= 8.0:
            return
        for idx in self._phone_face_indices:
            name = self._get_face_name(idx)
            if self.on_phone_suspect:
                self.on_phone_suspect(name)
        self._last_phone_alert = now

    # ── YOLOv8 person tracking ────────────────────────────────────────────────

    def _update_person_tracking(self, frame: np.ndarray):
        """Run YOLOv8 tracking on class 0 (person) for full-body bounding boxes."""
        yolo = _get_yolo()
        try:
            results = yolo.track(frame, persist=True, classes=[0],
                                 verbose=False, conf=0.35)
            new_tracked: dict = {}
            if results and results[0].boxes is not None:
                for box in results[0].boxes:
                    if box.id is None:
                        continue
                    tid = int(box.id[0])
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    new_tracked[tid] = (x1, y1, x2, y2)
            self._tracked_persons = new_tracked
            # If locked person disappeared, release lock
            if self._locked_id is not None and self._locked_id not in new_tracked:
                self._locked_id = None
        except Exception as e:
            print(f"[camera] person tracking error: {e}")

    def lock_at_point(self, nx: float, ny: float) -> Optional[int]:
        """
        Find the tracked person whose bbox contains normalised point (nx,ny)
        and lock onto that person. Returns track_id or None.
        """
        w, h = self._frame_wh
        px, py = int(nx * w), int(ny * h)
        best_id   = None
        best_area = float("inf")
        for tid, (x1, y1, x2, y2) in self._tracked_persons.items():
            if x1 <= px <= x2 and y1 <= py <= y2:
                area = (x2 - x1) * (y2 - y1)
                if area < best_area:
                    best_area = area
                    best_id   = tid
        self._locked_id = best_id
        return best_id

    def unlock(self):
        """Release any active person lock."""
        self._locked_id = None

    # ── DeepFace recognition ─────────────────────────────────────────────────

    def _handle_recognition(self, frame: np.ndarray, faces: list, now: float):
        """
        Crop each MediaPipe-detected face, run ArcFace on the crop.
        This avoids the whole-frame fallback bug where DeepFace returns a
        garbage embedding when the full-frame detector misses the face.
        """
        if not self.on_recognition or not faces:
            return

        h, w = frame.shape[:2]
        face_data: list = []

        try:
            from deepface import DeepFace
            for face_idx, mp_face in enumerate(faces):
                x1, y1, x2, y2 = mp_face["bbox"]

                # Add 25 % padding around the MediaPipe bbox for better alignment
                fw, fh  = max(x2 - x1, 1), max(y2 - y1, 1)
                pad_x   = int(fw * 0.25)
                pad_y   = int(fh * 0.25)
                cx1 = max(0, x1 - pad_x)
                cy1 = max(0, y1 - pad_y)
                cx2 = min(w, x2 + pad_x)
                cy2 = min(h, y2 + pad_y)

                # Skip crops that are too small to embed reliably
                if (cx2 - cx1) < 40 or (cy2 - cy1) < 40:
                    continue

                crop = frame[cy1:cy2, cx1:cx2]

                try:
                    res = DeepFace.represent(
                        img_path=crop,
                        model_name="ArcFace",
                        enforce_detection=False,
                        detector_backend="opencv",
                        align=True,
                    )
                    if not res:
                        continue

                    # Use the result whose facial area is largest
                    # (avoid the whole-crop fallback by checking area ratio)
                    best = max(res, key=lambda r: r.get("facial_area", {}).get("w", 0)
                                                  * r.get("facial_area", {}).get("h", 0))
                    area = best.get("facial_area", {})
                    rw, rh = area.get("w", 0), area.get("h", 0)
                    crop_h, crop_w = crop.shape[:2]

                    # If detected region covers >85 % of the crop it's likely the
                    # whole-image fallback — skip to avoid garbage embeddings
                    if rw * rh > crop_w * crop_h * 0.85:
                        continue

                    emb = np.array(best["embedding"], dtype=np.float32)
                    face_data.append((face_idx, emb,
                                      mp_face["attentive"], mp_face["sideways"]))

                except Exception as e:
                    pass   # single face failed — keep going

        except Exception as e:
            print(f"[camera] recognition error: {e}")
            return

        matched_indices = self.on_recognition(face_data) or set() if face_data else set()

        # Per-face uniform callbacks
        for idx, f in enumerate(faces):
            if idx in matched_indices and self.on_uniform and f.get("uniform_on") is not None:
                try:
                    name = self._get_face_name(idx)
                    if name != "Unknown":
                        self.on_uniform(idx, name, f["uniform_on"])
                except Exception as e:
                    print(f"[camera] on_uniform error: {e}")

            # Unknown faces are shown with green box — no separate alert needed

    # ── Frame processing (MediaPipe display layer) ────────────────────────────

    def _process_frame(self, frame: np.ndarray, landmarker) -> tuple:
        h, w = frame.shape[:2]
        self._frame_wh = (w, h)   # used by lock_at_point
        rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Scale up for better detection of small/distant faces.
        # Landmarks are returned in [0,1] normalised coords so bounding boxes
        # map back to original dimensions automatically via lm.x*w, lm.y*h.
        SCALE = 1.0
        detect_rgb = cv2.resize(rgb, (int(w * SCALE), int(h * SCALE)))
        mp_img = _MpImage(image_format=_ImageFormat.SRGB, data=detect_rgb)
        result = landmarker.detect(mp_img)

        pulse_on = (self._frame_count % 30) < 15

        faces = []
        for face_idx, face_lms in enumerate(result.face_landmarks or []):
            lms       = face_lms
            attentive = _is_attentive(lms)
            sideways  = _is_looking_sideways(lms)

            xs = [lm.x * w for lm in lms]
            ys = [lm.y * h for lm in lms]
            x1 = max(0, int(min(xs)) - 10)
            y1 = max(0, int(min(ys)) - 10)
            x2 = min(w, int(max(xs)) + 10)
            y2 = min(h, int(max(ys)) + 10)

            uniform_on     = _detect_uniform(frame, x1, x2, y2, h, w)
            name           = self._get_face_name(face_idx)
            is_unknown     = name == "Unknown"
            phone_detected = self._exam_mode and (face_idx in self._phone_face_indices)

            # ── Box colour & status ─────────────────────────────────────────
            if phone_detected:
                color  = (0, 0, 220)
                status = "Phone Detected"
            elif self._exam_mode and sideways:
                color  = (0, 0, 220)
                status = "SUSPICIOUS"
            else:
                # All detected faces — known or unknown — get green/blue
                color  = (0, 185, 80) if attentive else (60, 60, 200)
                status = "Attentive"  if attentive else "Distracted"

            thickness = 3 if phone_detected else 2
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            cv2.putText(frame, name,   (x1, y1 - 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
            cv2.putText(frame, status, (x1, y1 - 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)

            # ── Phone indicator (pulsing red) ───────────────────────────────
            if phone_detected:
                RED     = (0, 0, 220)
                face_cx = (x1 + x2) // 2
                face_w  = x2 - x1
                ph_w    = max(40, face_w // 3)
                ph_h    = int(ph_w * 1.9)
                ph_x1   = face_cx - ph_w // 2
                ph_y1   = min(h - ph_h - 10, y2 + 18)
                ph_x2   = ph_x1 + ph_w
                ph_y2   = ph_y1 + ph_h

                alpha = 0.40 if pulse_on else 0.15
                ov    = frame.copy()
                cv2.rectangle(ov, (ph_x1, ph_y1), (ph_x2, ph_y2), RED, -1)
                cv2.addWeighted(ov, alpha, frame, 1 - alpha, 0, frame)

                border = 3 if pulse_on else 1
                cv2.rectangle(frame, (ph_x1, ph_y1), (ph_x2, ph_y2), RED, border)

                sp_y = ph_y1 + 6
                cv2.rectangle(frame,
                              (ph_x1 + 6, sp_y), (ph_x2 - 6, sp_y + 4), RED, -1)
                cv2.circle(frame, ((ph_x1+ph_x2)//2, ph_y2 - 10), 5, RED, 2)

                cv2.putText(frame, "! UTAAS", (max(0, ph_x1 - 4), ph_y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, RED, 2)

                blen = 18
                bthk = 3 if pulse_on else 1
                for cx, cy, dx, dy in [
                    (x1, y1,  1,  1), (x2, y1, -1,  1),
                    (x1, y2,  1, -1), (x2, y2, -1, -1),
                ]:
                    cv2.line(frame, (cx, cy), (cx + dx*blen, cy), RED, bthk)
                    cv2.line(frame, (cx, cy), (cx, cy + dy*blen), RED, bthk)

            # ── Uniform pill ────────────────────────────────────────────────
            if uniform_on is not None and not phone_detected:
                u_color = (0, 185, 80) if uniform_on else (0, 0, 220)
                u_text  = "UNIFORM" if uniform_on else "NO UNIFORM"
                (tw, _), _ = cv2.getTextSize(
                    u_text, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
                u_y = y2 + 18
                cv2.rectangle(frame, (x1, u_y - 13),
                              (x1 + tw + 8, u_y + 3), u_color, -1)
                cv2.putText(frame, u_text, (x1 + 4, u_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

            faces.append({
                "face_idx":    face_idx,
                "attentive":   attentive,
                "sideways":    sideways,
                "looking_down": phone_detected,  # reuse field for phone UI indicator
                "uniform_on":  uniform_on,
                "name":        name,
                "bbox":        (x1, y1, x2, y2),
            })

        self._prune_face_names(len(faces))

        # ── Person tracking overlay ──────────────────────────────────────────
        CYAN  = (255, 220, 0)   # BGR cyan-yellow for locked
        GRAY  = (160, 160, 160) # BGR gray for untracked
        L     = 22              # corner bracket length

        for tid, (px1, py1, px2, py2) in self._tracked_persons.items():
            is_locked = (tid == self._locked_id)

            # Resolve label: check if any recognised face bbox overlaps this person bbox
            person_label = "Unknown Student"
            for f in faces:
                fx1, fy1, fx2, fy2 = f["bbox"]
                if (fx1 < px2 and fx2 > px1 and fy1 < py2 and fy2 > py1):
                    fname = f.get("name", "Unknown")
                    if fname != "Unknown":
                        person_label = fname
                    break

            if is_locked:
                # Solid cyan rectangle
                cv2.rectangle(frame, (px1, py1), (px2, py2), CYAN, 2)
                # Corner brackets
                for cx, cy, dx, dy in [
                    (px1, py1,  1,  1), (px2, py1, -1,  1),
                    (px1, py2,  1, -1), (px2, py2, -1, -1),
                ]:
                    cv2.line(frame, (cx, cy), (cx + dx * L, cy),        CYAN, 3)
                    cv2.line(frame, (cx, cy), (cx,           cy + dy * L), CYAN, 3)
                # Label above the box
                label_txt = f"LOCKED: {person_label}"
                (lw, lh), _ = cv2.getTextSize(label_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                lx, ly = px1, max(py1 - 10, lh + 4)
                cv2.rectangle(frame, (lx - 2, ly - lh - 4), (lx + lw + 4, ly + 2), CYAN, -1)
                cv2.putText(frame, label_txt, (lx, ly),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
            else:
                # Thin gray box with track id
                cv2.rectangle(frame, (px1, py1), (px2, py2), GRAY, 1)
                cv2.putText(frame, f"#{tid}", (px1 + 4, py1 + 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, GRAY, 1)

        # HUD
        if self._exam_mode:
            ov = frame.copy()
            cv2.rectangle(ov, (0, 0), (215, 44), (0, 0, 170), -1)
            cv2.addWeighted(ov, 0.55, frame, 0.45, 0, frame)
            cv2.putText(frame, "EXAM MODE", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.82, (255, 255, 255), 2)

        cv2.putText(frame, f"Faces: {len(faces)}", (w - 115, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

        return frame, faces

    # ── Public stream / frame ─────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame

    def generate_mjpeg(self):
        while True:
            frame = self.get_frame()
            if frame is None:
                ph = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.rectangle(ph, (0, 0), (640, 480), (240, 242, 247), -1)
                cv2.putText(ph, "Mergen AI", (195, 210),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.1, (79, 70, 229), 2)
                cv2.putText(ph, "Камер эхлуулэх товчийг дарна уу", (115, 260),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 120, 140), 1)
                frame = ph
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buf.tobytes()
                + b"\r\n"
            )
            time.sleep(0.033)


# ── Enrollment helper (DeepFace ArcFace) ─────────────────────────────────────

def process_enrollment_image(image_b64: str) -> Optional[np.ndarray]:
    """
    Decode a base64 image, detect one face with DeepFace ArcFace,
    return a 512-dim embedding.
    """
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        img_bytes = base64.b64decode(image_b64)
        arr   = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None

        from deepface import DeepFace
        results = DeepFace.represent(
            img_path=frame,
            model_name="ArcFace",
            enforce_detection=True,
            detector_backend="opencv",
            align=True,
        )
        if not results:
            return None

        # Pick the largest detected face
        best = max(
            results,
            key=lambda r: r.get("facial_area", {}).get("w", 0)
                        * r.get("facial_area", {}).get("h", 0),
        )
        return np.array(best["embedding"], dtype=np.float32)

    except Exception as e:
        print(f"[camera] enroll image error: {e}")
        return None
