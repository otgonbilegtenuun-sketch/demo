"""
app.py — FastAPI application for Mergen AI Classroom Monitor.

All page routes return the same index.html (SPA with JS routing).
API routes are prefixed with /api/.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import threading

import database as db
from camera import (
    FEATURE_FLAGS,
    CameraManager,
    CameraProcessor,
    process_enrollment_image,
    set_clips_dir,
)
from database import get_all_students, delete_student
from log_setup import get_logger
log = get_logger(__name__)

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _load_secret() -> str:
    """Load HMAC secret from $MERGEN_SECRET, else from a per-install file
    persisted next to the DB. Avoids hard-coding a shared secret in source."""
    env = os.environ.get("MERGEN_SECRET")
    if env and len(env) >= 16:
        return env
    base = os.path.dirname(os.path.abspath(__file__))
    secret_file = os.path.join(base, ".secret")
    try:
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as f:
                s = f.read().strip()
                if len(s) >= 16:
                    return s
        import secrets as _sec
        s = _sec.token_urlsafe(32)
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(s)
        try: os.chmod(secret_file, 0o600)
        except OSError: pass
        return s
    except Exception:
        import secrets as _sec
        return _sec.token_urlsafe(32)


_SECRET = _load_secret()
_LOGIN_FAILS: Dict[str, dict] = {}
_LOGIN_MAX_FAILS = 8
_LOGIN_WINDOW_S = 15 * 60


def _login_key(username: str, request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.lower()}"


def _check_login_rate(username: str, request: Request):
    key = _login_key(username, request)
    rec = _LOGIN_FAILS.get(key)
    now = time.time()
    if not rec or now - rec["first"] > _LOGIN_WINDOW_S:
        _LOGIN_FAILS[key] = {"first": now, "count": 0}
        return
    if rec["count"] >= _LOGIN_MAX_FAILS:
        raise HTTPException(429, detail="too many login attempts")


def _note_login_result(username: str, request: Request, ok: bool):
    key = _login_key(username, request)
    if ok:
        _LOGIN_FAILS.pop(key, None)
        return
    rec = _LOGIN_FAILS.setdefault(key, {"first": time.time(), "count": 0})
    rec["count"] += 1


def _create_token(user_id: int, role: str) -> str:
    payload = json.dumps({"id": user_id, "role": role, "exp": int(time.time()) + 86400 * 7})
    p64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(_SECRET.encode(), p64.encode(), hashlib.sha256).hexdigest()
    return f"{p64}.{sig}"


def _verify_token(token: str):
    try:
        p64, sig = token.rsplit(".", 1)
        expected = hmac.new(_SECRET.encode(), p64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(p64).decode())
        if payload["exp"] < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def _get_token_optional(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return _verify_token(authorization[7:])


def _token_from_sources(authorization: Optional[str] = None,
                        token: Optional[str] = None):
    if authorization and authorization.startswith("Bearer "):
        return _verify_token(authorization[7:])
    if token:
        return _verify_token(token)
    return None


def _get_token_required(token_payload=Depends(_get_token_optional)):
    if not token_payload:
        raise HTTPException(401, detail="Нэвтрээгүй байна")
    user = db.get_user_by_id(token_payload.get("id"))
    if not user:
        raise HTTPException(401, detail="Хэрэглэгч олдсонгүй")
    token_payload["role"] = user["role"]
    token_payload["student_id"] = user.get("student_id")
    return token_payload


def require_roles(*roles: str):
    allowed = set(roles)

    def _dep(token_payload=Depends(_get_token_required)):
        if allowed and token_payload.get("role") not in allowed:
            raise HTTPException(403, detail="Энэ үйлдэлд эрх хүрэхгүй байна")
        return token_payload

    return _dep


def _require_ws_role(ws: WebSocket, *roles: str):
    payload = _verify_token(ws.query_params.get("token") or "")
    if not payload:
        return None
    user = db.get_user_by_id(payload.get("id"))
    if not user or user.get("role") not in set(roles):
        return None
    payload["role"] = user["role"]
    payload["student_id"] = user.get("student_id")
    return payload


def _clean_text(value: Optional[str], field: str, max_len: int = 80) -> str:
    value = (value or "").strip()
    if not value:
        raise HTTPException(400, f"{field} is required")
    if len(value) > max_len:
        raise HTTPException(400, f"{field} must be <= {max_len} characters")
    if any(ord(ch) < 32 for ch in value):
        raise HTTPException(400, f"{field} contains invalid characters")
    return value


def _clean_username(value: Optional[str]) -> str:
    value = _clean_text(value, "username", 40)
    if len(value) < 3:
        raise HTTPException(400, "username must be at least 3 characters")
    if not all(ch.isalnum() or ch in ("_", ".", "-") for ch in value):
        raise HTTPException(400, "username may only use letters, numbers, _, ., -")
    return value


def _student_exists(student_id: Optional[int]) -> bool:
    if not student_id:
        return False
    conn = db.get_db()
    return conn.execute(
        "SELECT 1 FROM students WHERE id=? AND role='student'",
        (student_id,),
    ).fetchone() is not None


def _safe_student_photo_dir(name: str) -> tuple[str, str]:
    safe = "".join(ch if ch.isalnum() or ch in (" ", "_", "-", ".") else "_" for ch in name)
    safe = safe.strip(" .")[:80] or f"student_{int(time.time())}"
    root = os.path.realpath(PHOTOS_DIR)
    path = os.path.realpath(os.path.join(root, safe))
    if path != root and not path.startswith(root + os.sep):
        raise HTTPException(400, "invalid student name")
    os.makedirs(path, exist_ok=True)
    return path, safe


def _actor(token_payload: Optional[dict]) -> Optional[dict]:
    if not token_payload:
        return None
    return {
        "id": token_payload.get("id"),
        "role": token_payload.get("role"),
    }


def _audit(action: str, token_payload: Optional[dict] = None,
           entity_type: str = None, entity_id: str = None, detail: str = None):
    try:
        db.log_audit(action, _actor(token_payload), entity_type, entity_id, detail)
    except Exception as e:
        log.warning(f"[Mergen AI] audit failed for {action}: {e}")

# ── App & camera ──────────────────────────────────────────────────────────────

_BASE = os.path.dirname(os.path.abspath(__file__))

app    = FastAPI(title="Mergen AI")

_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
_extra_cors = os.environ.get("MERGEN_CORS_ORIGINS", "")
if _extra_cors:
    _CORS_ORIGINS.extend([o.strip() for o in _extra_cors.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
camera = CameraProcessor()
camera_manager = CameraManager()
camera_manager.register(camera, camera_id=1, classroom_id=1, name="Camera 1")


# ── Event bus (in-process pub-sub for WebSocket fan-out) ──────────────────────
#
# Camera-thread code calls EVENT_BUS.publish() to push events; subscribers are
# asyncio.Queue instances owned by each connected WebSocket. The bus is
# thread-safe: publish hops onto the asyncio loop with call_soon_threadsafe.
class _EventBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs: List["asyncio.Queue"] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def subscribe(self) -> "asyncio.Queue":
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue"):
        with self._lock:
            try: self._subs.remove(q)
            except ValueError: pass

    def publish(self, event_type: str, payload: dict):
        """Thread-safe: callable from any thread (camera, clip writer, FastAPI)."""
        if not self._loop:
            return
        msg = {"type": event_type, "payload": payload, "ts": time.time()}
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                self._loop.call_soon_threadsafe(_safe_put, q, msg)
            except RuntimeError:
                # loop closed (during shutdown) — silently drop
                pass


def _safe_put(q: "asyncio.Queue", msg: dict):
    """Drop oldest if subscriber is full so a slow client doesn't pin memory."""
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        try: q.get_nowait()
        except asyncio.QueueEmpty: pass
        try: q.put_nowait(msg)
        except asyncio.QueueFull: pass


EVENT_BUS = _EventBus()


@app.on_event("startup")
async def _attach_event_bus_loop():
    EVENT_BUS.attach_loop(asyncio.get_running_loop())

