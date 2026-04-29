"""
bullying_detector.py — heuristic incident flagger.

This is NOT a true bullying detector. It uses spatial-temporal patterns from
the existing YOLO person tracker plus MediaPipe face blendshapes to flag
sustained, multi-signal events that warrant human review.

Designed as a drop-in surface so a proper action-recognition model
(SlowFast / X3D / VideoMAE trained on RWF-2000 + Bullying10K) can replace
the heuristics without changing the camera or DB integration.

Signals
  proximity_cluster : >=CLUSTER_K persons close to one target person
  close_pair        : exactly 2 persons very close, sustained
  sudden_motion     : large center-of-bbox jump in a short window (push/swing)
  distress_face     : sustained negative-affect blendshape score on a face

Aggregation
  A signal must persist for SUSTAIN_S to be considered. When fired, the score
  is boosted by any concurrent signal active for >=1.5s (multimodal fusion).
  An incident is only emitted if the fused score >= INCIDENT_THRESHOLD and
  the cooldown has elapsed.
"""

from collections import deque
from typing import Callable, Optional
from log_setup import get_logger
log = get_logger(__name__)


class BullyingDetector:

    SUSTAIN_S          = 4.0    # default; per-signal overrides via SUSTAIN_BY_TYPE
    PROX_RATIO         = 0.65   # center-distance / avg-bbox-width below this = "close"
    CLUSTER_K          = 3      # N or more close neighbours = surrounding
    MOTION_RATIO       = 0.50   # center jump / bbox width over MOTION_WINDOW_S
    MOTION_WINDOW_S    = 0.6
    DISTRESS_THRESHOLD = 0.45   # weighted blendshape sum
    INCIDENT_COOLDOWN  = 30.0
    INCIDENT_THRESHOLD = 0.55   # fused score required to fire on_incident
    CONCURRENT_S       = 1.0    # min duration for a signal to count as concurrent

    # Per-type minimum sustain (s). Pose actions are inherently brief so we
    # don't require 4 s — that would miss real strikes/grabs entirely.
    SUSTAIN_BY_TYPE = {
        "proximity_cluster": 4.0,
        "close_pair":        4.0,
        "sudden_motion":     0.5,
        "distress_face":     4.0,
        "raised_arm":        1.0,
        "aggressive_lean":   2.0,
        "wrist_reach":       0.4,   # strongest cue, fires almost instantly
    }

    def __init__(self):
        self._track_history: dict = {}        # tid -> deque[(t, cx, cy, w, h)]
        self._signal_started: dict = {}       # signal_key -> first_seen_time
        self._last_incident: float = 0.0
        self._enabled: bool = True
        self._seat_resolver: Optional[Callable] = None
        self._pose_resolver: Optional[Callable] = None
        self.on_incident: Optional[Callable] = None

    # ── Public API ───────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if not value:
            self._signal_started.clear()

    def update(self, tracked_persons: dict, faces: list, now: float,
               name_resolver: Optional[Callable] = None,
               seat_resolver: Optional[Callable] = None,
               pose_resolver: Optional[Callable] = None):
        """
        Called per-frame from the camera loop.
          tracked_persons : { track_id: (x1,y1,x2,y2) } from YOLO tracker
          faces           : list[face_dict] from MediaPipe (must include 'bbox',
                            optionally 'distress' float in [0,1])
          name_resolver   : optional fn(track_id) -> name; used to label events
          seat_resolver   : optional fn(track_id) -> seat_id or None; if both
                            tracks in a close pair are in seats, the pair is
                            suppressed (seated neighbors, not confrontation).
          pose_resolver   : optional fn(track_id) -> pose features dict or None;
                            unlocks raised_arm / aggressive_lean / wrist_reach
                            signals (the strongest physical-aggression cues).
        """
        self._seat_resolver = seat_resolver
        self._pose_resolver = pose_resolver
        if not self._enabled:
            return

        self._update_history(tracked_persons, now)

        signals = []
        signals += self._detect_proximity(tracked_persons)
        signals += self._detect_motion_spikes(now)
        signals += self._detect_distress(faces, tracked_persons)
        signals += self._detect_pose_actions(tracked_persons)

        active_keys = {s["key"] for s in signals}
        # Drop signals that stopped firing
        for key in list(self._signal_started.keys()):
            if key not in active_keys:
                del self._signal_started[key]
        # Start clock on new signals
        for s in signals:
            self._signal_started.setdefault(s["key"], now)

        if (now - self._last_incident) < self.INCIDENT_COOLDOWN:
            return

        # Fire on the first signal that's been sustained for its required
        # duration, fused with any other signals active for CONCURRENT_S+
        for s in signals:
            duration       = now - self._signal_started.get(s["key"], now)
            required       = self.SUSTAIN_BY_TYPE.get(s["type"], self.SUSTAIN_S)
            if duration < required:
                continue

            concurrent = [
                x for x in signals
                if x["key"] != s["key"]
                and (now - self._signal_started.get(x["key"], now)) >= self.CONCURRENT_S
            ]
            fused = min(1.0, s["score"] + 0.20 * len(concurrent))
            if fused < self.INCIDENT_THRESHOLD:
                continue

            tracks = s.get("tracks", [])
            names = []
            if name_resolver:
                for tid in tracks:
                    n = name_resolver(tid)
                    if n and n != "Unknown":
                        names.append(n)

            event = {
                "timestamp":          now,
                "primary_signal":     s["type"],
                "concurrent_signals": [x["type"] for x in concurrent],
                "involved_tracks":    tracks,
                "involved_names":     names,
                "score":              round(fused, 2),
                "duration_s":         round(duration, 1),
            }

            if self.on_incident:
                try:
                    self.on_incident(event)
                except Exception as e:
                    log.error(f"[bullying] on_incident error: {e}")

            self._last_incident = now
            self._signal_started.pop(s["key"], None)
            break

    # ── Internal: history bookkeeping ────────────────────────────────────────

    def _update_history(self, tracked: dict, now: float):
        for tid, (x1, y1, x2, y2) in tracked.items():
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            w,  h  = max(x2 - x1, 1), max(y2 - y1, 1)
            buf = self._track_history.setdefault(tid, deque(maxlen=60))
            buf.append((now, cx, cy, w, h))

        # Drop tracks not seen for >5 s
        for tid in list(self._track_history.keys()):
            buf = self._track_history[tid]
            if not buf or (now - buf[-1][0]) > 5.0:
                del self._track_history[tid]

    # ── Internal: detectors ──────────────────────────────────────────────────

    def _detect_proximity(self, tracked: dict) -> list:
        signals = []
        ids = list(tracked.keys())
        if len(ids) < 2:
            return signals

        # Precompute centers + widths
        meta = {}
        for tid in ids:
            x1, y1, x2, y2 = tracked[tid]
            meta[tid] = ((x1 + x2) / 2.0, (y1 + y2) / 2.0, max(x2 - x1, 1))

        for tid_a in ids:
            acx, acy, aw = meta[tid_a]
            close = []
            for tid_b in ids:
                if tid_b == tid_a:
                    continue
                bcx, bcy, bw = meta[tid_b]
                avg_w = (aw + bw) / 2.0
                d = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5
                if d / avg_w < self.PROX_RATIO:
                    close.append(tid_b)

            if len(close) >= self.CLUSTER_K:
                signals.append({
                    "key":    f"cluster_{tid_a}",
                    "type":   "proximity_cluster",
                    "score":  0.55,
                    "tracks": [tid_a] + close,
                })
            elif len(close) == 1:
                pair = tuple(sorted([tid_a, close[0]]))
                # Suppress if both are seated — that's just neighbors at desks.
                if self._seat_resolver is not None:
                    s_a = self._seat_resolver(pair[0])
                    s_b = self._seat_resolver(pair[1])
                    if s_a is not None and s_b is not None:
                        continue
                signals.append({
                    "key":    f"pair_{pair[0]}_{pair[1]}",
                    "type":   "close_pair",
                    "score":  0.30,
                    "tracks": list(pair),
                })
        return signals

    def _detect_motion_spikes(self, now: float) -> list:
        signals = []
        for tid, buf in self._track_history.items():
            if len(buf) < 2:
                continue
            t_last, cx_last, cy_last, w_last, _ = buf[-1]
            target_t = t_last - self.MOTION_WINDOW_S
            prev = None
            for entry in buf:
                if entry[0] >= target_t:
                    prev = entry
                    break
            if not prev:
                continue
            t_prev, cx_p, cy_p, w_p, _ = prev
            if (t_last - t_prev) < 0.15:
                continue
            d = ((cx_last - cx_p) ** 2 + (cy_last - cy_p) ** 2) ** 0.5
            avg_w = max((w_last + w_p) / 2.0, 1)
            if d / avg_w > self.MOTION_RATIO:
                signals.append({
                    "key":    f"motion_{tid}",
                    "type":   "sudden_motion",
                    "score":  0.40,
                    "tracks": [tid],
                })
        return signals

    def _detect_distress(self, faces: list, tracked: dict) -> list:
        """
        Flag faces whose distress score is high. If the face's bbox overlaps a
        tracked person, attribute to that track for naming.
        """
        signals = []
        for f in faces:
            d = f.get("distress")
            if d is None or d < self.DISTRESS_THRESHOLD:
                continue
            tid = self._face_to_track(f.get("bbox"), tracked)
            key = f"distress_{tid}" if tid is not None else f"distress_face_{f.get('face_idx', 0)}"
            signals.append({
                "key":    key,
                "type":   "distress_face",
                "score":  0.35,
                "tracks": [tid] if tid is not None else [],
            })
        return signals

    @staticmethod
    def _face_to_track(face_bbox, tracked: dict) -> Optional[int]:
        if not face_bbox or not tracked:
            return None
        fx1, fy1, fx2, fy2 = face_bbox
        for tid, (px1, py1, px2, py2) in tracked.items():
            if fx1 < px2 and fx2 > px1 and fy1 < py2 and fy2 > py1:
                return tid
        return None

    # ── Pose-derived signals ────────────────────────────────────────────────

    def _detect_pose_actions(self, tracked: dict) -> list:
        """raised_arm / aggressive_lean per track + wrist_reach (cross-person)."""
        signals = []
        if self._pose_resolver is None:
            return signals

        # Cache pose features per track to avoid double calls
        pose_cache = {}
        for tid in tracked.keys():
            p = self._pose_resolver(tid)
            if p is not None:
                pose_cache[tid] = p

        if not pose_cache:
            return signals

        # Per-track action signals
        for tid, p in pose_cache.items():
            if p.get("raised_arm"):
                signals.append({
                    "key":    f"raised_{tid}",
                    "type":   "raised_arm",
                    "score":  0.50,
                    "tracks": [tid],
                })
            if p.get("aggressive_lean"):
                signals.append({
                    "key":    f"lean_{tid}",
                    "type":   "aggressive_lean",
                    "score":  0.30,
                    "tracks": [tid],
                })

        # Cross-person: wrist of A inside bbox of B (a strong grab/strike cue)
        for tid_a, p in pose_cache.items():
            for wrist_xy in (p.get("l_wrist_xy"), p.get("r_wrist_xy")):
                if not wrist_xy:
                    continue
                wx, wy, wv = wrist_xy
                if wv < 0.5:
                    continue
                for tid_b, (bx1, by1, bx2, by2) in tracked.items():
                    if tid_b == tid_a:
                        continue
                    if bx1 <= wx <= bx2 and by1 <= wy <= by2:
                        pair = tuple(sorted([tid_a, tid_b]))
                        signals.append({
                            "key":    f"reach_{pair[0]}_{pair[1]}",
                            "type":   "wrist_reach",
                            "score":  0.55,    # strongest physical-contact cue
                            "tracks": [tid_a, tid_b],
                        })
                        break
        return signals


