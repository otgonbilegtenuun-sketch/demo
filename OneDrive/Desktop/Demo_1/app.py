"""
app.py — FastAPI application for EduGuard AI Classroom Monitor.

All page routes return the same index.html (SPA with JS routing).
API routes are prefixed with /api/.
"""

import os
from typing import List, Optional

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

def _on_face_recognized(embedding: np.ndarray, attentive: bool, sideways: bool):
    student, sim = db.find_matching_student(embedding)
    if student:
        camera.set_last_name(student["name"])
        db.update_attendance(student["id"], attentive)
        db.log_attention(student["id"], student["name"], attentive)
        if camera.exam_mode and sideways:
            db.save_alert(student["id"], student["name"], "suspicious_glance")
            print(f"[ALERT] {student['name']} suspicious glance (sim={sim:.3f})")
    else:
        camera.set_last_name(None)


def _on_phone_suspect(name: str):
    """Called when down-gaze threshold triggers a phone-use suspicion."""
    conn = db.get_db()
    row  = conn.execute("SELECT id FROM students WHERE name=?", (name,)).fetchone()
    if row:
        db.save_alert(row["id"], name, "phone_detected")
    else:
        # Fallback to first enrolled student if name not matched yet
        first = db.get_first_student()
        if first:
            db.save_alert(first["id"], name, "phone_detected")
    print(f"[ALERT] {name} phone/down-gaze detected")


camera.on_recognition   = _on_face_recognized
camera.on_phone_suspect = _on_phone_suspect


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
    return StreamingResponse(
        camera.generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
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


# ── Reset ─────────────────────────────────────────────────────────────────────

@app.post("/api/reset")
async def reset_demo():
    db.reset_today_data()
    return {"success": True}
