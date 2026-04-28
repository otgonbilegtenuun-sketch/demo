"""
safety_detector.py - low-cost school safety signals.

This module is deliberately heuristic. It flags patterns that deserve human
review and sends them through the same incident queue as bullying signals.
It does not make disciplinary or medical decisions.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Callable, Optional

import cv2
import numpy as np


def _center(bbox):
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _inside(bbox, zone):
    cx, cy = _center(bbox)
    return zone["x1"] <= cx <= zone["x2"] and zone["y1"] <= cy <= zone["y2"]


def _overlaps(a, b) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


class SafetyDetector:
    INCIDENT_COOLDOWN_S = 45.0

    BAG_CLASSES = {24: "backpack", 26: "handbag", 28: "suitcase"}
    WEAPON_LIKE_CLASSES = {
        43: "knife",
        76: "scissors",
    }

    def __init__(self):
        self.enabled = True
        self.after_hours_enabled = True
        self.restricted_zones_enabled = True
        self.fall_enabled = True
        self.running_enabled = True
        self.object_safety_enabled = True
        self.camera_tamper_enabled = True

        self.school_start = "08:00"
        self.school_end = "18:00"
        self.restricted_zones: list[dict] = []

        self.on_incident: Optional[Callable[[dict], None]] = None
        self._track_history: dict[int, deque] = {}
        self._signal_started: dict[str, float] = {}
        self._last_event_by_key: dict[str, float] = {}
        self._unattended_objects: dict[str, dict] = {}

    def configure(self, config: dict):
        self.school_start = config.get("school_start", self.school_start)
        self.school_end = config.get("school_end", self.school_end)
        self.restricted_zones = list(config.get("restricted_zones", []))

    def update_flags(self, flags: dict):
        self.enabled = bool(flags.get("safety_monitor", self.enabled))
        self.after_hours_enabled = bool(flags.get("after_hours_detect", self.after_hours_enabled))
        self.restricted_zones_enabled = bool(flags.get("restricted_zone_detect", self.restricted_zones_enabled))
        self.fall_enabled = bool(flags.get("fall_detect", self.fall_enabled))
        self.running_enabled = bool(flags.get("running_detect", self.running_enabled))
        self.object_safety_enabled = bool(flags.get("object_safety_detect", self.object_safety_enabled))
        self.camera_tamper_enabled = bool(flags.get("camera_tamper_detect", self.camera_tamper_enabled))

    def update(self, frame, tracked_persons: dict, objects: list, now: float, name_resolver: Optional[Callable] = None):
        if not self.enabled:
            return
        self._update_history(tracked_persons, now)

        signals = []
        if self.camera_tamper_enabled:
            signals += self._detect_camera_tamper(frame)
        if tracked_persons:
            if self.fall_enabled:
                signals += self._detect_falls(tracked_persons)
            if self.running_enabled:
                signals += self._detect_running(now)
            if self.restricted_zones_enabled:
                signals += self._detect_restricted_zones(tracked_persons)
            if self.after_hours_enabled and self._is_after_hours():
                signals += self._detect_after_hours(tracked_persons)
        if self.object_safety_enabled and objects:
            signals += self._detect_object_safety(objects, tracked_persons, now)

        active = {s["key"] for s in signals}
        for key in list(self._signal_started.keys()):
            if key not in active:
                self._signal_started.pop(key, None)
        for s in signals:
            self._signal_started.setdefault(s["key"], now)

        for s in signals:
            duration = now - self._signal_started.get(s["key"], now)
            if duration < s.get("sustain_s", 1.0):
                continue
            last = self._last_event_by_key.get(s["key"], 0.0)
            if now - last < self.INCIDENT_COOLDOWN_S:
                continue

            tracks = s.get("tracks", [])
            names = []
            if name_resolver:
                for tid in tracks:
                    n = name_resolver(tid)
                    if n and n != "Unknown":
                        names.append(n)

            event = {
                "timestamp": now,
                "primary_signal": s["type"],
                "concurrent_signals": s.get("concurrent", []),
                "involved_tracks": tracks,
                "involved_names": names,
                "score": round(float(s.get("score", 0.6)), 2),
                "duration_s": round(duration, 1),
            }
            if self.on_incident:
                self.on_incident(event)
            self._last_event_by_key[s["key"]] = now
            self._signal_started.pop(s["key"], None)

    def _update_history(self, tracked_persons: dict, now: float):
        for tid, bbox in tracked_persons.items():
            x1, y1, x2, y2 = bbox
            cx, cy = _center(bbox)
            w, h = max(x2 - x1, 1), max(y2 - y1, 1)
            buf = self._track_history.setdefault(tid, deque(maxlen=90))
            buf.append((now, cx, cy, w, h, bbox))
        for tid in list(self._track_history.keys()):
            if not self._track_history[tid] or now - self._track_history[tid][-1][0] > 8.0:
                self._track_history.pop(tid, None)

    def _detect_camera_tamper(self, frame) -> list:
        if frame is None or frame.size == 0:
            return [{"key": "camera_no_frame", "type": "camera_no_frame", "score": 0.95, "sustain_s": 3.0}]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray))
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        signals = []
        if mean < 12.0:
            signals.append({"key": "camera_blocked_dark", "type": "camera_blocked_or_dark", "score": 0.85, "sustain_s": 5.0})
        if blur < 5.0 and mean > 20.0:
            signals.append({"key": "camera_blurry", "type": "camera_blurry_or_covered", "score": 0.70, "sustain_s": 8.0})
        return signals

    def _detect_falls(self, tracked_persons: dict) -> list:
        signals = []
        for tid, bbox in tracked_persons.items():
            x1, y1, x2, y2 = bbox
            w, h = max(x2 - x1, 1), max(y2 - y1, 1)
            if w / h > 1.25:
                signals.append({"key": f"fall_{tid}", "type": "fall_or_collapse", "score": 0.80, "tracks": [tid], "sustain_s": 2.0})
        return signals

    def _detect_running(self, now: float) -> list:
        signals = []
        for tid, buf in self._track_history.items():
            if len(buf) < 2:
                continue
            latest = buf[-1]
            prev = None
            for item in reversed(buf):
                if now - item[0] >= 0.7:
                    prev = item
                    break
            if not prev:
                continue
            dt = max(latest[0] - prev[0], 0.1)
            dist = ((latest[1] - prev[1]) ** 2 + (latest[2] - prev[2]) ** 2) ** 0.5
            speed_ratio = dist / max(latest[3], 1) / dt
            if speed_ratio > 3.0:
                signals.append({"key": f"running_{tid}", "type": "running_or_fast_movement", "score": 0.55, "tracks": [tid], "sustain_s": 0.8})
        return signals

    def _detect_restricted_zones(self, tracked_persons: dict) -> list:
        signals = []
        for zone in self.restricted_zones:
            if not zone.get("enabled", True):
                continue
            for tid, bbox in tracked_persons.items():
                if _inside(bbox, zone):
                    name = zone.get("name", "restricted")
                    signals.append({
                        "key": f"zone_{name}_{tid}",
                        "type": "restricted_zone_entry",
                        "score": 0.75,
                        "tracks": [tid],
                        "sustain_s": 2.0,
                        "concurrent": [name],
                    })
        return signals

    def _detect_after_hours(self, tracked_persons: dict) -> list:
        tracks = list(tracked_persons.keys())[:6]
        return [{
            "key": "after_hours_presence",
            "type": "after_hours_presence",
            "score": 0.80,
            "tracks": tracks,
            "sustain_s": 5.0,
        }]

    def _detect_object_safety(self, objects: list, tracked_persons: dict, now: float) -> list:
        signals = []
        person_boxes = list(tracked_persons.values())
        for obj in objects:
            cls_id = int(obj.get("class_id", -1))
            bbox = obj.get("bbox")
            if not bbox:
                continue
            if cls_id in self.WEAPON_LIKE_CLASSES:
                signals.append({
                    "key": f"weapon_{cls_id}_{self._object_bucket(bbox)}",
                    "type": "weapon_like_object",
                    "score": 0.85,
                    "sustain_s": 0.5,
                    "concurrent": [self.WEAPON_LIKE_CLASSES[cls_id]],
                })
                continue
            if cls_id in self.BAG_CLASSES:
                if any(_overlaps(bbox, p) for p in person_boxes):
                    continue
                key = f"bag_{cls_id}_{self._object_bucket(bbox)}"
                entry = self._unattended_objects.setdefault(key, {"first_seen": now, "last_seen": now})
                entry["last_seen"] = now
                if now - entry["first_seen"] >= 45.0:
                    signals.append({
                        "key": key,
                        "type": "unattended_object",
                        "score": 0.55,
                        "sustain_s": 1.0,
                        "concurrent": [self.BAG_CLASSES[cls_id]],
                    })

        for key in list(self._unattended_objects.keys()):
            if now - self._unattended_objects[key]["last_seen"] > 20.0:
                self._unattended_objects.pop(key, None)
        return signals

    def _is_after_hours(self) -> bool:
        now = datetime.now().strftime("%H:%M")
        if self.school_start <= self.school_end:
            return now < self.school_start or now > self.school_end
        return self.school_end < now < self.school_start

    @staticmethod
    def _object_bucket(bbox) -> str:
        cx, cy = _center(bbox)
        return f"{int(cx // 80)}_{int(cy // 80)}"
