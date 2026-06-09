"""
appearance_tracker.py — Top-view person re-identification using appearance features.

For ceiling/top-corner cameras where face recognition is unreliable, this module
identifies students by their visual appearance: hair color, clothing color/pattern,
and body proportions. Uses only OpenCV — no extra model downloads needed.

Workflow:
  1. Teacher confirms seating at start of class → calibrate() captures appearance
     profiles for each seat/student pair.
  2. During class, identify() compares a new person crop against stored profiles
     and returns the best-match student with a confidence score.
  3. Profiles are per-day — students change clothes between days.

Feature vector (192 dims total):
  - Head region HSV histogram (48 bins) — captures hair color
  - Torso region HSV histogram (48 bins) — captures clothing color
  - Head color moments (9 values) — mean/std/skew per HSV channel
  - Torso color moments (9 values)
  - Spatial color grid (4x4 avg color = 48 values) — captures color layout
  - Body proportions (head/torso ratio, aspect ratio = 6 values)
  - Texture energy via Laplacian variance (2 values, head + torso)
  - Edge orientation histogram (22 bins) — captures pattern/stripe direction
"""

import threading
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from log_setup import get_logger

log = get_logger(__name__)

HSV_BINS = (8, 6, 6)          # H, S, V bins → 8*6 = 48 per region after flattening
GRID_SIZE = 4                  # 4x4 spatial grid
EDGE_HIST_BINS = 12            # orientation histogram bins
MIN_CROP_PX = 60               # reject crops smaller than this
MATCH_THRESHOLD = 0.55         # cosine similarity threshold for positive match
HIGH_CONFIDENCE = 0.72         # above this we're very confident


def _hsv_histogram(region: np.ndarray) -> np.ndarray:
    """Compute normalised HSV histogram for a BGR region."""
    if region.size == 0:
        return np.zeros(HSV_BINS[0] * HSV_BINS[1], dtype=np.float32)
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None,
                        [HSV_BINS[0], HSV_BINS[1]],
                        [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten().astype(np.float32)


def _color_moments(region: np.ndarray) -> np.ndarray:
    """Mean, std, skewness per channel (9 values total)."""
    if region.size == 0:
        return np.zeros(9, dtype=np.float32)
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV).astype(np.float64)
    moments = []
    for ch in range(3):
        channel = hsv[:, :, ch].flatten()
        mu = np.mean(channel)
        std = np.std(channel) + 1e-7
        skew = np.mean(((channel - mu) / std) ** 3)
        moments.extend([mu / 180.0 if ch == 0 else mu / 256.0,
                        std / 180.0 if ch == 0 else std / 256.0,
                        np.clip(skew, -3, 3) / 3.0])
    return np.array(moments, dtype=np.float32)


def _spatial_color_grid(region: np.ndarray, grid: int = GRID_SIZE) -> np.ndarray:
    """Divide region into grid x grid cells, compute average HSV per cell."""
    if region.size == 0:
        return np.zeros(grid * grid * 3, dtype=np.float32)
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, w = hsv.shape[:2]
    features = []
    for r in range(grid):
        for c in range(grid):
            y1, y2 = h * r // grid, h * (r + 1) // grid
            x1, x2 = w * c // grid, w * (c + 1) // grid
            cell = hsv[y1:y2, x1:x2]
            if cell.size == 0:
                features.extend([0, 0, 0])
            else:
                avg = np.mean(cell, axis=(0, 1))
                features.extend([avg[0] / 180.0, avg[1] / 256.0, avg[2] / 256.0])
    return np.array(features, dtype=np.float32)


def _texture_energy(region: np.ndarray) -> float:
    """Laplacian variance — higher = more texture/pattern."""
    if region.size == 0:
        return 0.0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(np.var(lap)) / 10000.0


def _edge_orientation_hist(region: np.ndarray, bins: int = EDGE_HIST_BINS) -> np.ndarray:
    """Histogram of gradient orientations — captures stripes/patterns."""
    if region.size == 0:
        return np.zeros(bins, dtype=np.float32)
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    angle = np.arctan2(gy, gx) * 180 / np.pi  # -180 to 180
    angle = (angle + 180) % 360  # 0 to 360
    hist, _ = np.histogram(angle, bins=bins, range=(0, 360), weights=mag)
    total = hist.sum()
    if total > 0:
        hist = hist / total
    return hist.astype(np.float32)