# ── Blendshape -> distress score ─────────────────────────────────────────────

# Negative-affect blendshapes used by MediaPipe FaceLandmarker. Weights chosen
# so that sustained frowning / squinting / brow-lowering reaches ~0.5+.
_DISTRESS_WEIGHTS = {
    "browDownLeft":    0.18,
    "browDownRight":   0.18,
    "mouthFrownLeft":  0.20,
    "mouthFrownRight": 0.20,
    "eyeSquintLeft":   0.10,
    "eyeSquintRight":  0.10,
    "mouthStretchLeft":  0.12,
    "mouthStretchRight": 0.12,
    "jawOpen":         0.06,   # contributes only when combined with frown
}


def distress_from_blendshapes(blendshape_categories) -> float:
    """
    Convert MediaPipe blendshape Category list -> distress score [0,1].
    Returns 0.0 if blendshapes are missing or empty.

    NOTE: oblique corner-camera angles produce noisy blendshape readings.
    Treat this as a weak prior; the detector requires SUSTAIN_S of high
    distress + a concurrent spatial signal before flagging.
    """
    if not blendshape_categories:
        return 0.0
    score = 0.0
    for cat in blendshape_categories:
        w = _DISTRESS_WEIGHTS.get(cat.category_name)
        if w:
            score += w * float(cat.score)
    return min(1.0, score)