HTML_FILE    = os.path.join(_BASE, "..", "frontend", "index.html")
FRONTEND_DIR = os.path.join(_BASE, "..", "frontend")
PHOTOS_DIR   = os.path.join(_BASE, "..", "photos")
UPLOADS_DIR  = os.path.join(_BASE, "..", "uploads")
ICONS_DIR    = os.path.join(_BASE, "..", "frontend", "icons")
CLIPS_DIR    = os.path.join(_BASE, "..", "clips")
os.makedirs(PHOTOS_DIR,  exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(ICONS_DIR,   exist_ok=True)
os.makedirs(CLIPS_DIR,   exist_ok=True)
set_clips_dir(CLIPS_DIR)


def _demo_enabled() -> bool:
    return db.get_bool_config("demo_mode_enabled", False)


def _demo_camera_count() -> int:
    return db.get_int_config("demo_camera_count", 20, 1, 64)


def _demo_camera_health() -> list:
    now = int(time.time())
    out = []
    for idx in range(1, _demo_camera_count() + 1):
        online = idx % 7 != 0
        fps = 0 if not online else 12 + (idx * 3 % 11)
        out.append({
            "camera_id": idx,
            "classroom_id": 1 + ((idx - 1) // 4),
            "name": f"Camera {idx:02d}",
            "source": "demo",
            "running": online,
            "online": online,
            "fps_actual": fps,
            "face_count": 0 if not online else idx % 5,
            "last_frame_age_s": None if not online else idx % 4,
            "last_alert": None if idx % 5 else {
                "type": "attention_down",
                "student_name": ["Tenuun", "Otgonbileg", "Bataa"][idx % 3],
                "age_s": 30 + idx,
            },
            "status": "offline" if not online else ("degraded" if fps < 15 else "online"),
            "updated_at": now,
        })
    return out


def _media_summary() -> dict:
    roots = {
        "photos": PHOTOS_DIR,
        "uploads": UPLOADS_DIR,
        "clips": CLIPS_DIR,
    }
    summary = {}
    for name, root in roots.items():
        count = 0
        total = 0
        for base, _, files in os.walk(root):
            for fn in files:
                try:
                    path = os.path.join(base, fn)
                    total += os.path.getsize(path)
                    count += 1
                except OSError:
                    pass
        summary[name] = {"files": count, "bytes": total}
    try:
        usage = shutil.disk_usage(_BASE)
        disk = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_pct": round(usage.used / usage.total * 100, 1) if usage.total else 0,
        }
    except OSError:
        disk = None
    return {"disk": disk, "media": summary}


def _demo_students() -> list:
    names = [("Tenuun", "10A"), ("Otgonbileg", "10A"), ("Bataa", "10A"), ("Anu", "10B"), ("Nomun", "10B")]
    rows = []
    for idx, (name, cls) in enumerate(names, start=1):
        present = idx != 4
        rows.append({
            "id": idx,
            "name": name,
            "class_name": cls,
            "role": "student",
            "has_face": True,
            "present_today": present,
            "present": present,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - idx * 360)),
            "attention_score": 92 - idx * 7,
            "alert_count": 0 if idx in (1, 5) else idx - 1,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - idx * 86400)),
        })
    return rows


def _demo_alerts(limit: int = 30) -> list:
    base = [
        ("Otgonbileg", "attention_down", 60),
        ("Bataa", "uniform_missing", 180),
        ("Unknown", "unknown_person", 420),
        ("Nomun", "phone_detected", 780),
    ]
    return [
        {
            "id": idx,
            "student_id": idx if name != "Unknown" else None,
            "student_name": name,
            "alert_type": kind,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - age)),
        }
        for idx, (name, kind, age) in enumerate(base, start=1)
    ][:limit]


def _demo_incidents(limit: int = 50) -> list:
    rows = [
        {
            "id": 1,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 900)),
            "primary_signal": "crowding",
            "concurrent_signals": ["rapid_motion", "close_contact"],
            "involved_names": ["Tenuun", "Bataa"],
            "score": 0.72,
            "duration_s": 8.4,
            "reviewed": 0,
            "review_outcome": None,
            "video_clip_path": None,
        },
        {
            "id": 2,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 2200)),
            "primary_signal": "fall_detected",
            "concurrent_signals": ["pose_change"],
            "involved_names": ["Nomun"],
            "score": 0.81,
            "duration_s": 4.1,
            "reviewed": 1,
            "review_outcome": "confirmed",
            "video_clip_path": None,
        },
    ]
    return rows[:limit]

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
# NOTE: /icons is also registered as an explicit route below (more reload-friendly)


def serve_html():
    return FileResponse(HTML_FILE)


@app.get("/icons/{filename}")
async def serve_icon(filename: str):
    """Serve GIF icons from frontend/icons/ — explicit route avoids mount restart issues."""
    import mimetypes
    path = os.path.realpath(os.path.join(ICONS_DIR, os.path.basename(filename)))
    root = os.path.realpath(ICONS_DIR)
    if path != root and not path.startswith(root + os.sep):
        raise HTTPException(400, detail="Invalid icon path")
    if not os.path.isfile(path):
        raise HTTPException(404, detail=f"Icon not found: {filename}")
    mime, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=mime or "image/gif")


def _require_media_roles(token: Optional[str],
                         authorization: Optional[str],
                         *roles: str):
    payload = _token_from_sources(authorization, token)
    if not payload:
        raise HTTPException(401, detail="Нэвтрээгүй байна")
    user = db.get_user_by_id(payload.get("id"))
    if not user:
        raise HTTPException(401, detail="Хэрэглэгч олдсонгүй")
    if roles and user.get("role") not in set(roles):
        raise HTTPException(403, detail="Энэ файлд хандах эрх хүрэхгүй байна")
    return user


def _safe_media_response(root_dir: str,
                         requested_path: str,
                         allowed_exts: set[str]):
    clean = (requested_path or "").replace("\\", "/").lstrip("/")
    if not clean or any(part in ("", ".", "..") for part in clean.split("/")):
        raise HTTPException(400, detail="Invalid media path")
    root = os.path.realpath(root_dir)
    path = os.path.realpath(os.path.join(root, clean))
    if not path.startswith(root + os.sep):
        raise HTTPException(400, detail="Invalid media path")
    if os.path.splitext(path)[1].lower() not in allowed_exts:
        raise HTTPException(404, detail="Media not found")
    if not os.path.isfile(path):
        raise HTTPException(404, detail="Media not found")
    return FileResponse(path)


@app.get("/photos/{file_path:path}")
async def serve_photo(file_path: str,
                      token: Optional[str] = None,
                      authorization: Optional[str] = Header(None)):
    _require_media_roles(token, authorization, "teacher", "admin")
    return _safe_media_response(PHOTOS_DIR, file_path, {".jpg", ".jpeg", ".png", ".webp"})


@app.get("/clips/{filename}")
async def serve_incident_clip(filename: str,
                              token: Optional[str] = None,
                              authorization: Optional[str] = Header(None)):
    _require_media_roles(token, authorization, "teacher", "admin")
    return _safe_media_response(CLIPS_DIR, filename, {".mp4", ".webm", ".mov"})


# ── Alert publishing helpers ──────────────────────────────────────────────────

def _emit_alert(student_id: int, student_name: str, alert_type: str):
    row = db.save_alert(student_id, student_name, alert_type)
    EVENT_BUS.publish("alert_new", row)


def _emit_unknown_alert(alert_type: str = "unknown_person"):
    row = db.save_unknown_alert(alert_type)
    EVENT_BUS.publish("alert_new", row)


# ── Recognition callback (camera thread, every 2 s) ──────────────────────────

_last_unknown_alert: float = 0.0
_UNKNOWN_COOLDOWN    = 10.0   # minimum seconds between unknown-face alerts


def _on_faces_recognized(face_data: list) -> set:
    """
    Called once per recognition cycle with all detected faces.
    face_data: list of (face_idx, embedding, attentive, sideways)
    Returns: set of face_idx that matched a known student (one-to-one assignment).
    """
    # Step 1: find best match for every face
    candidates = []
    for face_idx, embedding, attentive, sideways in face_data:
        student, sim = db.find_matching_student(embedding)
        log.info(f"[recog] face#{face_idx} best_sim={sim:.3f} match={student['name'] if student else 'none'}")
        if student:
            candidates.append((sim, face_idx, student, attentive, sideways))

    # Step 2: greedy one-to-one assignment — sort by similarity desc so the
    # best pair is claimed first; each student and each face slot used at most once.
    candidates.sort(key=lambda x: -x[0])
    assigned_students: set = set()
    matched_indices:   set = set()

    for sim, face_idx, student, attentive, sideways in candidates:
        if student["id"] in assigned_students:
            continue
        assigned_students.add(student["id"])
        matched_indices.add(face_idx)

        camera.set_face_name(face_idx, student["name"])

        # IEP/ADHD profile: skip attention bookkeeping for opted-out students.
        # Attendance still records (last_seen, total_frames) but is treated as
        # always-attentive so the student isn't penalised.
        skip_attention = camera.is_attention_disabled(student["id"])
        eff_attentive  = True if skip_attention else attentive
        db.update_attendance(student["id"], eff_attentive)
        if not skip_attention:
            db.log_attention(student["id"], student["name"], attentive)

        if camera.exam_mode and sideways and not skip_attention:
            if _should_emit_alert(student["name"], "suspicious_glance"):
                _emit_alert(student["id"], student["name"], "suspicious_glance")
                log.warning(f"[ALERT] {student['name']} suspicious glance (sim={sim:.3f})")

    return matched_indices


def _on_unknown_face(face_idx: int):
    """Called in exam mode when a face cannot be matched to any enrolled student."""
    global _last_unknown_alert
    now = time.time()
    if now - _last_unknown_alert < _UNKNOWN_COOLDOWN:
        return
    _last_unknown_alert = now
    _emit_unknown_alert("unknown_person")
    log.warning(f"[ALERT] Unknown person detected in exam mode (face slot #{face_idx})")


