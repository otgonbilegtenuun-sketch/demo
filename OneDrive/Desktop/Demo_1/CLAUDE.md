# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
python run.py
```

Starts the FastAPI server at **http://localhost:8080** with uvicorn auto-reload. The entry point runs `backend/app.py` as `app:app` with `app_dir="backend"`.

## Installing dependencies

```bash
pip install -r requirements.txt
pip install deepface insightface ultralytics
```

`deepface`, `insightface`, and `ultralytics` (YOLOv8) are used at runtime but not listed in `requirements.txt`.

## Demo accounts

Seeded automatically on first run:

| Username   | Password     | Role    |
|------------|--------------|---------|
| `admin`    | `admin123`   | admin   |
| `teacher1` | `teacher123` | teacher |
| `parent1`  | `parent123`  | parent  |

## Architecture

This is a **single-page application** where all page routes (`/`, `/monitor`, `/dashboard/teacher`, etc.) return the same `frontend/index.html`. Client-side routing is handled in `frontend/app.js` via `history.pushState`. All backend endpoints are prefixed `/api/`.

### Backend (`backend/`)

- **`app.py`** — FastAPI app. Mounts `frontend/` as `/static` and `photos/` as `/photos`. Defines all API routes and wires camera callbacks. Auth uses a custom HMAC-signed token (7-day expiry), **not** a standard JWT library.
- **`camera.py`** — `CameraProcessor` runs in a background thread. Three AI models operate at different cadences:
  - **MediaPipe Face Landmarker** (`face_landmarker.task`) — every frame; provides face bboxes and gaze (attentive/sideways) via landmark geometry
  - **DeepFace ArcFace** — every 2 seconds; generates 512-dim embeddings for recognition
  - **YOLOv8 nano** (`yolov8n.pt`) — every 15 frames in exam mode only; detects phones (class 67) and tracks persons (class 0)
  - Callbacks (`on_recognition`, `on_unknown_face`, `on_phone_suspect`, `on_uniform`) are set by `app.py` to keep camera logic decoupled from DB writes.
- **`database.py`** — SQLite with WAL mode. Per-thread connections via `threading.local`. Tables: `students`, `attendance`, `attention_log`, `alerts`, `uniform_log`, `users`. Face embeddings stored as raw `BLOB` (numpy `float32` bytes). Recognition uses cosine similarity with a threshold of 0.50.

### Frontend (`frontend/`)

- **`index.html`** — Single HTML file containing all page `<div>` elements (hidden by default) and inline SVG sprite.
- **`app.js`** — All JS in one file (~1500 lines). Global state in object `S`. i18n dictionary `I18N` supports Mongolian (`mn`) and English (`en`). `showPage(path)` activates the correct `<div>` and calls its `init*()` function.
- **`style.css`**, `nav/nav.css`, `pages/pages.css`, `hero/hero.css` — CSS split by concern.

### Key data flows

- **Enrollment**: Browser captures 3 webcam photos → `POST /api/enroll` → `process_enrollment_image()` runs ArcFace → average embedding stored in `students.face_embedding`.
- **Live monitoring**: `GET /video_feed` streams MJPEG at ~30fps. Camera thread annotates frames with bboxes, names, attention status, and phone indicators. Recognition runs every 2s and writes attendance/alerts to SQLite.
- **Exam mode**: Toggled via `POST /api/exam_mode`. Enables YOLOv8 phone detection, sideways-gaze alerts, and unknown-person alerts. Camera thread checks `camera.exam_mode` flag directly.
- **Dashboards**: Teacher/parent/admin dashboards poll `/api/attendance/today`, `/api/attention/history`, `/api/uniform/*`, and `/api/alerts/recent` every 5 seconds.

### Role-based access

Three roles: `teacher`, `parent`, `admin`. Enforced client-side in `showPage()` and server-side where sensitive. Admin role gets access to `/monitor` (camera control); parents are restricted to `/dashboard/parent`.