def extract_features(person_crop: np.ndarray) -> Optional[np.ndarray]:
    """Extract appearance feature vector from a YOLO person bounding box crop.
    Returns None if the crop is too small."""
    h, w = person_crop.shape[:2]
    if h < MIN_CROP_PX or w < MIN_CROP_PX // 2:
        return None

    # Split into head (top 30%) and torso (30-70%)
    head_end = int(h * 0.30)
    torso_end = int(h * 0.70)
    head = person_crop[:head_end, :]
    torso = person_crop[head_end:torso_end, :]

    features = []

    # Color histograms (48 + 48 = 96)
    features.append(_hsv_histogram(head))
    features.append(_hsv_histogram(torso))

    # Color moments (9 + 9 = 18)
    features.append(_color_moments(head))
    features.append(_color_moments(torso))

    # Spatial color grid on torso (48)
    features.append(_spatial_color_grid(torso))

    # Body proportions (6)
    head_h = max(head.shape[0], 1)
    torso_h = max(torso.shape[0], 1)
    props = np.array([
        head_h / h,
        torso_h / h,
        w / h,
        head.shape[1] / max(w, 1),
        head_h / max(torso_h, 1),
        w / max(h, 1),
    ], dtype=np.float32)
    features.append(props)

    # Texture energy (2)
    features.append(np.array([
        _texture_energy(head),
        _texture_energy(torso),
    ], dtype=np.float32))

    # Edge orientation (12 + 10 = 22 — but let's do 12 for torso only to keep it simple)
    features.append(_edge_orientation_hist(torso))

    vec = np.concatenate(features)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    dot = float(np.dot(a, b))
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


class AppearanceTracker:
    """Manages per-student appearance profiles for top-view re-identification."""

    def __init__(self):
        self._lock = threading.Lock()
        # student_id → list of feature vectors (averaged for matching)
        self._profiles: Dict[int, List[np.ndarray]] = {}
        # student_id → student_name (for logging)
        self._names: Dict[int, str] = {}
        self._calibration_date: str = ""
        self._enabled = True

    @property
    def is_calibrated(self) -> bool:
        with self._lock:
            return len(self._profiles) > 0

    @property
    def profile_count(self) -> int:
        with self._lock:
            return len(self._profiles)

    def calibrate_student(self, student_id: int, student_name: str,
                          person_crop: np.ndarray) -> bool:
        """Capture an appearance profile for a student from their current seat crop.
        Call multiple times to add more samples (improves robustness)."""
        feat = extract_features(person_crop)
        if feat is None:
            return False

        from datetime import date
        today = date.today().isoformat()

        with self._lock:
            if self._calibration_date != today:
                self._profiles.clear()
                self._names.clear()
                self._calibration_date = today

            if student_id not in self._profiles:
                self._profiles[student_id] = []
            self._profiles[student_id].append(feat)
            self._names[student_id] = student_name

        log.info(f"[Appearance] calibrated {student_name} "
                 f"({len(self._profiles[student_id])} samples)")
        return True

    def identify(self, person_crop: np.ndarray) -> Tuple[Optional[int], Optional[str], float]:
        """Match a person crop against all stored profiles.
        Returns (student_id, student_name, confidence) or (None, None, 0.0)."""
        feat = extract_features(person_crop)
        if feat is None:
            return None, None, 0.0

        with self._lock:
            if not self._profiles:
                return None, None, 0.0

            best_id = None
            best_sim = -1.0
            for sid, samples in self._profiles.items():
                avg = np.mean(samples, axis=0)
                avg_norm = np.linalg.norm(avg)
                if avg_norm > 0:
                    avg = avg / avg_norm
                sim = cosine_similarity(feat, avg)
                if sim > best_sim:
                    best_sim = sim
                    best_id = sid

            if best_id is not None and best_sim >= MATCH_THRESHOLD:
                return best_id, self._names.get(best_id, "Unknown"), round(best_sim, 3)

        return None, None, round(best_sim, 3) if best_sim > 0 else 0.0

    def identify_among(self, person_crop: np.ndarray,
                       candidate_ids: List[int]) -> Tuple[Optional[int], Optional[str], float]:
        """Match against a subset of students (e.g. those assigned to nearby seats)."""
        feat = extract_features(person_crop)
        if feat is None:
            return None, None, 0.0

        with self._lock:
            best_id = None
            best_sim = -1.0
            for sid in candidate_ids:
                samples = self._profiles.get(sid)
                if not samples:
                    continue
                avg = np.mean(samples, axis=0)
                avg_norm = np.linalg.norm(avg)
                if avg_norm > 0:
                    avg = avg / avg_norm
                sim = cosine_similarity(feat, avg)
                if sim > best_sim:
                    best_sim = sim
                    best_id = sid

            if best_id is not None and best_sim >= MATCH_THRESHOLD:
                return best_id, self._names.get(best_id, "Unknown"), round(best_sim, 3)

        return None, None, round(best_sim, 3) if best_sim > 0 else 0.0

    def get_profiles_summary(self) -> list:
        """Return summary for API consumers."""
        with self._lock:
            return [
                {
                    "student_id": sid,
                    "student_name": self._names.get(sid, "Unknown"),
                    "n_samples": len(samples),
                    "calibration_date": self._calibration_date,
                }
                for sid, samples in self._profiles.items()
            ]

    def clear(self):
        with self._lock:
            self._profiles.clear()
            self._names.clear()
            self._calibration_date = ""
