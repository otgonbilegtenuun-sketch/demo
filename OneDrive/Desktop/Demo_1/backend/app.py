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
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database as db
from camera import CameraProcessor, process_enrollment_image
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
os.makedirs(PHOTOS_DIR,  exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(ICONS_DIR,   exist_ok=True)

app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
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
        db.update_attendance(student["id"], attentive)
        db.log_attention(student["id"], student["name"], attentive)
        if camera.exam_mode and sideways:
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


camera.on_recognition   = _on_faces_recognized
camera.on_unknown_face  = _on_unknown_face
camera.on_phone_suspect = _on_phone_suspect
camera.on_uniform       = _on_uniform


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    db.init_db()
    print("[Mergen AI] Database ready")


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


# ── SPA catch-all (must be last) ──────────────────────────────────────────────

@app.get("/{full_path:path}")
async def spa_catchall(full_path: str):
    """Serve the SPA for any unmatched GET route (fixes browser-direct-navigation 404s)."""
    return serve_html()
