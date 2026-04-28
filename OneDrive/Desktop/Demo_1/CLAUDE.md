# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
python run.py
```

Starts the FastAPI server at **http://localhost:8080** with uvicorn auto-reload. The root entry point runs `apps/edge-agent/backend/app.py` as `app:app`.

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

## Product scope and current features

Mergen AI is an edge-first classroom attendance, safety, and incident-review prototype. Position it as:

> Automated attendance + seat-based classroom analytics + exam deterrence + incident replay for teacher review.

Do not claim that the AI proves cheating, bullying, violence, or student intent. Every AI incident is a **review prompt**, not a verdict.

Implemented features:

- Student enrollment with 3-photo face embedding averaging.
- Attendance and attention logging from live camera frames.
- Exam mode with sideways-gaze and optional phone detection.
- Seat-map editor at `/seats`; maps camera pixel rectangles to students.
- Incident review queue at `/incidents`; outcomes are `confirmed`, `false_positive`, and `inconclusive`.
- Incident clip export from the rolling replay buffer.
- Manual "save last 30 seconds" capture from the monitor page.
- Bullying/incident heuristics: close pair, proximity cluster, sudden motion, distress face, optional pose cues.
- Safety heuristics: fall/collapse posture, running/fast movement, restricted-zone entry, after-hours presence, unattended bag-like object, weapon-like object, camera blocked/dark/blurry/stream failure.
- Admin settings at `/admin`: detector flags, retention, restricted-zone JSON, school hours, per-student opt-out profiles, threshold review summary.
- Eval workflow at `/eval`: record clips, label clips, run `apps/edge-agent/eval/run_eval.py`, and view precision/recall/FPR.

## Repository structure

```text
apps/
  edge-agent/       current Python/FastAPI school-local camera AI app
  cloud-api/        future cloud metadata API
  web-dashboard/    future Next.js/React cloud dashboard
  mobile-app/       future mobile client
packages/
  shared-types/     future shared API contracts
  shared-ui/        future shared dashboard UI package
infra/              future deployment/Docker/service files
docs/               architecture, hardware, and versioning notes
scripts/            future maintenance scripts
```

The current working product is `apps/edge-agent`. The root `run.py` exists as a convenience wrapper so `python run.py` still works from the repository root.

## Hardware targets

For a 10-camera pilot, use one central GPU PC and low-resolution RTSP substreams.

Recommended minimum serious setup:

- CPU: Intel i5-12400/i5-13400 or Ryzen 5 5600+
- GPU: RTX 3060 12GB or RTX 4060 8GB
- RAM: 32GB
- Storage: 1TB NVMe, plus HDD/NAS only if retaining many clips
- Network: gigabit LAN with PoE switch
- Camera AI stream: 640x360 or 720p at 3-5 FPS, not full 1080p/4K

Primary bottlenecks:

1. GPU inference: YOLO, ArcFace, optional object/pose/emotion models.
2. CPU video decoding and stream management.
3. Disk only when recording many clips/full video.
4. RAM is usually fine once 32GB is available.

Capacity assumptions:

- CPU-only old office PC: 2-3 cameras with limited detection.
- i5 + RTX 3060/4060 + 32GB: target 8-12 optimized cameras.
- i7 + RTX 4070 + 32GB/64GB: target 15-25 optimized cameras.

The current codebase is still a single-camera `CameraProcessor`. Multi-camera production needs a `CameraManager` that owns one processor per RTSP stream, batches model inference where possible, and tags every event with `camera_id` and `classroom_id`.

## Recommended production stack

Keep this stack for the current prototype:

- Backend: Python + FastAPI + OpenCV.
- ML/runtime: MediaPipe Face Landmarker, DeepFace ArcFace, Ultralytics YOLO.
- Storage: SQLite for prototype/single school edge box.
- Frontend: current static SPA is acceptable for the prototype.

For production:

- Backend: FastAPI service split into API process + camera worker process.
- Queue: `queue.Queue` locally first; Redis/RQ or Celery if multi-process.
- DB: PostgreSQL for school/cloud metadata; SQLite only on a single edge box.
- Frontend: Next.js/React only after the product flows stabilize. Do not migrate now just for style.
- Video: keep raw video/clips on-prem by default; cloud receives metadata only unless explicitly configured.
- Deployment: one edge service per school, systemd/Windows service, rotating logs, health endpoint.

## Version control policy

- Current product version: `v0.1 Edge Demo`.
- Treat `main` as the working demo branch until a separate production branch exists.
- Use semantic-ish demo versions for planning:
  - `v0.1`: local single-camera edge demo.
  - `v0.2`: validated thresholds from real classroom footage.
  - `v0.3`: multi-camera edge server with `camera_id`/`classroom_id`.
  - `v0.4`: cloud metadata sync.
  - `v0.5`: Next.js/React cloud dashboard.
  - `v1.0`: pilot-ready school deployment.
- Commit source files only; do not commit `classroom.db`, generated clips, photos, uploads, model downloads, or eval video clips.
- Use focused commits with clear messages.
- Push only after validation passes and the user explicitly asks for push.
- Validate before pushing:

```bash
python -c "import ast; files=['apps/edge-agent/backend/app.py','apps/edge-agent/backend/camera.py','apps/edge-agent/backend/database.py','apps/edge-agent/backend/bullying_detector.py','apps/edge-agent/backend/pose_analyzer.py','apps/edge-agent/backend/safety_detector.py','apps/edge-agent/eval/run_eval.py']; [ast.parse(open(f, encoding='utf-8').read()) for f in files]; print('py OK')"
node -e "new Function(require('fs').readFileSync('apps/edge-agent/frontend/app.js','utf8')); console.log('js OK')"
python apps/edge-agent/eval/run_eval.py
```

## Architecture

The current edge agent is a **single-page application** where all page routes (`/`, `/monitor`, `/dashboard/teacher`, etc.) return the same `apps/edge-agent/frontend/index.html`. Client-side routing is handled in `apps/edge-agent/frontend/app.js` via `history.pushState`. All backend endpoints are prefixed `/api/`.

### Backend (`apps/edge-agent/backend/`)

- **`app.py`** — FastAPI app. Mounts `apps/edge-agent/frontend/` as `/static` and local photos/clips as static assets. Defines all API routes and wires camera callbacks. Auth uses a custom HMAC-signed token (7-day expiry), **not** a standard JWT library.
- **`camera.py`** — `CameraProcessor` runs in a background thread. Three AI models operate at different cadences:
  - **MediaPipe Face Landmarker** (`face_landmarker.task`) — every frame; provides face bboxes and gaze (attentive/sideways) via landmark geometry
  - **DeepFace ArcFace** — every 2 seconds; generates 512-dim embeddings for recognition
  - **YOLOv8 nano** (`yolov8n.pt`) — every 15 frames in exam mode only; detects phones (class 67) and tracks persons (class 0)
  - Callbacks (`on_recognition`, `on_unknown_face`, `on_phone_suspect`, `on_uniform`) are set by `app.py` to keep camera logic decoupled from DB writes.
- **`database.py`** — SQLite with WAL mode. Per-thread connections via `threading.local`. Tables: `students`, `attendance`, `attention_log`, `alerts`, `uniform_log`, `users`. Face embeddings stored as raw `BLOB` (numpy `float32` bytes). Recognition uses cosine similarity with a threshold of 0.50.

### Frontend (`apps/edge-agent/frontend/`)

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
