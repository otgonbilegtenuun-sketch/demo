"""
pose_analyzer.py — single-person MediaPipe Pose run on each tracked-person crop.

Why per-crop instead of whole-frame multi-pose:
  - MediaPipe's classic Pose solution is single-person but bundled with the pip
    package (no model file download needed).
  - Running it on a person bbox crop (~150x300 px) is ~5–10 ms on CPU.
  - We already have tracked-person bboxes from YOLO, so the cost is bounded.

Features extracted per person:
  raised_arm     — either wrist y above shoulder y by margin (strike indicator)
  lean_deg       — torso lean from vertical (positive=lean right, negative=lean left)
  reach_toward   — wrist x past the bbox edge toward another person (set by camera.py)
  visibility_ok  — required keypoints all visible enough to trust the reading
"""

import math
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

_MP_SOLUTIONS = getattr(mp, "solutions", None)
mp_pose = getattr(_MP_SOLUTIONS, "pose", None) if _MP_SOLUTIONS is not None else None
POSE_AVAILABLE = mp_pose is not None

# MediaPipe pose landmark indices we care about
_L_SHOULDER, _R_SHOULDER = 11, 12
_L_ELBOW,    _R_ELBOW    = 13, 14
_L_WRIST,    _R_WRIST    = 15, 16
_L_HIP,      _R_HIP      = 23, 24

_RAISED_MARGIN_NORM = 0.06   # wrist must be this much above shoulder (in 0–1 norm coords)
_VISIBILITY_MIN     = 0.4
_LEAN_DEG_FLAG      = 22.0   # |lean| > 22° = aggressive lean


class PoseAnalyzer:
    def __init__(self, model_complexity: int = 0):
        if mp_pose is None:
            raise RuntimeError(
                "MediaPipe pose is unavailable in this install. "
                "Install a MediaPipe build with mp.solutions.pose or add a "
                "PoseLandmarker .task model before enabling pose_signals."
            )
        # static_image_mode=True is correct here — we feed independent crops,
        # not a video stream of one person.
        self._pose = mp_pose.Pose(
            static_image_mode=True,
            model_complexity=model_complexity,
            enable_segmentation=False,
            smooth_landmarks=False,
            min_detection_confidence=0.4,
        )

    def close(self):
        try:
            self._pose.close()
        except Exception:
            pass

    def analyze_crop(self, crop_bgr: np.ndarray) -> Optional[dict]:
        """Run pose on a single person crop. Returns features dict or None."""
        if crop_bgr is None or crop_bgr.size == 0:
            return None
        h, w = crop_bgr.shape[:2]
        if h < 60 or w < 40:
            return None

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        try:
            res = self._pose.process(rgb)
        except Exception:
            return None
        if not res.pose_landmarks:
            return None
        lms = res.pose_landmarks.landmark

        # Visibility gate — if shoulders/hips aren't seen, results are unreliable
        need = [_L_SHOULDER, _R_SHOULDER, _L_HIP, _R_HIP]
        if any(lms[i].visibility < _VISIBILITY_MIN for i in need):
            return None

        # Shoulder midpoint
        sho_x = (lms[_L_SHOULDER].x + lms[_R_SHOULDER].x) / 2.0
        sho_y = (lms[_L_SHOULDER].y + lms[_R_SHOULDER].y) / 2.0
        hip_x = (lms[_L_HIP].x + lms[_R_HIP].x) / 2.0
        hip_y = (lms[_L_HIP].y + lms[_R_HIP].y) / 2.0

        # Lean angle from vertical (atan2 of horizontal vs vertical torso vector)
        dx = sho_x - hip_x
        dy = hip_y - sho_y    # positive when shoulders above hips (normal upright)
        lean_deg = math.degrees(math.atan2(dx, dy)) if dy > 1e-3 else 0.0

        # Raised arm — wrist y SMALLER than shoulder y (top of frame is y=0)
        l_w = lms[_L_WRIST]; r_w = lms[_R_WRIST]
        l_raised = (l_w.visibility >= _VISIBILITY_MIN
                    and l_w.y < sho_y - _RAISED_MARGIN_NORM)
        r_raised = (r_w.visibility >= _VISIBILITY_MIN
                    and r_w.y < sho_y - _RAISED_MARGIN_NORM)

        return {
            "raised_arm":      bool(l_raised or r_raised),
            "lean_deg":        round(lean_deg, 1),
            "aggressive_lean": abs(lean_deg) > _LEAN_DEG_FLAG,
            # Wrist positions in CROP-NORMALISED coords; camera.py maps back to frame coords
            "l_wrist_norm":    (l_w.x, l_w.y, l_w.visibility),
            "r_wrist_norm":    (r_w.x, r_w.y, r_w.visibility),
            "shoulder_y_norm": sho_y,
        }
