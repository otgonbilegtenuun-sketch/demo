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
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import threading

import database as db
from camera import (
    FEATURE_FLAGS,
    CameraProcessor,
    process_enrollment_image,
    set_clips_dir,
)
from database import get_all_students, delete_student

# ── Auth helpers ──────────────────────────────────────────────────────────────

_SECRET = "mergen-ai-secret-2024-xk9"


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

# ── App & camera ──────────────────────────────────────────────────────────────

_BASE = os.path.dirname(os.path.abspath(__file__))

app    = FastAPI(title="Mergen AI")
camera = CameraProcessor()

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

app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
app.mount("/clips",  StaticFiles(directory=CLIPS_DIR),  name="clips")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
# NOTE: /icons is also registered as an explicit route below (more reload-friendly)


def serve_html():
    return FileResponse(HTML_FILE)


@app.get("/icons/{filename}")
async def serve_icon(filename: str):
    """Serve GIF icons from frontend/icons/ — explicit route avoids mount restart issues."""
    import mimetypes
    path = os.path.join(ICONS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, detail=f"Icon not found: {filename}")
    mime, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=mime or "image/gif")


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
            db.save_alert(student["id"], student["name"], "suspicious_glance")
            print(f"[ALERT] {student['name']} suspicious glance (sim={sim:.3f})")

    return matched_indices


def _on_unknown_face(face_idx: int):
    """Called in exam mode when a face cannot be matched to any enrolled student."""
    global _last_unknown_alert
    now = time.time()
    if now - _last_unknown_alert < _UNKNOWN_COOLDOWN:
        return
    _last_unknown_alert = now
    db.save_unknown_alert("unknown_person")
    print(f"[ALERT] Unknown person detected in exam mode (face slot #{face_idx})")


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


def _on_phone_suspect(name: str):
    """Called when down-gaze threshold triggers a phone-use suspicion."""
    conn = db.get_db()
    row  = conn.execute("SELECT id FROM students WHERE name=?", (name,)).fetchone()
    if row:
        db.save_alert(row["id"], name, "phone_detected")
    else:
        first = db.get_first_student()
        if first:
            db.save_alert(first["id"], name, "phone_detected")
    print(f"[ALERT] {name} phone/down-gaze detected")


def _save_review_incident(event: dict, label: str = "INCIDENT") -> int:
    iid = db.save_bullying_incident(
        primary_signal     = event.get("primary_signal", "unknown"),
        concurrent_signals = event.get("concurrent_signals", []),
        involved_names     = event.get("involved_names", []),
        score              = event.get("score", 0.0),
        duration_s         = event.get("duration_s", 0.0),
    )
    print(f"[{label}] flag #{iid}: {event.get('primary_signal')} "
          f"score={event.get('score')} names={event.get('involved_names')}")
    center_ts = float(event.get("timestamp", time.time()))
    threading.Thread(
        target=_dump_incident_clip,
        args=(iid, center_ts, float(event.get("clip_pre_s", 5.0)),
              float(event.get("clip_post_s", 10.0))),
        daemon=True,
    ).start()
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
        print(f"[BULLYING] save error: {e}")


def _on_safety_incident(event: dict):
    """Safety signals are review prompts only; never automatic verdicts."""
    try:
        _save_review_incident(event, "SAFETY")
    except Exception as e:
        print(f"[SAFETY] save error: {e}")


def _dump_incident_clip(incident_id: int, center_ts: float,
                        pre_s: float = 5.0, post_s: float = 10.0):
    """Background: write the ring-buffer clip and update the DB row."""
    try:
        path = camera.dump_clip(center_ts, pre_s=pre_s, post_s=post_s)
        if not path:
            return
        # Rename to use the incident id so the URL is stable
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
        print(f"[BULLYING] clip #{incident_id} → {url}")
    except Exception as e:
        print(f"[BULLYING] clip dump error #{incident_id}: {e}")