_uniform_log_times: dict = {}   # face_idx -> last_log_timestamp
_UNIFORM_LOG_INTERVAL = 60.0    # log at most once per minute per face slot


def _on_uniform(face_idx: int, student_name: str, is_wearing: bool):
    """Log uniform status for a recognised student (rate-limited)."""
    global _uniform_log_times
    now = time.time()
    if now - _uniform_log_times.get(face_idx, 0) < _UNIFORM_LOG_INTERVAL:
        return
    _uniform_log_times[face_idx] = now
    conn = db.get_db()
    row = conn.execute("SELECT id FROM students WHERE name=?", (student_name,)).fetchone()
    if row:
        db.log_uniform(row["id"], student_name, is_wearing)


# Per-student per-alert-type suppression window. A teacher can't act on a
# duplicate "phone detected" alert every 8 seconds, so we collapse repeats
# within ALERT_DEDUPE_S into a single row.
ALERT_DEDUPE_S = 120.0
_alert_last_seen: dict = {}   # (student_name, alert_type) -> timestamp


def _should_emit_alert(name: str, alert_type: str) -> bool:
    key = (name or "Unknown", alert_type)
    now = time.time()
    last = _alert_last_seen.get(key, 0.0)
    if (now - last) < ALERT_DEDUPE_S:
        return False
    _alert_last_seen[key] = now
    return True


def _on_phone_suspect(name: str):
    """Called when down-gaze threshold triggers a phone-use suspicion.
       Rate-limited to one row per student per ALERT_DEDUPE_S window."""
    if not _should_emit_alert(name, "phone_detected"):
        return
    conn = db.get_db()
    row  = conn.execute("SELECT id FROM students WHERE name=?", (name,)).fetchone()
    if row:
        _emit_alert(row["id"], name, "phone_detected")
    else:
        _emit_unknown_alert("phone_detected")
    log.warning(f"[ALERT] {name} phone/down-gaze detected")


def _save_review_incident(event: dict, label: str = "INCIDENT") -> int:
    iid = db.save_bullying_incident(
        primary_signal     = event.get("primary_signal", "unknown"),
        concurrent_signals = event.get("concurrent_signals", []),
        involved_names     = event.get("involved_names", []),
        score              = event.get("score", 0.0),
        duration_s         = event.get("duration_s", 0.0),
    )
    log.info(f"[{label}] flag #{iid}: {event.get('primary_signal')} "
             f"score={event.get('score')} names={event.get('involved_names')}")
    EVENT_BUS.publish("incident_new", {
        "id":                 iid,
        "label":              label,
        "primary_signal":     event.get("primary_signal", "unknown"),
        "concurrent_signals": event.get("concurrent_signals", []),
        "involved_names":     event.get("involved_names", []),
        "score":              event.get("score", 0.0),
        "duration_s":         event.get("duration_s", 0.0),
    })
    center_ts = float(event.get("timestamp", time.time()))
    pre_s  = float(event.get("clip_pre_s",  5.0))
    post_s = float(event.get("clip_post_s", 10.0))
    camera.enqueue_clip(
        center_ts, pre_s=pre_s, post_s=post_s,
        on_done=lambda path, _iid=iid: _finalize_incident_clip(_iid, path),
    )
    return iid


def _on_bullying_incident(event: dict):
    """
    Called by the camera thread when the heuristic flagger fires.
    NOTE: This flags spatial/temporal patterns that *correlate* with bullying;
    it is NOT a verdict. All incidents must be reviewed by staff.
    """
    try:
        _save_review_incident(event, "BULLYING")
    except Exception as e:
        log.error(f"[BULLYING] save error: {e}")


def _on_safety_incident(event: dict):
    """Safety signals are review prompts only; never automatic verdicts."""
    try:
        _save_review_incident(event, "SAFETY")
    except Exception as e:
        log.error(f"[SAFETY] save error: {e}")


def _finalize_incident_clip(incident_id: int, path: Optional[str]):
    """Called from the camera clip-writer thread once dump_clip finishes.
       Renames the file to a stable URL and updates the DB row."""
    if not path:
        return
    try:
        final_name = f"incident_{incident_id}.mp4"
        final_path = os.path.join(CLIPS_DIR, final_name)
        try:
            if os.path.exists(final_path):
                os.remove(final_path)
            os.rename(path, final_path)
        except Exception:
            final_path = path
            final_name = os.path.basename(path)
        url = f"/clips/{final_name}"
        db.update_bullying_clip_path(incident_id, url)
        EVENT_BUS.publish("clip_ready", {"incident_id": incident_id, "url": url})
        log.info(f"[BULLYING] clip #{incident_id} → {url}")
    except Exception as e:
        log.error(f"[BULLYING] clip finalize error #{incident_id}: {e}")


def _on_seat_attendance(seat_id: int, student_id: int, student_name: str):
    """Called when YOLO confirms a person at an assigned seat for >= 90 s.
    Primary attendance mechanism for ceiling cameras where face recognition
    is unreliable due to the top-down viewing angle."""
    try:
        db.mark_seat_attendance(student_id)
        EVENT_BUS.publish("seat_attendance", {
            "seat_id": seat_id,
            "student_id": student_id,
            "student_name": student_name,
        })
        log.info(f"[SEAT] attendance: {student_name} (seat #{seat_id})")
    except Exception as e:
        log.error(f"[SEAT] attendance error: {e}")


camera.on_recognition       = _on_faces_recognized
camera.on_unknown_face      = _on_unknown_face
camera.on_phone_suspect     = _on_phone_suspect
camera.on_uniform           = _on_uniform
camera.on_bullying_incident = _on_bullying_incident
camera.on_safety_incident   = _on_safety_incident
camera.on_seat_attendance   = _on_seat_attendance


DEFAULT_SAFETY_CONFIG = {
    "school_start": "08:00",
    "school_end": "18:00",
    "restricted_zones": [],
}


def _load_safety_config() -> dict:
    raw = db.get_config("safety_config")
    if not raw:
        return dict(DEFAULT_SAFETY_CONFIG)
    try:
        cfg = json.loads(raw)
    except Exception:
        return dict(DEFAULT_SAFETY_CONFIG)
    out = dict(DEFAULT_SAFETY_CONFIG)
    out.update({k: v for k, v in cfg.items() if k in out})
    if not isinstance(out.get("restricted_zones"), list):
        out["restricted_zones"] = []
    return out


def _save_safety_config(config: dict) -> dict:
    out = dict(DEFAULT_SAFETY_CONFIG)
    out.update({k: v for k, v in (config or {}).items() if k in out})
    for key in ("school_start", "school_end"):
        try:
            hh, mm = str(out[key]).split(":", 1)
            if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise ValueError
            out[key] = f"{int(hh):02d}:{int(mm):02d}"
        except Exception:
            raise HTTPException(400, f"{key} must be HH:MM")
    if len(out.get("restricted_zones", [])) > 20:
        raise HTTPException(400, "restricted_zones max is 20")
    zones = []
    for z in out.get("restricted_zones", []):
        try:
            x1, y1, x2, y2 = int(z["x1"]), int(z["y1"]), int(z["x2"]), int(z["y2"])
            if min(x1, y1, x2, y2) < 0 or x2 <= x1 or y2 <= y1:
                continue
            zones.append({
                "name": _clean_text(str(z.get("name") or "restricted"), "zone.name", 60),
                "x1": x1, "y1": y1,
                "x2": x2, "y2": y2,
                "enabled": bool(z.get("enabled", True)),
            })
        except Exception:
            continue
    out["restricted_zones"] = zones
    db.set_config("safety_config", json.dumps(out))
    camera.configure_safety(out)
    return out


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    db.init_db()
    log.info("[Mergen AI] Database ready")

    # Quiet down noisy ConnectionResetError tracebacks from Windows asyncio
    # proactor when WebSocket clients disconnect without a clean close frame.
    def _quiet_exception_handler(loop, context):
        exc = context.get("exception")
        msg = context.get("message", "")
        if isinstance(exc, ConnectionResetError) or "ConnectionResetError" in msg:
            return  # known-benign client drop
        loop.default_exception_handler(context)
    try:
        asyncio.get_running_loop().set_exception_handler(_quiet_exception_handler)
    except Exception:
        pass

    # Load persisted feature flags (overrides defaults baked into camera.py)
    for k in list(FEATURE_FLAGS.keys()):
        v = db.get_config(f"flag.{k}")
        if v is not None:
            FEATURE_FLAGS[k] = (v == "1")

    # Push seat map + attention profile flags to camera process
    _push_seat_map_to_camera("Class A")
    _push_attention_disabled_to_camera()
    camera.configure_safety(_load_safety_config())

    # Background purge thread — runs every 24 h
    def _purge_loop():
        while True:
            try:
                time.sleep(24 * 3600)
                days = int(db.get_config("retention_days", "30"))
                counts = db.purge_old_data(days)
                log.info(f"[purge] retention={days}d rows={counts}")
            except Exception as e:
                log.error(f"[purge] error: {e}")
                time.sleep(3600)
    threading.Thread(target=_purge_loop, daemon=True).start()


