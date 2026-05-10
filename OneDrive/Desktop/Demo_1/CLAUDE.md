# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the server

```bash
python run.py          # starts on :8080 (auto-finds next free port if busy)
python run.py 9000     # explicit port
```

Starts the FastAPI server with uvicorn auto-reload. Entry point: `apps/edge-agent/backend/app.py` as `app:app`.

## Installing dependencies

```bash
pip install -r apps/edge-agent/requirements.txt
```

All runtime deps (`deepface`, `ultralytics`, `mediapipe`, etc.) are in the requirements file.

## Validation before push

```bash
python -c "import ast; files=['apps/edge-agent/backend/app.py','apps/edge-agent/backend/camera.py','apps/edge-agent/backend/database.py','apps/edge-agent/backend/bullying_detector.py','apps/edge-agent/backend/pose_analyzer.py','apps/edge-agent/backend/safety_detector.py','apps/edge-agent/eval/run_eval.py']; [ast.parse(open(f, encoding='utf-8').read()) for f in files]; print('py OK')"
node -e "new Function(require('fs').readFileSync('apps/edge-agent/frontend/app.js','utf8')); console.log('js OK')"
```

Push only after validation passes and the user explicitly asks.

## Demo accounts

Seeded automatically on first run:

| Username   | Password     | Role    |
|------------|--------------|---------|
| `admin`    | `admin123`   | admin   |
| `teacher1` | `teacher123` | teacher |
| `parent1`  | `parent123`  | parent  |

## Product scope

Mergen AI is an edge-first classroom attendance, safety, and incident-review prototype.

> Automated attendance + seat-based classroom analytics + exam deterrence + incident replay for teacher review.

Do not claim that the AI proves cheating, bullying, violence, or student intent. Every AI incident is a **review prompt**, not a verdict.

## Architecture

Single-page application. All page routes (`/`, `/monitor`, `/dashboard/teacher`, etc.) return `apps/edge-agent/frontend/index.html`. Client-side routing via `history.pushState` in `app.js`. All backend endpoints are prefixed `/api/`.

### Backend (`apps/edge-agent/backend/`)

- **`app.py`** — FastAPI app. Mounts frontend as `/static`, photos/clips as static assets. All API routes. Auth uses custom HMAC-signed token (7-day expiry), not a JWT library. Camera callbacks wired here to decouple camera logic from DB writes.
- **`camera.py`** — `CameraProcessor` runs in a background thread. AI models at different cadences:
  - **MediaPipe Face Landmarker** (`face_landmarker.task`) — every frame; face bboxes + gaze (attentive/sideways)
  - **YuNet** (`face_detection_yunet_2023mar.onnx`) — optional better face detector for small/profile faces; auto-downloaded
  - **DeepFace ArcFace** — recognition every 3s (live) or 5s (file playback); generates 512-dim embeddings
  - **YOLOv8 nano** (`yolov8n.pt`) — every 15 frames in exam mode; phones (class 67) + persons (class 0)
  - Callbacks: `on_recognition`, `on_unknown_face`, `on_phone_suspect`, `on_uniform`, `on_bullying_incident`, `on_safety_incident`, `on_seat_attendance`
- **`database.py`** — SQLite with WAL mode + `busy_timeout=5000`. Per-thread connections via `threading.local`. Face embeddings stored as raw `BLOB` (numpy `float32` bytes). Recognition threshold: **0.38** cosine similarity.
- **`bullying_detector.py`** — Heuristics: close pair, proximity cluster, sudden motion, distress face, pose cues.
- **`safety_detector.py`** — Heuristics: fall/collapse, running, restricted-zone, after-hours, unattended object, camera tamper.
- **`pose_analyzer.py`** — Optional MediaPipe Pose for bullying signal enrichment.
- **`appearance_tracker.py`** — Person re-ID via color histograms for ceiling-mode seat tracking.
- **`log_setup.py`** — Centralized logger configuration.

### Frontend (`apps/edge-agent/frontend/`)

- **`index.html`** — All page `<div>` elements (hidden by default) + inline SVG sprite.
- **`app.js`** — All JS in one file. Global state in object `S`. i18n: Mongolian (`mn`) and English (`en`). `showPage(path)` activates the correct div + calls its `init*()` function.
- **`style.css`**, `nav/nav.css`, `pages/pages.css`, `hero/hero.css`, `layout/layout.css` — CSS split by concern.

### Key data flows

- **Enrollment**: Browser captures 3 webcam photos → `POST /api/enroll` → ArcFace embedding averaged → stored in `students.face_embedding`.
- **Live monitoring**: `GET /video_feed` streams MJPEG. Camera thread annotates frames with bboxes, names, attention status. Recognition runs every 3s.
- **Video file upload**: `POST /api/video/upload` saves file, starts `camera.start_from_file()`. Non-batch mode: ~5fps analysis with frame skipping for 1x playback speed (heavy detectors disabled). Batch mode: full pipeline as fast as possible.
- **Exam mode**: `POST /api/exam_mode`. Enables YOLOv8 phone detection + sideways-gaze + unknown-person alerts.
- **Dashboards**: Poll `/api/attendance/today`, `/api/attention/history`, `/api/alerts/recent` every 2.5-5 seconds.

### Database tables

`students`, `attendance`, `attention_log`, `alerts`, `uniform_log`, `classroom_seats`, `app_config`, `audit_log`, `bullying_incidents`, `users`. Tables have `camera_id` column for future multi-camera support.

### Role-based access

Three roles: `teacher`, `parent`, `admin`. Enforced client-side in `showPage()` and server-side via `require_roles()`. Admin controls `/monitor`; parents restricted to `/dashboard/parent`.

## Video file playback architecture

Non-batch file playback only runs **MediaPipe + DeepFace** (no YOLO, safety, bullying, or pose). Frame skipping: processes ~5 frames/sec from a 30fps video. Wall-clock pacing keeps 1x speed. Batch mode runs the full pipeline without frame delay.

Recognition uses `ssd` → `skip` backend fallback on pre-cropped face regions. The `opencv` (Haar cascade) backend is skipped because it fails on MediaPipe crops.

## Version control policy

- Current version: `v0.1 Edge Demo`. `main` = working demo branch.
- Commit source files only. Never commit `classroom.db`, generated clips, photos, uploads, model files (`.onnx`, `.pt`), or eval video clips.
- `.gitignore` covers `*.db`, `photos/`, `uploads/`, `clips/`, `__pycache__/`, model files.

## Hardware targets

| Tier | CPU | GPU | RAM | Capacity |
|------|-----|-----|-----|----------|
| Minimum | i5-12th gen / Ryzen 5 5600 | None (CPU only) | 16GB | 1 camera, ~2-3 AI FPS |
| Recommended | i5-13400 / Ryzen 5 7600 | RTX 3060 12GB | 32GB | 1-3 cameras, real-time |
| Comfortable | i7-13700 / Ryzen 7 7700 | RTX 4070 | 32-64GB | 8-12 cameras |

Primary bottleneck is GPU inference (YOLO, ArcFace). Without GPU, all AI runs on CPU — expect slower processing. Camera AI streams should be 640x360 or 720p at 3-5 FPS, not full 1080p/4K.
