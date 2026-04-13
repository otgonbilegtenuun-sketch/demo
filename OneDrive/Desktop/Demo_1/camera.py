"""
camera.py — OpenCV + MediaPipe Tasks API face processing.

MediaPipe 0.10+ uses the Tasks API with a downloaded .task model file.

Phone detection: tracks consecutive "looking-down" frames as a proxy for
phone use (realistic without needing a full object-detection model).
"""

import base64
import os
import threading
import time
from typing import Callable, Optional

import cv2
import mediapipe as mp
import numpy as np

# ── Tasks API aliases ─────────────────────────────────────────────────────────
_BaseOptions        = mp.tasks.BaseOptions
_FaceLandmarker     = mp.tasks.vision.FaceLandmarker
_FaceLandmarkerOpts = mp.tasks.vision.FaceLandmarkerOptions
_RunningMode        = mp.tasks.vision.RunningMode
_MpImage            = mp.Image
_ImageFormat        = mp.ImageFormat

MODEL_PATH      = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
FACE_NAME_TTL   = 6.0   # seconds a recognised name stays visible after last match


def _make_landmarker(num_faces: int = 8) -> _FaceLandmarker:
    opts = _FaceLandmarkerOpts(
        base_options=_BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=_RunningMode.IMAGE,
        num_faces=num_faces,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    return _FaceLandmarker.create_from_options(opts)


# ── Landmark analysis helpers ─────────────────────────────────────────────────

def _normalize_landmarks(landmarks) -> np.ndarray:
    """
    Position/scale-invariant 936-element float32 embedding
    (468 landmarks × x,y, centred and unit-scaled).
    """
    pts = np.array([[lm.x, lm.y] for lm in landmarks], dtype=np.float32)
    center = pts.mean(axis=0)
    pts -= center
    scale = np.sqrt((pts ** 2).sum(axis=1)).max()
    if scale > 0:
        pts /= scale
    return pts.flatten()


def _is_looking_sideways(landmarks) -> bool:
    """True when horizontal head rotation exceeds ~16°."""
    nose  = landmarks[1]
    l_eye = landmarks[33]
    r_eye = landmarks[263]
    face_w = abs(r_eye.x - l_eye.x)
    if face_w < 0.01:
        return False
    eye_mid = (l_eye.x + r_eye.x) / 2.0
    return abs(nose.x - eye_mid) / face_w > 0.27


def _is_attentive(landmarks) -> bool:
    """True when face is roughly forward-facing (looking at camera)."""
    nose  = landmarks[1]
    l_eye = landmarks[33]
    r_eye = landmarks[263]
    face_w = abs(r_eye.x - l_eye.x)
    if face_w < 0.01:
        return False
    eye_mid = (l_eye.x + r_eye.x) / 2.0
    return abs(nose.x - eye_mid) / face_w < 0.18


def _is_looking_down(landmarks) -> bool:
    """
    True when head is tilted notably downward.
    Heuristic: when looking down the upper face (forehead→nose) occupies
    more vertical space than the lower face (nose→chin).
    This is a reliable proxy for phone-in-lap use.
    """
    forehead = landmarks[10]   # mid-forehead
    nose     = landmarks[1]    # nose tip
    chin     = landmarks[152]  # chin bottom

    upper_h = abs(nose.y - forehead.y)
    lower_h = abs(chin.y  - nose.y)
    if lower_h < 0.001:
        return False
    return (upper_h / lower_h) > 1.55


# ── Camera processor ──────────────────────────────────────────────────────────

class CameraProcessor:
    def __init__(self):
        self._cap:    Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._lock    = threading.Lock()
        self._running = False
        self._frame:  Optional[np.ndarray] = None

        self._exam_mode  = False

        # Per-face name cache: face_idx → {"name": str|None, "ts": float}
        self._face_name_map: dict = {}

        # Consecutive down-gaze counter for phone-use detection
        self._down_streak = 0
        # Cooldown: don't re-alert within 8 seconds
        self._last_phone_alert = 0.0

        self._face_info: list = []

        # Callbacks set by app.py
        # on_recognition(face_idx, embedding, attentive, sideways) → bool (True = matched)
        self.on_recognition:   Optional[Callable] = None
        # on_phone_suspect(student_name) → called when down-gaze threshold hit
        self.on_phone_suspect:  Optional[Callable] = None
        # on_unknown_face(face_idx) → called in exam mode when face not recognised
        self.on_unknown_face:   Optional[Callable] = None

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
            self._down_streak = 0
            with self._lock:
                self._face_name_map.clear()

    @property
    def recognized_faces(self) -> list:
        with self._lock:
            return list(self._face_info)

    def set_face_name(self, face_idx: int, name: Optional[str]):
        """Record the recognised name for a specific face slot."""
        with self._lock:
            self._face_name_map[face_idx] = {"name": name, "ts": time.time()}

    def _get_face_name(self, face_idx: int) -> str:
        """Return the sticky name for a face slot, or 'Unknown' if expired."""
        with self._lock:
            entry = self._face_name_map.get(face_idx)
        if entry and (time.time() - entry["ts"]) < FACE_NAME_TTL:
            return entry["name"] or "Unknown"
        return "Unknown"

    def _prune_face_names(self, num_faces: int):
        """Drop stale entries for face slots that are no longer visible."""
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
        self._cap     = cap
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running    = False
        self._down_streak = 0
        time.sleep(0.15)
        if self._cap:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._frame = None

    # ── Processing loop ───────────────────────────────────────────────────────

    def _loop(self):
        landmarker     = _make_landmarker(num_faces=8)
        last_recog     = 0.0
        recog_interval = 2.0  # seconds between DB updates

        try:
            while self._running:
                ret, frame = self._cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

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
                if (now - last_recog) >= recog_interval and faces:
                    try:
                        self._handle_recognition(faces, now)
                    except Exception as e:
                        print(f"[camera] _handle_recognition error: {e}")
                    last_recog = now

                time.sleep(0.033)
        except Exception as e:
            print(f"[camera] loop fatal error: {e}")
        finally:
            landmarker.close()

    def _handle_recognition(self, faces: list, now: float):
        """Run recognition callbacks and phone-down-gaze logic."""
        for idx, f in enumerate(faces):
            # Recognition callback — returns True if a known student matched
            matched = False
            if self.on_recognition:
                try:
                    matched = bool(self.on_recognition(idx, f["embedding"], f["attentive"], f["sideways"]))
                except Exception as e:
                    print(f"[camera] on_recognition error: {e}")

            # Exam mode: alert on unknown face
            if self._exam_mode and not matched and self.on_unknown_face:
                try:
                    self.on_unknown_face(idx)
                except Exception as e:
                    print(f"[camera] on_unknown_face error: {e}")

            # Phone detection: track consecutive down-gaze frames
            if self._exam_mode and f.get("looking_down"):
                self._down_streak += 1
                if (self._down_streak >= 2
                        and self.on_phone_suspect
                        and (now - self._last_phone_alert) > 8.0):
                    name = self._get_face_name(idx)
                    self.on_phone_suspect(name)
                    self._last_phone_alert = now
                    self._down_streak      = 0
            else:
                self._down_streak = max(0, self._down_streak - 1)

    def _process_frame(self, frame: np.ndarray, landmarker) -> tuple:
        h, w   = frame.shape[:2]
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = _MpImage(image_format=_ImageFormat.SRGB, data=rgb)
        result = landmarker.detect(mp_img)

        faces = []
        for face_idx, face_lms in enumerate(result.face_landmarks or []):
            lms          = face_lms
            attentive    = _is_attentive(lms)
            sideways     = _is_looking_sideways(lms)
            looking_down = _is_looking_down(lms)
            embedding    = _normalize_landmarks(lms)

            xs = [lm.x * w for lm in lms]
            ys = [lm.y * h for lm in lms]
            x1 = max(0, int(min(xs)) - 10)
            y1 = max(0, int(min(ys)) - 10)
            x2 = min(w, int(max(xs)) + 10)
            y2 = min(h, int(max(ys)) + 10)

            name = self._get_face_name(face_idx)
            is_unknown = (name == "Unknown")

            # Box colour based on current state
            if self._exam_mode and is_unknown:
                color  = (128, 0, 200)   # purple = unknown/intruder
                status = "ZORCHIGCH"
            elif self._exam_mode and looking_down:
                color  = (0, 140, 255)   # orange = down/phone
                status = "Down gaze"
            elif self._exam_mode and sideways:
                color  = (0, 0, 220)     # red = suspicious
                status = "SUSPICIOUS"
            elif attentive:
                color  = (0, 185, 80)    # green = attentive
                status = "Attentive"
            else:
                color  = (60, 60, 200)   # blue = distracted
                status = "Distracted"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, name,   (x1, y1 - 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
            cv2.putText(frame, status, (x1, y1 - 7),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)

            faces.append({
                "face_idx":     face_idx,
                "embedding":    embedding,
                "attentive":    attentive,
                "sideways":     sideways,
                "looking_down": looking_down,
                "name":         name,
                "bbox":         (x1, y1, x2, y2),
            })

        self._prune_face_names(len(faces))

        # HUD overlays
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
        """Sync generator — runs in starlette thread pool."""
        while True:
            frame = self.get_frame()
            if frame is None:
                ph = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.rectangle(ph, (0, 0), (640, 480), (240, 242, 247), -1)
                cv2.putText(ph, "EduGuard AI", (195, 210),
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


# ── Enrollment helper ─────────────────────────────────────────────────────────

def process_enrollment_image(image_b64: str) -> Optional[np.ndarray]:
    """Decode a base64 JPEG, detect one face, return normalised embedding."""
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        img_bytes = base64.b64decode(image_b64)
        arr   = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None

        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = _MpImage(image_format=_ImageFormat.SRGB, data=rgb)

        with _make_landmarker(num_faces=1) as lm:
            result = lm.detect(mp_img)

        if not result.face_landmarks:
            return None
        return _normalize_landmarks(result.face_landmarks[0])

    except Exception as e:
        print(f"[camera] enroll image error: {e}")
        return None
