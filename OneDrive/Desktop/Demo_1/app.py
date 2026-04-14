"""
app.py — FastAPI application for EduGuard AI Classroom Monitor.

All page routes return the same index.html (SPA with JS routing).
API routes are prefixed with /api/.
"""

import asyncio
import os
import time
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import database as db
from camera import CameraProcessor, process_enrollment_image
from database import get_all_students, delete_student

# ── App & camera ──────────────────────────────────────────────────────────────

app    = FastAPI(title="EduGuard AI")
camera = CameraProcessor()

HTML_FILE = os.path.join(os.path.dirname(__file__), "templates", "index.html")


def serve_html():
    return FileResponse(HTML_FILE)


# ── Recognition callback (camera thread, every 2 s) ──────────────────────────

_last_unknown_alert: float = 0.0
_UNKNOWN_COOLDOWN    = 10.0   # minimum seconds between unknown-face alerts


def _on_face_recognized(face_idx: int, embedding: np.ndarray, attentive: bool, sideways: bool) -> bool:
    """Called for every detected face every 2 s. Returns True if a known student matched."""
    student, sim = db.find_matching_student(embedding)
    if student:
        camera.set_face_name(face_idx, student["name"])
        db.update_attendance(student["id"], attentive)
        db.log_attention(student["id"], student["name"], attentive)
        if camera.exam_mode and sideways:
            db.save_alert(student["id"], student["name"], "suspicious_glance")
            print(f"[ALERT] {student['name']} suspicious glance (sim={sim:.3f})")
        return True
    # Don't wipe the sticky name — let FACE_NAME_TTL expire it naturally
    return False


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


camera.on_recognition   = _on_face_recognized
camera.on_unknown_face  = _on_unknown_face
camera.on_phone_suspect = _on_phone_suspect
camera.on_uniform       = _on_uniform


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    db.init_db()
    print("[EduGuard] Database ready")


@app.on_event("shutdown")
async def _shutdown():
    camera.stop()


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def page_home():             return serve_html()

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
                    cv2.putText(ph, "EduGuard AI", (195, 210),
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
            await asyncio.sleep(0.033)

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


@app.get("/api/exam_mode")
async def get_exam_mode():
    return {"enabled": camera.exam_mode}


@app.post("/api/exam_mode")
async def set_exam_mode(body: ExamModeBody):
    camera.exam_mode = body.enabled
    return {"enabled": camera.exam_mode}


# ── Enrollment ────────────────────────────────────────────────────────────────

class EnrollBody(BaseModel):
    name:       str
    class_name: str
    role:       str = "student"
    images:     List[str]


@app.post("/api/enroll")
async def enroll(body: EnrollBody):
    embeddings = [
        e for img in body.images
        if (e := process_enrollment_image(img)) is not None
    ]
    if not embeddings:
        raise HTTPException(400, "Нүүр илрүүлэгдсэнгүй. Гэрэлтэй газарт зураг авна уу.")
    avg_emb    = np.mean(embeddings, axis=0).astype(np.float32)
    student_id = db.save_student(body.name, body.class_name, body.role, avg_emb)
    return {"success": True, "id": student_id, "name": body.name, "captures": len(embeddings)}


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
async def parent_student():
    s = db.get_first_student()
    if not s:
        raise HTTPException(404, "Бүртгэлтэй оюутан байхгүй")
    today = db.get_today_attendance()
    info  = next((x for x in today if x["id"] == s["id"]), None)
    return {"student": s, "today": info}


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