camera.on_recognition       = _on_faces_recognized
camera.on_unknown_face      = _on_unknown_face
camera.on_phone_suspect     = _on_phone_suspect
camera.on_uniform           = _on_uniform
camera.on_bullying_incident = _on_bullying_incident
camera.on_safety_incident   = _on_safety_incident


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
    zones = []
    for z in out.get("restricted_zones", []):
        try:
            zones.append({
                "name": str(z.get("name") or "restricted"),
                "x1": int(z["x1"]), "y1": int(z["y1"]),
                "x2": int(z["x2"]), "y2": int(z["y2"]),
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
    print("[Mergen AI] Database ready")

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
                print(f"[purge] retention={days}d rows={counts}")
            except Exception as e:
                print(f"[purge] error: {e}")
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
async def page_admin():            return serve_html()


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


@app.post("/api/auth/login")
async def auth_login(body: LoginBody):
    user = db.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(401, detail="Нэвтрэх нэр эсвэл нууц үг буруу байна")
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
    if db.username_exists(body.username):
        raise HTTPException(400, detail="Энэ нэвтрэх нэр аль хэдийн бүртгэлтэй байна")
    signup_role = body.role if body.role in ("teacher", "parent", "admin") else "parent"
    uid = db.create_user(
        username=body.username,
        password=body.password,
        role=signup_role,
        student_id=body.student_id if signup_role == "parent" else None,
        full_name=body.full_name,
    )
    user = db.get_user_by_id(uid)
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
async def auth_me(token_payload=Depends(_get_token_optional)):
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
async def video_feed():
    async def _stream():
        _ph = None  # cached placeholder frame bytes
        while True:
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
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                data = buf.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + data
                + b"\r\n"
            )
            await asyncio.sleep(0.066)

    return StreamingResponse(
        _stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store"},
    )


# ── Camera control ────────────────────────────────────────────────────────────

@app.post("/api/camera/start")
async def camera_start():
    ok = camera.start()
    if not ok:
        raise HTTPException(503, detail="Камер нээгдсэнгүй. Өөр програм ашиглаж байна уу?")
    return {"status": "started"}


@app.post("/api/camera/stop")
async def camera_stop():
    camera.stop()
    return {"status": "stopped"}


@app.post("/api/test/recognize")
async def test_recognize(file: UploadFile = File(...)):
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
    emb = process_enrollment_image(b64)
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


@app.post("/api/video/upload")
async def video_upload(file: UploadFile = File(...)):
    """Upload a video file and process it as if it were a live camera feed."""
    save_path = os.path.join(UPLOADS_DIR, file.filename or "upload.mp4")
    content   = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    ok = camera.start_from_file(save_path)
    if not ok:
        raise HTTPException(400, "Видео файл нээгдсэнгүй. Формат дэмжигдэж байна уу?")
    return {"status": "started", "filename": file.filename}


@app.get("/api/camera/status")
async def camera_status():
    faces = camera.recognized_faces
    return {
        "running":    camera.is_running,
        "exam_mode":  camera.exam_mode,
        "face_count": len(faces),
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


# ── Exam mode ─────────────────────────────────────────────────────────────────

class ExamModeBody(BaseModel):
    enabled: bool


# ── Person lock ───────────────────────────────────────────────────────────────

class LockBody(BaseModel):
    nx: float   # normalised x (0–1)
    ny: float   # normalised y (0–1)


@app.get("/api/exam_mode")
async def get_exam_mode():
    return {"enabled": camera.exam_mode}


@app.post("/api/exam_mode")
async def set_exam_mode(body: ExamModeBody):
    camera.exam_mode = body.enabled
    return {"enabled": camera.exam_mode}


@app.post("/api/lock")
async def lock_person(body: LockBody):
    tid = camera.lock_at_point(body.nx, body.ny)
    return {"locked": tid is not None, "track_id": tid}


@app.post("/api/unlock")
async def unlock_person():
    camera.unlock()
    return {"locked": False}


# ── Enrollment ────────────────────────────────────────────────────────────────

class EnrollBody(BaseModel):
    name:       str
    class_name: str
    role:       str = "student"
    images:     List[str]


@app.post("/api/enroll")
async def enroll(body: EnrollBody):
    embeddings = []
    student_photos_dir = os.path.join(PHOTOS_DIR, body.name)
    os.makedirs(student_photos_dir, exist_ok=True)

    for i, img in enumerate(body.images):
        e = process_enrollment_image(img)
        if e is not None:
            embeddings.append(e)
            try:
                img_data  = img.split(",")[1] if "," in img else img
                img_bytes = base64.b64decode(img_data)
                with open(os.path.join(student_photos_dir, f"{i+1}.jpg"), "wb") as f:
                    f.write(img_bytes)
            except Exception as ex:
                print(f"[enroll] photo save error: {ex}")

    if not embeddings:
        raise HTTPException(400, "Нүүр илрүүлэгдсэнгүй. Гэрэлтэй газарт зураг авна уу.")
    avg_emb    = np.mean(embeddings, axis=0).astype(np.float32)
    student_id = db.save_student(body.name, body.class_name, body.role, avg_emb)
    return {"success": True, "id": student_id, "name": body.name, "captures": len(embeddings),
            "photo_url": f"/photos/{body.name}/1.jpg"}


# ── Attendance & analytics ────────────────────────────────────────────────────

@app.get("/api/attendance/today")
async def attendance_today():
    return db.get_today_attendance()


@app.get("/api/attendance/stats")
async def attendance_stats():
    return db.get_admin_stats()


@app.get("/api/attention/history")
async def attention_history():
    return db.get_attention_history()


@app.get("/api/parent/student")
async def parent_student(token_payload=Depends(_get_token_optional)):
    student_id = None
    if token_payload and token_payload.get("role") == "parent":
        user = db.get_user_by_id(token_payload["id"])
        if user:
            student_id = user.get("student_id")

    if student_id:
        conn = db.get_db()
        row = conn.execute(
            "SELECT id, name, class_name FROM students WHERE id=?", (student_id,)
        ).fetchone()
        s = dict(row) if row else None
    else:
        s = db.get_first_student()

    if not s:
        raise HTTPException(404, "Бүртгэлтэй оюутан байхгүй")
    today = db.get_today_attendance()
    info  = next((x for x in today if x["id"] == s["id"]), None)
    return {"student": s, "today": info}


@app.get("/api/parent/history")
async def parent_history(days: int = 14, token_payload=Depends(_get_token_optional)):
    student_id = None
    if token_payload and token_payload.get("role") == "parent":
        user = db.get_user_by_id(token_payload["id"])
        if user:
            student_id = user.get("student_id")

    if not student_id:
        first = db.get_first_student()
        student_id = first["id"] if first else None

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
async def list_students():
    return get_all_students()


@app.delete("/api/students/{student_id}")
async def remove_student(student_id: int):
    ok = delete_student(student_id)
    if not ok:
        raise HTTPException(404, "Оюутан олдсонгүй")
    return {"success": True, "deleted_id": student_id}


# ── Alerts ────────────────────────────────────────────────────────────────────

@app.get("/api/alerts/recent")
async def alerts_recent(since_id: int = 0):
    return db.get_recent_alerts(since_id=since_id)


class PhoneBody(BaseModel):
    student_name: Optional[str] = None


@app.post("/api/alerts/phone")
async def phone_alert(body: PhoneBody = None):
    s = db.get_first_student()
    if not s:
        raise HTTPException(404, "Бүртгэлтэй оюутан байхгүй")
    name = (body.student_name if body and body.student_name else s["name"])
    db.save_alert(s["id"], name, "phone_detected")
    return {"success": True, "student": name}


# ── Bullying / incident flagging ──────────────────────────────────────────────

class BullyingReviewBody(BaseModel):
    outcome: str   # confirmed | false_positive | inconclusive


class BullyingConfigBody(BaseModel):
    enabled: bool


@app.get("/api/bullying/recent")
async def bullying_recent(since_id: int = 0, limit: int = 50):
    return db.get_recent_bullying_incidents(since_id=since_id, limit=limit)


@app.get("/api/bullying/stats")
async def bullying_stats():
    return db.get_bullying_stats()


@app.post("/api/bullying/{incident_id}/review")
async def bullying_review(incident_id: int, body: BullyingReviewBody):
    if body.outcome not in ("confirmed", "false_positive", "inconclusive"):
        raise HTTPException(400, "Invalid outcome")
    ok = db.review_bullying_incident(incident_id, body.outcome)
    if not ok:
        raise HTTPException(404, "Incident not found")
    return {"success": True}


@app.get("/api/bullying/config")
async def bullying_config_get():
    return {"enabled": camera._bullying.enabled}


@app.post("/api/bullying/config")
async def bullying_config_set(body: BullyingConfigBody):
    camera._bullying.enabled = body.enabled
    return {"enabled": camera._bullying.enabled}


# ── Uniform ───────────────────────────────────────────────────────────────────

@app.get("/api/uniform/today")
async def uniform_today():
    return db.get_today_uniform()


@app.get("/api/uniform/stats")
async def uniform_stats():
    return db.get_uniform_stats()


@app.get("/api/uniform/weekly")
async def uniform_weekly():
    return db.get_uniform_weekly()


# ── Reset ─────────────────────────────────────────────────────────────────────

@app.post("/api/reset")
async def reset_demo():
    db.reset_today_data()
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
async def seats_get(class_name: str = "Class A"):
    return db.get_seat_map(class_name)


@app.post("/api/seats")
async def seats_set(body: SeatMapBody):
    db.replace_seat_map(body.class_name, [s.dict() for s in body.seats])
    seats = _push_seat_map_to_camera(body.class_name)
    return {"saved": len(seats), "seats": seats}


@app.delete("/api/seats")
async def seats_clear(class_name: str = "Class A"):
    db.clear_seat_map(class_name)
    _push_seat_map_to_camera(class_name)
    return {"cleared": True}


@app.get("/api/seats/occupancy")
async def seats_occupancy():
    return camera.get_seat_occupancy_snapshot()


@app.get("/api/snapshot")
async def snapshot():
    """Return the latest annotated camera frame as JPEG — used by the seat editor."""
    frame = camera.get_frame()
    if frame is None:
        raise HTTPException(503, "Камер ажиллахгүй байна")
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(500, "encode failed")
    from fastapi.responses import Response
    return Response(content=buf.tobytes(), media_type="image/jpeg")


# ── Per-student behavior profile ──────────────────────────────────────────────

class StudentProfileBody(BaseModel):
    attention_disabled: Optional[bool] = None
    distress_disabled:  Optional[bool] = None
    profile_note:       Optional[str]  = None


def _push_attention_disabled_to_camera():
    camera.set_attention_disabled_ids(db.get_attention_disabled_ids())


@app.get("/api/students/{student_id}/profile")
async def student_profile_get(student_id: int):
    p = db.get_student_profile(student_id)
    if not p:
        raise HTTPException(404, "Оюутан олдсонгүй")
    return p


@app.patch("/api/students/{student_id}/profile")
async def student_profile_patch(student_id: int, body: StudentProfileBody):
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
async def admin_flags_get():
    return dict(FEATURE_FLAGS)


@app.post("/api/admin/flags")
async def admin_flags_set(body: FeatureFlagsBody):
    for k, v in body.dict(exclude_none=True).items():
        if k in FEATURE_FLAGS:
            FEATURE_FLAGS[k] = bool(v)
            db.set_config(f"flag.{k}", "1" if v else "0")
    return dict(FEATURE_FLAGS)


@app.get("/api/admin/retention")
async def admin_retention_get():
    days = int(db.get_config("retention_days", "30"))
    return {"days": days}


@app.post("/api/admin/retention")
async def admin_retention_set(body: RetentionBody):
    if body.days < 1 or body.days > 3650:
        raise HTTPException(400, "days must be 1..3650")
    db.set_config("retention_days", str(body.days))
    return {"days": body.days}


@app.post("/api/admin/purge")
async def admin_purge_now():
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
        print(f"[purge] clip cleanup error: {e}")
    return {"days": days, "rows_deleted": counts, "clips_deleted": purged_clips}


@app.get("/api/safety/config")
async def safety_config_get():
    return _load_safety_config()


@app.post("/api/safety/config")
async def safety_config_set(body: SafetyConfigBody):
    return _save_safety_config(body.dict())


@app.post("/api/clips/manual")
async def manual_clip_capture():
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
    return {"success": True, "incident_id": iid}


# ── Threshold-tuning suggestion (read-only) ───────────────────────────────────

@app.get("/api/bullying/threshold-suggestion")
async def bullying_threshold_suggestion():
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

EVAL_DIR        = os.path.join(_BASE, "..", "eval")
EVAL_CLIPS_DIR  = os.path.join(EVAL_DIR, "clips")
EVAL_LABELS_CSV = os.path.join(EVAL_DIR, "labels.csv")
EVAL_RESULTS    = os.path.join(EVAL_DIR, "last_run.json")
os.makedirs(EVAL_CLIPS_DIR, exist_ok=True)

ALLOWED_LABELS = {"fight", "crowd_bully", "normal", "crowd_normal", "note_passing"}

# Mount eval clips so the frontend can preview them
app.mount("/eval_clips", StaticFiles(directory=EVAL_CLIPS_DIR), name="eval_clips")


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
async def eval_record_start(body: EvalRecordBody):
    if not camera.is_running:
        raise HTTPException(503, "Камер ажиллахгүй байна. Эхлүүлнэ үү.")
    if body.duration_s < 5 or body.duration_s > 600:
        raise HTTPException(400, "duration_s must be 5..600")
    fn = body.filename or f"clip_{int(time.time())}.mp4"
    if not fn.endswith(".mp4"):
        fn += ".mp4"
    if "/" in fn or "\\" in fn or ".." in fn:
        raise HTTPException(400, "invalid filename")
    path = os.path.join(EVAL_CLIPS_DIR, fn)
    ok = camera.start_recording(path, max_seconds=body.duration_s, fps=12)
    if not ok:
        raise HTTPException(503, "Recording failed (no frame yet?)")
    return {"started": True, "filename": fn, "duration_s": body.duration_s}


@app.post("/api/eval/record/stop")
async def eval_record_stop():
    p = camera.stop_recording()
    return {"stopped": True, "path": p}


@app.get("/api/eval/record/status")
async def eval_record_status():
    return camera.recording_status()


@app.get("/api/eval/clips")
async def eval_list_clips():
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
async def eval_label_clip(filename: str, body: EvalLabelBody):
    if "/" in filename or "\\" in filename:
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
async def eval_delete_clip(filename: str):
    if "/" in filename or "\\" in filename:
        raise HTTPException(400, "invalid filename")
    p = os.path.join(EVAL_CLIPS_DIR, filename)
    if os.path.exists(p):
        os.remove(p)
    labels = _read_labels_csv()
    if labels.pop(filename, None) is not None:
        _write_labels_csv(labels)
    return {"deleted": True}


@app.post("/api/eval/run")
async def eval_run():
    """Run the evaluation harness. Writes eval/last_run.json and returns it.
       NOTE: stops the live camera if it's running, since the runner spawns
       its own CameraProcessor per clip and uses the same webcam index."""
    runner = os.path.join(EVAL_DIR, "run_eval.py")
    if not os.path.exists(runner):
        raise HTTPException(404, "eval/run_eval.py not found")
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
async def eval_results():
    """Latest eval results JSON, or empty stub if never run."""
    import json as _json
    if os.path.exists(EVAL_RESULTS):
        with open(EVAL_RESULTS) as f:
            return _json.load(f)
    return {"never_run": True}


# ── Eval page route ──────────────────────────────────────────────────────────

@app.get("/eval")
async def page_eval():             return serve_html()


# ── SPA catch-all (must be last) ──────────────────────────────────────────────

@app.get("/{full_path:path}")
async def spa_catchall(full_path: str):
    """Serve the SPA for any unmatched GET route (fixes browser-direct-navigation 404s)."""
    return serve_html()