@app.on_event("shutdown")
async def _shutdown():
    camera.stop()


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def page_home():             return serve_html()

@app.get("/landing")
async def page_landing():          return serve_html()

@app.get("/login")
async def page_login():            return serve_html()

@app.get("/signup")
async def page_signup():           return serve_html()

@app.get("/about")
async def page_about():            return serve_html()

@app.get("/enroll")
async def page_enroll():           return serve_html()

@app.get("/monitor")
async def page_monitor():          return serve_html()

@app.get("/dashboard/teacher")
async def page_teacher():          return serve_html()

@app.get("/dashboard/parent")
async def page_parent():           return serve_html()

@app.get("/dashboard/admin")
async def page_admin():            return serve_html()

@app.get("/students")
async def page_students():         return serve_html()

@app.get("/incidents")
async def page_incidents():        return serve_html()

@app.get("/seats")
async def page_seats():            return serve_html()

@app.get("/admin")
async def page_admin_config():     return serve_html()


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    username: str
    password: str


class SignupBody(BaseModel):
    username: str
    password: str
    role: Optional[str] = "parent"
    full_name: Optional[str] = None
    student_id: Optional[int] = None


class DemoModeBody(BaseModel):
    enabled: bool
    camera_count: Optional[int] = None


@app.post("/api/auth/login")
async def auth_login(body: LoginBody, request: Request):
    username = _clean_username(body.username)
    if not body.password or len(body.password) > 128:
        raise HTTPException(400, detail="invalid password")
    _check_login_rate(username, request)
    user = db.authenticate_user(username, body.password)
    if not user:
        raise HTTPException(401, detail="Нэвтрэх нэр эсвэл нууц үг буруу байна")
    _note_login_result(username, request, True)
    _audit("auth.login", {"id": user["id"], "role": user["role"]}, "user", str(user["id"]))
    token = _create_token(user["id"], user["role"])
    return {
        "token": token,
        "user": {
            "id":         user["id"],
            "username":   user["username"],
            "role":       user["role"],
            "full_name":  user["full_name"],
            "student_id": user["student_id"],
        },
    }


@app.post("/api/auth/signup")
async def auth_signup(body: SignupBody):
    username = _clean_username(body.username)
    if not body.password or len(body.password) < 8 or len(body.password) > 128:
        raise HTTPException(400, detail="password must be 8..128 characters")
    signup_role = (body.role or "parent").strip()
    if signup_role != "parent":
        raise HTTPException(400, detail="self signup is parent-only")
    full_name = _clean_text(body.full_name, "full_name", 120) if body.full_name else None
    student_id = body.student_id
    if not _student_exists(student_id):
        raise HTTPException(400, detail="parent signup requires a valid student")

    if db.username_exists(username):
        raise HTTPException(400, detail="Энэ нэвтрэх нэр аль хэдийн бүртгэлтэй байна")
    uid = db.create_user(
        username=username,
        password=body.password,
        role=signup_role,
        student_id=student_id,
        full_name=full_name,
    )
    user = db.get_user_by_id(uid)
    _audit("auth.signup", {"id": uid, "role": signup_role}, "user", str(uid))
    token = _create_token(uid, signup_role)
    return {
        "token": token,
        "user": {
            "id":         user["id"],
            "username":   user["username"],
            "role":       signup_role,
            "full_name":  user["full_name"],
            "student_id": user["student_id"],
        },
    }


@app.get("/api/auth/me")
async def auth_me(token_payload=Depends(_get_token_required)):
    if not token_payload:
        raise HTTPException(401, detail="Нэвтрээгүй байна")
    user = db.get_user_by_id(token_payload["id"])
    if not user:
        raise HTTPException(401, detail="Хэрэглэгч олдсонгүй")
    return {
        "id":         user["id"],
        "username":   user["username"],
        "role":       user["role"],
        "full_name":  user["full_name"],
        "student_id": user["student_id"],
    }


@app.get("/api/auth/students")
async def students_for_signup():
    """Return students list for parent signup (no auth required)."""
    return db.get_students_list()


# ── Video stream ──────────────────────────────────────────────────────────────

@app.get("/video_feed")
async def video_feed(request: Request,
                     token: Optional[str] = None,
                     authorization: Optional[str] = Header(None)):
    payload = _token_from_sources(authorization, token)
    user = db.get_user_by_id(payload.get("id")) if payload else None
    if not user or user.get("role") != "admin":
        raise HTTPException(401, detail="Нэвтрээгүй байна")

    async def _stream():
        _ph = None  # cached placeholder frame bytes
        try:
            while True:
                # Stop encoding if the client navigated away — otherwise we keep
                # JPEG-compressing forever, burning CPU per disconnected viewer.
                if await request.is_disconnected():
                    return
                frame = camera.get_frame()
                if frame is None:
                    if _ph is None:
                        ph = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.rectangle(ph, (0, 0), (640, 480), (240, 242, 247), -1)
                        cv2.putText(ph, "Mergen AI", (195, 210),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (79, 70, 229), 2)
                        cv2.putText(ph, "Камер эхлүүлэх товчийг дарна уу", (115, 260),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 120, 140), 1)
                        _, buf = cv2.imencode(".jpg", ph, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        _ph = buf.tobytes()
                    data = _ph
                else:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    data = buf.tobytes()

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + data
                    + b"\r\n"
                )
                await asyncio.sleep(0.066)
        except (asyncio.CancelledError, GeneratorExit):
            return

    return StreamingResponse(
        _stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store"},
    )


# ── Camera control ────────────────────────────────────────────────────────────

@app.post("/api/camera/start")
async def camera_start(token_payload=Depends(require_roles("admin"))):
    ok = camera.start()
    if not ok:
        raise HTTPException(503, detail="Камер нээгдсэнгүй. Өөр програм ашиглаж байна уу?")
    _audit("camera.start", token_payload, "camera", "1")
    return {"status": "started"}


@app.post("/api/camera/stop")
async def camera_stop(token_payload=Depends(require_roles("admin"))):
    camera.stop()
    _audit("camera.stop", token_payload, "camera", "1")
    return {"status": "stopped"}


@app.post("/api/test/recognize")
async def test_recognize(file: UploadFile = File(...),
                         _=Depends(require_roles("teacher", "admin"))):
    """Upload a photo — returns which enrolled student matches (or not)."""
    content = await file.read()
    arr     = np.frombuffer(content, np.uint8)
    frame   = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Зураг уншигдсангүй")

    import base64
    _, buf = cv2.imencode(".jpg", frame)
    b64    = "data:image/jpeg;base64," + base64.b64encode(buf).decode()

    from camera import process_enrollment_image
    emb = await run_in_threadpool(process_enrollment_image, b64)
    if emb is None:
        return {"matched": False, "reason": "Нүүр илрүүлэгдсэнгүй"}

    student, sim = db.find_matching_student(emb)
    if student:
        return {
            "matched":    True,
            "name":       student["name"],
            "class_name": student["class_name"],
            "similarity": round(float(sim), 3),
        }
    return {
        "matched":    False,
        "reason":     "Тохирох оюутан олдсонгүй",
        "best_sim":   round(float(sim), 3),
    }


_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


def _safe_upload_path(name: Optional[str], default: str) -> str:
    """Sanitize a user-supplied filename and resolve it under UPLOADS_DIR.
    Rejects anything that escapes the uploads directory or has a non-video ext."""
    base = os.path.basename(name or default).strip() or default
    # Drop control chars + path separators that os.path.basename doesn't strip on every OS
    base = base.replace("\\", "_").replace("/", "_")
    root, ext = os.path.splitext(base)
    if ext.lower() not in _VIDEO_EXTS:
        ext = ".mp4"
    base = (root[:80] or "upload") + ext.lower()
    save_path = os.path.realpath(os.path.join(UPLOADS_DIR, base))
    if not save_path.startswith(os.path.realpath(UPLOADS_DIR) + os.sep):
        raise HTTPException(400, "Invalid filename")
    return save_path


@app.post("/api/video/upload")
async def video_upload(file: UploadFile = File(...),
                       batch: bool = False,
                       token_payload=Depends(require_roles("admin"))):
    """Upload a video file and process it as if it were a live camera feed.

    Streams the upload to disk in chunks (1 MB) so memory stays flat even for
    multi-GB files; enforces an extension allowlist and a size cap.

    Pass ?batch=true to enable batch mode: processes frames as fast as possible
    without MJPEG streaming, suitable for offline analysis of recorded video."""
    save_path = _safe_upload_path(file.filename, "upload.mp4")
    written = 0
    try:
        with open(save_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_UPLOAD_BYTES:
                    f.close()
                    try: os.remove(save_path)
                    except OSError: pass
                    raise HTTPException(413, f"File exceeds {_MAX_UPLOAD_BYTES // (1024*1024)} MB limit")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        try: os.remove(save_path)
        except OSError: pass
        raise HTTPException(500, f"Upload failed: {e}")

    ok = await run_in_threadpool(camera.start_from_file, save_path, batch)
    if not ok:
        try: os.remove(save_path)
        except OSError: pass
        raise HTTPException(400, "Видео файл нээгдсэнгүй. Формат дэмжигдэж байна уу?")
    _audit("video.upload", token_payload, "upload", os.path.basename(save_path), f"{written} bytes batch={batch}")
    return {"status": "started", "filename": os.path.basename(save_path), "batch": batch}


@app.get("/api/cameras")
async def cameras_list(_=Depends(require_roles("admin"))):
    """List registered cameras. Today returns exactly one entry; v0.3 will
       return one per RTSP stream registered with the CameraManager."""
    if _demo_enabled():
        cams = _demo_camera_health()
        return {
            "default_id": 1,
            "cameras": [
                {
                    "camera_id": c["camera_id"],
                    "classroom_id": c["classroom_id"],
                    "name": c["name"],
                    "running": c["running"],
                    "source": c["source"],
                }
                for c in cams
            ],
        }
    return {
        "default_id": camera_manager.default_id,
        "cameras":    camera_manager.list(),
    }


@app.get("/api/cameras/health")
async def cameras_health(_=Depends(require_roles("teacher", "admin"))):
    if _demo_enabled():
        return {
            "demo_mode": True,
            "summary": {
                "total": _demo_camera_count(),
                "online": sum(1 for c in _demo_camera_health() if c["online"]),
                "offline": sum(1 for c in _demo_camera_health() if not c["online"]),
            },
            "cameras": _demo_camera_health(),
        }
    progress = camera.batch_progress
    faces = camera.recognized_faces
    status = {
        "camera_id": 1,
        "classroom_id": 1,
        "name": "Camera 01",
        "source": "local",
        "running": camera.is_running,
        "online": camera.is_running,
        "fps_actual": progress.get("fps_actual", 0),
        "face_count": len(faces),
        "last_frame_age_s": None,
        "last_alert": None,
        "status": "online" if camera.is_running else "offline",
        "updated_at": int(time.time()),
    }
    return {
        "demo_mode": False,
        "summary": {
            "total": 1,
            "online": 1 if camera.is_running else 0,
            "offline": 0 if camera.is_running else 1,
        },
        "cameras": [status],
    }


@app.get("/api/camera/status")
async def camera_status(_=Depends(require_roles("admin"))):
    if _demo_enabled():
        faces = [
            {"name": "Tenuun", "attentive": True, "looking_down": False, "uniform_on": True},
            {"name": "Otgonbileg", "attentive": False, "looking_down": True, "uniform_on": True},
            {"name": "Bataa", "attentive": True, "looking_down": False, "uniform_on": False},
        ]
        return {
            "running": True,
            "exam_mode": camera.exam_mode,
            "face_count": len(faces),
            "batch": {
                "batch_mode": False, "current_frame": 0,
                "total_frames": 0, "percent": 0,
                "elapsed_s": 0, "fps_actual": 0,
            },
            "faces": faces,
        }
    faces = camera.recognized_faces if camera.is_running else []
    bp = camera.batch_progress
    return {
        "running":    camera.is_running,
        "exam_mode":  camera.exam_mode,
        "face_count": len(faces),
        "batch":      bp,
        "playback":   camera.playback_info,
        "faces": [
            {
                "name":         f.get("name", "Unknown"),
                "attentive":    f.get("attentive"),
                "looking_down": f.get("looking_down"),
                "uniform_on":   f.get("uniform_on"),
            }
            for f in faces
        ],
    }


# ── Video playback controls ──────────────────────────────────────────────────

@app.post("/api/camera/pause")
async def camera_pause(_=Depends(require_roles("admin"))):
    camera.pause()
    return {"ok": True}


@app.post("/api/camera/resume")
async def camera_resume(_=Depends(require_roles("admin"))):
    camera.resume()
    return {"ok": True}


@app.post("/api/camera/seek")
async def camera_seek(seconds: float, _=Depends(require_roles("admin"))):
    camera.seek(seconds)
    return {"ok": True}


# ── Exam mode ─────────────────────────────────────────────────────────────────

class ExamModeBody(BaseModel):
    enabled: bool


# ── Person lock ───────────────────────────────────────────────────────────────

class LockBody(BaseModel):
    nx: float   # normalised x (0–1)
    ny: float   # normalised y (0–1)


@app.get("/api/exam_mode")
async def get_exam_mode(_=Depends(require_roles("teacher", "admin"))):
    return {"enabled": camera.exam_mode}


@app.post("/api/exam_mode")
async def set_exam_mode(body: ExamModeBody, _=Depends(require_roles("admin"))):
    camera.exam_mode = body.enabled
    return {"enabled": camera.exam_mode}


@app.post("/api/lock")
async def lock_person(body: LockBody, _=Depends(require_roles("admin"))):
    if not (0 <= body.nx <= 1 and 0 <= body.ny <= 1):
        raise HTTPException(400, "coordinates must be between 0 and 1")
    tid = camera.lock_at_point(body.nx, body.ny)
    return {"locked": tid is not None, "track_id": tid}


@app.post("/api/unlock")
async def unlock_person(_=Depends(require_roles("admin"))):
    camera.unlock()
    return {"locked": False}


# ── Enrollment ────────────────────────────────────────────────────────────────

class EnrollBody(BaseModel):
    name:       str
    class_name: str
    role:       str = "student"
    images:     List[str]


@app.post("/api/enroll")
async def enroll(body: EnrollBody, token_payload=Depends(require_roles("teacher", "admin"))):
    name = _clean_text(body.name, "name", 80)
    class_name = _clean_text(body.class_name, "class_name", 40)
    role = (body.role or "student").strip()
    if role != "student":
        raise HTTPException(400, "role must be student")
    if not body.images or len(body.images) > 6:
        raise HTTPException(400, "images must contain 1..6 items")

    embeddings = []
    student_photos_dir, photo_dir_name = _safe_student_photo_dir(name)

    for i, img in enumerate(body.images):
        if not isinstance(img, str) or len(img) > 12 * 1024 * 1024:
            raise HTTPException(400, "invalid enrollment image")
        e = await run_in_threadpool(process_enrollment_image, img)
        if e is not None:
            embeddings.append(e)
            try:
                img_data  = img.split(",")[1] if "," in img else img
                img_bytes = base64.b64decode(img_data, validate=True)
                with open(os.path.join(student_photos_dir, f"{i+1}.jpg"), "wb") as f:
                    f.write(img_bytes)
            except Exception as ex:
                log.error(f"[enroll] photo save error: {ex}")

    if not embeddings:
        raise HTTPException(400, "Нүүр илрүүлэгдсэнгүй. Гэрэлтэй газарт зураг авна уу.")
    avg_emb    = np.mean(embeddings, axis=0).astype(np.float32)
    student_id = db.save_student(name, class_name, role, avg_emb)
    _audit("student.enroll", token_payload, "student", str(student_id), f"{name} / {class_name}")
    return {"success": True, "id": student_id, "name": name, "captures": len(embeddings),
            "photo_url": f"/photos/{photo_dir_name}/1.jpg"}


# ── Attendance & analytics ────────────────────────────────────────────────────

@app.get("/api/attendance/today")
async def attendance_today(_=Depends(require_roles("teacher", "admin"))):
    if _demo_enabled():
        return _demo_students()
    return db.get_today_attendance()


@app.get("/api/attendance/stats")
async def attendance_stats(_=Depends(require_roles("teacher", "admin"))):
    if _demo_enabled():
        rows = _demo_students()
        present = sum(1 for r in rows if r["present"])
        total = len(rows)
        avg_attention = round(sum(r["attention_score"] for r in rows if r["present"]) / max(present, 1))
        return {
            "total_students": total,
            "total": total,
            "present": present,
            "absent": total - present,
            "attendance_rate": round(present / max(total, 1) * 100),
            "avg_attention": avg_attention,
            "total_alerts": sum(r["alert_count"] for r in rows),
        }
    return db.get_admin_stats()


@app.get("/api/attention/history")
async def attention_history(_=Depends(require_roles("teacher", "admin"))):
    if _demo_enabled():
        return [
            {"time_label": f"{h:02d}:00", "avg_attention": 70 + ((h * 7) % 24)}
            for h in range(8, 17)
        ]
    return db.get_attention_history()


@app.get("/api/parent/student")
async def parent_student(token_payload=Depends(require_roles("parent"))):
    student_id = token_payload.get("student_id")
    if not student_id:
        raise HTTPException(404, "Хүүхэд холбогдоогүй байна")
    conn = db.get_db()
    row = conn.execute(
        "SELECT id, name, class_name FROM students WHERE id=?", (student_id,)
    ).fetchone()
    s = dict(row) if row else None

    if not s:
        raise HTTPException(404, "Бүртгэлтэй оюутан байхгүй")
    today = db.get_today_attendance()
    info  = next((x for x in today if x["id"] == s["id"]), None)
    return {"student": s, "today": info}


@app.get("/api/parent/history")
async def parent_history(days: int = 14, token_payload=Depends(require_roles("parent"))):
    if days < 1 or days > 90:
        raise HTTPException(400, "days must be 1..90")
    student_id = token_payload.get("student_id")

    if not student_id:
        return []

    conn = db.get_db()
    rows = conn.execute(
        """SELECT a.date,
                  CAST(julianday('now','localtime') - julianday(a.date) AS INTEGER) AS days_ago,
                  (a.total_frames > 0) AS present,
                  a.arrived_at,
                  CASE WHEN a.total_frames > 0
                       THEN ROUND(CAST(a.attention_frames AS REAL) / a.total_frames * 100)
                       ELSE 0 END AS attention_score
           FROM attendance a
           WHERE a.student_id = ?
             AND a.date >= date('now','localtime',? || ' days')
           ORDER BY a.date DESC""",
        (student_id, f"-{days}"),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Student management ────────────────────────────────────────────────────────

@app.get("/api/students")
async def list_students(_=Depends(require_roles("teacher", "admin"))):
    if _demo_enabled():
        return _demo_students()
    students = get_all_students()
    for s in students:
        safe = "".join(ch if ch.isalnum() or ch in (" ", "_", "-", ".") else "_" for ch in s["name"])
        safe = safe.strip(" .")[:80] or f"student_{s['id']}"
        photo_path = os.path.join(PHOTOS_DIR, safe, "1.jpg")
        s["photo_url"] = f"/photos/{safe}/1.jpg" if os.path.exists(photo_path) else None
    return students


@app.delete("/api/students/{student_id}")
async def remove_student(student_id: int, token_payload=Depends(require_roles("teacher", "admin"))):
    ok = delete_student(student_id)
    if not ok:
        raise HTTPException(404, "Оюутан олдсонгүй")
    _audit("student.delete", token_payload, "student", str(student_id))
    return {"success": True, "deleted_id": student_id}


# ── Alerts ────────────────────────────────────────────────────────────────────

@app.get("/api/alerts/recent")
async def alerts_recent(since_id: int = 0, _=Depends(require_roles("teacher", "admin"))):
    if since_id < 0:
        raise HTTPException(400, "since_id must be >= 0")
    if _demo_enabled():
        return [a for a in _demo_alerts() if a["id"] > since_id]
    return db.get_recent_alerts(since_id=since_id)


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    """Push channel for alerts, incidents, clip-ready, and periodic camera status.
       Frontend uses this when available and falls back to polling on disconnect."""
    payload = _require_ws_role(ws, "teacher", "admin")
    if not payload:
        await ws.close(code=1008)
        return
    await ws.accept()
    q = EVENT_BUS.subscribe()
    status_task = asyncio.create_task(_ws_status_loop(ws))
    try:
        while True:
            msg = await q.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"[ws] events error: {e}")
    finally:
        status_task.cancel()
        EVENT_BUS.unsubscribe(q)


async def _ws_status_loop(ws: WebSocket):
    """Push camera_status every 2s on its own cadence (don't block the bus)."""
    try:
        while True:
            faces = camera.recognized_faces
            bp = camera.batch_progress
            await ws.send_json({
                "type": "camera_status",
                "ts":   time.time(),
                "payload": {
                    "running":    camera.is_running,
                    "exam_mode":  camera.exam_mode,
                    "face_count": len(faces),
                    "batch":      bp,
                    "faces": [
                        {
                            "name":         f.get("name", "Unknown"),
                            "attentive":    f.get("attentive"),
                            "looking_down": f.get("looking_down"),
                            "uniform_on":   f.get("uniform_on"),
                        }
                        for f in faces
                    ],
                },
            })
            await asyncio.sleep(2.0)
    except (asyncio.CancelledError, WebSocketDisconnect):
        return
    except Exception as e:
        log.error(f"[ws] status loop error: {e}")


class PhoneBody(BaseModel):
    student_name: Optional[str] = None


@app.post("/api/alerts/phone")
async def phone_alert(body: PhoneBody = None, _=Depends(require_roles("teacher", "admin"))):
    s = db.get_first_student()
    if not s:
        raise HTTPException(404, "Бүртгэлтэй оюутан байхгүй")
    name = _clean_text(body.student_name, "student_name", 80) if body and body.student_name else s["name"]
    _emit_alert(s["id"], name, "phone_detected")
    return {"success": True, "student": name}


# ── Bullying / incident flagging ──────────────────────────────────────────────

class BullyingReviewBody(BaseModel):
    outcome: str   # confirmed | false_positive | inconclusive


class BullyingConfigBody(BaseModel):
    enabled: bool


@app.get("/api/bullying/recent")
async def bullying_recent(since_id: int = 0, limit: int = 50,
                          _=Depends(require_roles("teacher", "admin"))):
    if since_id < 0:
        raise HTTPException(400, "since_id must be >= 0")
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be 1..200")
    if _demo_enabled():
        return [i for i in _demo_incidents(limit) if i["id"] > since_id]
    return db.get_recent_bullying_incidents(since_id=since_id, limit=limit)


@app.get("/api/bullying/stats")
async def bullying_stats(_=Depends(require_roles("teacher", "admin"))):
    if _demo_enabled():
        rows = _demo_incidents()
        pending = sum(1 for r in rows if not r["reviewed"])
        return {
            "today": len(rows),
            "week": len(rows),
            "pending_review": pending,
            "by_signal_week": [
                {"primary_signal": "crowding", "count": 1},
                {"primary_signal": "fall_detected", "count": 1},
            ],
        }
    return db.get_bullying_stats()


@app.post("/api/bullying/{incident_id}/review")
async def bullying_review(incident_id: int, body: BullyingReviewBody,
                          token_payload=Depends(require_roles("teacher", "admin"))):
    if body.outcome not in ("confirmed", "false_positive", "inconclusive"):
        raise HTTPException(400, "Invalid outcome")
    ok = db.review_bullying_incident(incident_id, body.outcome)
    if not ok:
        raise HTTPException(404, "Incident not found")
    _audit("incident.review", token_payload, "incident", str(incident_id), body.outcome)
    return {"success": True}


@app.get("/api/bullying/config")
async def bullying_config_get(_=Depends(require_roles("teacher", "admin"))):
    return {"enabled": camera._bullying.enabled}


@app.post("/api/bullying/config")
async def bullying_config_set(body: BullyingConfigBody,
                              _=Depends(require_roles("teacher", "admin"))):
    camera._bullying.enabled = body.enabled
    return {"enabled": camera._bullying.enabled}


# ── Uniform ───────────────────────────────────────────────────────────────────

@app.get("/api/uniform/today")
async def uniform_today(token_payload=Depends(_get_token_required)):
    rows = db.get_today_uniform()
    if token_payload.get("role") == "parent":
        student_id = token_payload.get("student_id")
        return [r for r in rows if r["id"] == student_id] if student_id else []
    if token_payload.get("role") in ("teacher", "admin"):
        return rows
    raise HTTPException(403, "forbidden")


@app.get("/api/uniform/stats")
async def uniform_stats(_=Depends(require_roles("teacher", "admin"))):
    return db.get_uniform_stats()


@app.get("/api/uniform/weekly")
async def uniform_weekly(_=Depends(require_roles("teacher", "admin"))):
    return db.get_uniform_weekly()


# ── Reset ─────────────────────────────────────────────────────────────────────

@app.post("/api/reset")
async def reset_demo(token_payload=Depends(require_roles("admin"))):
    db.reset_today_data()
    _audit("demo.reset_today", token_payload, "demo", "today")
    return {"success": True}


# ── Seat map ──────────────────────────────────────────────────────────────────

class SeatBody(BaseModel):
    student_id: Optional[int] = None
    x1: int
    y1: int
    x2: int
    y2: int


class SeatMapBody(BaseModel):
    class_name: str = "Class A"
    seats: List[SeatBody]


def _push_seat_map_to_camera(class_name: str = "Class A"):
    """Reload the camera's in-memory seat map from the DB."""
    seats = db.get_seat_map(class_name)
    camera.set_seat_map([
        {
            "id":           s["id"],
            "student_id":   s["student_id"],
            "student_name": s.get("student_name"),
            "x1": s["x1"], "y1": s["y1"], "x2": s["x2"], "y2": s["y2"],
        }
        for s in seats
    ])
    return seats


@app.get("/api/seats")
async def seats_get(class_name: str = "Class A",
                    _=Depends(require_roles("teacher", "admin"))):
    class_name = _clean_text(class_name, "class_name", 40)
    return db.get_seat_map(class_name)


@app.post("/api/seats")
async def seats_set(body: SeatMapBody, token_payload=Depends(require_roles("teacher", "admin"))):
    class_name = _clean_text(body.class_name, "class_name", 40)
    if len(body.seats) > 80:
        raise HTTPException(400, "too many seats")
    for s in body.seats:
        if min(s.x1, s.y1, s.x2, s.y2) < 0:
            raise HTTPException(400, "seat coordinates must be >= 0")
        if s.x2 <= s.x1 or s.y2 <= s.y1:
            raise HTTPException(400, "invalid seat rectangle")
        if s.student_id is not None and not _student_exists(s.student_id):
            raise HTTPException(400, "seat student_id does not exist")
    db.replace_seat_map(class_name, [s.dict() for s in body.seats])
    seats = _push_seat_map_to_camera(class_name)
    _audit("seats.save", token_payload, "classroom", class_name, f"{len(seats)} seats")
    return {"saved": len(seats), "seats": seats}


@app.delete("/api/seats")
async def seats_clear(class_name: str = "Class A",
                      token_payload=Depends(require_roles("teacher", "admin"))):
    class_name = _clean_text(class_name, "class_name", 40)
    db.clear_seat_map(class_name)
    _push_seat_map_to_camera(class_name)
    _audit("seats.clear", token_payload, "classroom", class_name)
    return {"cleared": True}


@app.get("/api/seats/occupancy")
async def seats_occupancy(_=Depends(require_roles("teacher", "admin"))):
    return camera.get_seat_occupancy_snapshot()


@app.get("/api/snapshot")
async def snapshot(_=Depends(require_roles("teacher", "admin"))):
    """Return the latest annotated camera frame as JPEG — used by the seat editor."""
    frame = camera.get_frame()
    if frame is None:
        raise HTTPException(503, "Камер ажиллахгүй байна")
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(500, "encode failed")
    from fastapi.responses import Response
    return Response(content=buf.tobytes(), media_type="image/jpeg")


# ── Appearance re-identification (ceiling cameras) ───────────────────────────

@app.post("/api/appearance/calibrate")
async def appearance_calibrate(token_payload=Depends(require_roles("teacher", "admin"))):
    """Auto-calibrate appearance for all occupied seats that have assigned students.
    Teacher calls this once at the start of class after confirming seating."""
    if not camera.is_running:
        raise HTTPException(400, "Camera not running")
    seats = db.get_seat_map("Class A")
    calibrated = []
    for seat in seats:
        sid = seat.get("student_id")
        if not sid:
            continue
        student = db.get_student_by_id(sid)
        if not student:
            continue
        ok = camera.calibrate_appearance(
            seat["id"], sid, student["name"])
        if ok:
            calibrated.append({"seat_id": seat["id"],
                               "student_id": sid,
                               "student_name": student["name"]})
    _audit("appearance.calibrate", token_payload, "system", "", f"{len(calibrated)} students")
    return {"calibrated": len(calibrated), "students": calibrated}


@app.get("/api/appearance/status")
async def appearance_status(_=Depends(require_roles("teacher", "admin"))):
    return {
        "calibrated": camera.appearance_tracker.is_calibrated,
        "profiles": camera.appearance_tracker.get_profiles_summary(),
    }


# ── Per-student behavior profile ──────────────────────────────────────────────

class StudentProfileBody(BaseModel):
    attention_disabled: Optional[bool] = None
    distress_disabled:  Optional[bool] = None
    profile_note:       Optional[str]  = None


def _push_attention_disabled_to_camera():
    camera.set_attention_disabled_ids(db.get_attention_disabled_ids())


@app.get("/api/students/{student_id}/profile")
async def student_profile_get(student_id: int, _=Depends(require_roles("admin"))):
    p = db.get_student_profile(student_id)
    if not p:
        raise HTTPException(404, "Оюутан олдсонгүй")
    return p


@app.patch("/api/students/{student_id}/profile")
async def student_profile_patch(student_id: int, body: StudentProfileBody,
                                _=Depends(require_roles("admin"))):
    if body.profile_note is not None and len(body.profile_note) > 500:
        raise HTTPException(400, "profile_note must be <= 500 characters")
    ok = db.update_student_profile(
        student_id,
        attention_disabled=body.attention_disabled,
        distress_disabled=body.distress_disabled,
        profile_note=body.profile_note,
    )
    if not ok:
        raise HTTPException(400, "no change")
    _push_attention_disabled_to_camera()
    return db.get_student_profile(student_id)


# ── Admin config: feature flags + retention ───────────────────────────────────

class FeatureFlagsBody(BaseModel):
    uniform_detect:     Optional[bool] = None
    unknown_face_alert: Optional[bool] = None
    phone_detect:       Optional[bool] = None
    pose_signals:       Optional[bool] = None
    safety_monitor:     Optional[bool] = None
    fall_detect:        Optional[bool] = None
    running_detect:     Optional[bool] = None
    restricted_zone_detect: Optional[bool] = None
    after_hours_detect: Optional[bool] = None
    object_safety_detect: Optional[bool] = None
    camera_tamper_detect: Optional[bool] = None


class RetentionBody(BaseModel):
    days: int


class SafetyConfigBody(BaseModel):
    school_start: str = "08:00"
    school_end: str = "18:00"
    restricted_zones: List[Dict[str, Any]] = []


@app.get("/api/admin/flags")
async def admin_flags_get(_=Depends(require_roles("admin"))):
    return dict(FEATURE_FLAGS)


@app.post("/api/admin/flags")
async def admin_flags_set(body: FeatureFlagsBody, token_payload=Depends(require_roles("admin"))):
    for k, v in body.dict(exclude_none=True).items():
        if k in FEATURE_FLAGS:
            FEATURE_FLAGS[k] = bool(v)
            db.set_config(f"flag.{k}", "1" if v else "0")
    _audit("admin.flags", token_payload, "config", "feature_flags")
    return dict(FEATURE_FLAGS)


@app.get("/api/admin/retention")
async def admin_retention_get(_=Depends(require_roles("admin"))):
    days = int(db.get_config("retention_days", "30"))
    return {"days": days}


@app.post("/api/admin/retention")
async def admin_retention_set(body: RetentionBody, token_payload=Depends(require_roles("admin"))):
    if body.days < 1 or body.days > 3650:
        raise HTTPException(400, "days must be 1..3650")
    db.set_config("retention_days", str(body.days))
    _audit("admin.retention", token_payload, "config", "retention_days", str(body.days))
    return {"days": body.days}


@app.post("/api/admin/purge")
async def admin_purge_now(token_payload=Depends(require_roles("admin"))):
    days = int(db.get_config("retention_days", "30"))
    counts = db.purge_old_data(days)
    # Also purge old clip files
    cutoff = time.time() - days * 86400
    purged_clips = 0
    try:
        for fn in os.listdir(CLIPS_DIR):
            p = os.path.join(CLIPS_DIR, fn)
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p); purged_clips += 1
    except Exception as e:
        log.error(f"[purge] clip cleanup error: {e}")
    _audit("admin.purge", token_payload, "retention", str(days), json.dumps(counts))
    return {"days": days, "rows_deleted": counts, "clips_deleted": purged_clips}


@app.get("/api/safety/config")
async def safety_config_get(_=Depends(require_roles("admin"))):
    return _load_safety_config()


@app.post("/api/safety/config")
async def safety_config_set(body: SafetyConfigBody, token_payload=Depends(require_roles("admin"))):
    saved = _save_safety_config(body.dict())
    _audit("safety.config", token_payload, "config", "safety")
    return saved


@app.post("/api/clips/manual")
async def manual_clip_capture(token_payload=Depends(require_roles("admin"))):
    if camera.get_frame() is None:
        raise HTTPException(503, "camera is not running or no replay buffer is available")
    event = {
        "timestamp": time.time(),
        "primary_signal": "manual_capture",
        "concurrent_signals": [],
        "involved_names": [],
        "score": 1.0,
        "duration_s": 0.0,
        "clip_pre_s": 30.0,
        "clip_post_s": 0.0,
    }
    iid = _save_review_incident(event, "MANUAL")
    _audit("clip.manual", token_payload, "incident", str(iid))
    return {"success": True, "incident_id": iid}


# ── Threshold-tuning suggestion (read-only) ───────────────────────────────────

@app.get("/api/bullying/threshold-suggestion")
async def bullying_threshold_suggestion(_=Depends(require_roles("admin"))):
    """Return per-signal precision and a suggested threshold from reviewed
       incidents. Caller can apply manually via /api/bullying/config (not
       auto-applied — needs human sanity-check)."""
    rows = db.get_review_stats_by_signal()
    return {
        "current_threshold": camera._bullying.INCIDENT_THRESHOLD,
        "by_signal":         rows,
        "advice": (
            "Review at least 30 incidents before trusting suggestions. "
            "Apply by editing INCIDENT_THRESHOLD in bullying_detector.py."
        ),
    }


# ── Eval workflow (record → label → run) ──────────────────────────────────────

EVAL_DIR        = os.path.abspath(os.path.join(_BASE, "..", "eval"))
EVAL_CLIPS_DIR  = os.path.join(EVAL_DIR, "clips")
EVAL_LABELS_CSV = os.path.join(EVAL_DIR, "labels.csv")
EVAL_RESULTS    = os.path.join(EVAL_DIR, "last_run.json")
os.makedirs(EVAL_CLIPS_DIR, exist_ok=True)

ALLOWED_LABELS = {"fight", "crowd_bully", "normal", "crowd_normal", "note_passing"}

@app.get("/eval_clips/{filename}")
async def serve_eval_clip(filename: str,
                          token: Optional[str] = None,
                          authorization: Optional[str] = Header(None)):
    _require_media_roles(token, authorization, "teacher", "admin")
    return _safe_media_response(EVAL_CLIPS_DIR, filename, {".mp4", ".webm", ".mov"})


def _read_labels_csv() -> dict:
    import csv
    out = {}
    if os.path.exists(EVAL_LABELS_CSV):
        with open(EVAL_LABELS_CSV) as f:
            for row in csv.DictReader(f):
                if row.get("filename") and row.get("truth_label"):
                    out[row["filename"]] = row["truth_label"]
    return out


def _write_labels_csv(labels: dict):
    import csv
    with open(EVAL_LABELS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "truth_label"])
        w.writeheader()
        for fn, lbl in sorted(labels.items()):
            w.writerow({"filename": fn, "truth_label": lbl})


class EvalRecordBody(BaseModel):
    duration_s: int = 60
    filename:   Optional[str] = None


@app.post("/api/eval/record/start")
async def eval_record_start(body: EvalRecordBody,
                            _=Depends(require_roles("teacher", "admin"))):
    if not camera.is_running:
        raise HTTPException(503, "Камер ажиллахгүй байна. Эхлүүлнэ үү.")
    if body.duration_s < 5 or body.duration_s > 600:
        raise HTTPException(400, "duration_s must be 5..600")
    fn = body.filename or f"clip_{int(time.time())}.mp4"
    if not fn.endswith(".mp4"):
        fn += ".mp4"
    if "/" in fn or "\\" in fn or ".." in fn or len(fn) > 120:
        raise HTTPException(400, "invalid filename")
    path = os.path.realpath(os.path.join(EVAL_CLIPS_DIR, fn))
    if not path.startswith(os.path.realpath(EVAL_CLIPS_DIR) + os.sep):
        raise HTTPException(400, "invalid filename")
    ok = camera.start_recording(path, max_seconds=body.duration_s, fps=12)
    if not ok:
        raise HTTPException(503, "Recording failed (no frame yet?)")
    return {"started": True, "filename": fn, "duration_s": body.duration_s}


@app.post("/api/eval/record/stop")
async def eval_record_stop(_=Depends(require_roles("teacher", "admin"))):
    p = camera.stop_recording()
    return {"stopped": True, "path": p}


@app.get("/api/eval/record/status")
async def eval_record_status(_=Depends(require_roles("teacher", "admin"))):
    return camera.recording_status()


@app.get("/api/eval/clips")
async def eval_list_clips(_=Depends(require_roles("teacher", "admin"))):
    labels = _read_labels_csv()
    out = []
    for fn in sorted(os.listdir(EVAL_CLIPS_DIR)):
        if not fn.endswith(".mp4"):
            continue
        p = os.path.join(EVAL_CLIPS_DIR, fn)
        out.append({
            "filename":     fn,
            "size_bytes":   os.path.getsize(p),
            "modified":     int(os.path.getmtime(p)),
            "url":          f"/eval_clips/{fn}",
            "truth_label":  labels.get(fn),
        })
    return out


class EvalLabelBody(BaseModel):
    truth_label: str


@app.post("/api/eval/clips/{filename}/label")
async def eval_label_clip(filename: str, body: EvalLabelBody,
                          _=Depends(require_roles("teacher", "admin"))):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "invalid filename")
    if body.truth_label not in ALLOWED_LABELS:
        raise HTTPException(400, f"label must be one of {sorted(ALLOWED_LABELS)}")
    if not os.path.exists(os.path.join(EVAL_CLIPS_DIR, filename)):
        raise HTTPException(404, "clip not found")
    labels = _read_labels_csv()
    labels[filename] = body.truth_label
    _write_labels_csv(labels)
    return {"saved": True, "filename": filename, "truth_label": body.truth_label}


@app.delete("/api/eval/clips/{filename}")
async def eval_delete_clip(filename: str,
                           _=Depends(require_roles("teacher", "admin"))):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "invalid filename")
    p = os.path.join(EVAL_CLIPS_DIR, filename)
    if os.path.exists(p):
        os.remove(p)
    labels = _read_labels_csv()
    if labels.pop(filename, None) is not None:
        _write_labels_csv(labels)
    return {"deleted": True}


@app.post("/api/eval/run")
async def eval_run(_=Depends(require_roles("teacher", "admin"))):
    """Run the evaluation harness. Writes eval/last_run.json and returns it.
       NOTE: stops the live camera if it's running, since the runner spawns
       its own CameraProcessor per clip and uses the same webcam index."""
    runner = os.path.join(EVAL_DIR, "run_eval.py")
    if not os.path.exists(runner):
        raise HTTPException(404, "edge-agent eval runner not found")
    if not _read_labels_csv():
        raise HTTPException(400, "no labeled clips — record some and assign labels first")
    # Pause the live camera for the duration of the eval
    was_running = camera.is_running
    if was_running:
        camera.stop()
    import subprocess, json as _json
    try:
        out = subprocess.check_output(
            ["python", runner, "--json"],
            cwd=EVAL_DIR, stderr=subprocess.STDOUT, timeout=600,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, e.output.decode("utf-8", errors="replace"))
    finally:
        if was_running:
            camera.start()
    if os.path.exists(EVAL_RESULTS):
        with open(EVAL_RESULTS) as f:
            return _json.load(f)
    return {"output": out.decode("utf-8", errors="replace")}


@app.get("/api/eval/results")
async def eval_results(_=Depends(require_roles("teacher", "admin"))):
    """Latest eval results JSON, or empty stub if never run."""
    import json as _json
    if os.path.exists(EVAL_RESULTS):
        with open(EVAL_RESULTS) as f:
            return _json.load(f)
    return {"never_run": True}


# ── Eval page route ──────────────────────────────────────────────────────────

# ── Demo, audit, and system health APIs ───────────────────────────────────────

@app.get("/api/demo/config")
async def demo_config_get(_=Depends(require_roles("admin"))):
    return {
        "enabled": _demo_enabled(),
        "camera_count": _demo_camera_count(),
    }


@app.post("/api/demo/config")
async def demo_config_set(body: DemoModeBody,
                          token_payload=Depends(require_roles("admin"))):
    count = body.camera_count if body.camera_count is not None else _demo_camera_count()
    count = max(1, min(int(count), 64))
    db.set_config("demo_mode_enabled", "1" if body.enabled else "0")
    db.set_config("demo_camera_count", str(count))
    _audit("demo.config", token_payload, "demo", "mode", json.dumps({
        "enabled": body.enabled,
        "camera_count": count,
    }))
    return {"enabled": body.enabled, "camera_count": count}


@app.get("/api/audit/recent")
async def audit_recent(limit: int = 80, _=Depends(require_roles("admin"))):
    return db.get_audit_log(limit)


@app.get("/api/system/health")
async def system_health(_=Depends(require_roles("admin"))):
    media = _media_summary()
    cams = await cameras_health(_)
    return {
        "status": "ok",
        "demo_mode": _demo_enabled(),
        "uptime_s": round(time.time() - _STARTED_AT) if "_STARTED_AT" in globals() else 0,
        "camera_summary": cams.get("summary"),
        **media,
    }


@app.get("/eval")
async def page_eval():             return serve_html()


# ── Health endpoint (for monitoring + uptime checks) ──────────────────────────

_STARTED_AT = time.time()


@app.get("/api/health")
async def health():
    """Liveness + readiness probe. Returns 200 always; payload tells you
       what's actually working so an external uptime monitor can alert
       on degraded state without false-positive 5xxs."""
    conn = db.get_db()
    try:
        last_inc = conn.execute(
            "SELECT MAX(timestamp) AS ts FROM bullying_incidents"
        ).fetchone()
        last_incident = last_inc["ts"] if last_inc else None
    except Exception:
        last_incident = None
    try:
        n_students = conn.execute(
            "SELECT COUNT(*) FROM students WHERE role='student'"
        ).fetchone()[0]
    except Exception:
        n_students = -1

    return {
        "status":         "ok",
        "uptime_s":       round(time.time() - _STARTED_AT),
        "demo_mode":      _demo_enabled(),
        "camera_running": camera.is_running,
        "exam_mode":      camera.exam_mode,
        "recording":      camera.is_recording(),
        "n_students":     n_students,
        "last_incident":  last_incident,
        "feature_flags":  dict(FEATURE_FLAGS),
    }


# ── SPA catch-all (must be last) ──────────────────────────────────────────────

@app.get("/{full_path:path}")
async def spa_catchall(full_path: str):
    """Serve the SPA for any unmatched GET route (fixes browser-direct-navigation 404s)."""
    return serve_html()
