# Technology Stack

## Current `v0.1 Edge Demo`

| Layer | Choice | Reason |
|---|---|---|
| Camera AI | Python | Best ecosystem for OpenCV, MediaPipe, YOLO, DeepFace |
| Local API | FastAPI | Lightweight, async-friendly, easy to deploy on an edge PC |
| Local dashboard | Static HTML/CSS/JS | Fast prototype, no build step |
| Local DB | SQLite | Simple single-edge deployment |
| Evaluation | Python scripts + UI wrapper | Keeps detector validation close to camera code |

## Production Direction

| Layer | Recommended |
|---|---|
| School edge agent | Python + FastAPI |
| Camera workers | Python processes, one worker group per camera batch |
| Edge DB | SQLite for small installs, PostgreSQL for multi-camera schools |
| Cloud API | FastAPI or NestJS |
| Cloud DB | PostgreSQL |
| Cloud dashboard | Next.js + React + TypeScript |
| Mobile app | React Native later, only after cloud dashboard stabilizes |

## Rule

Do not move camera AI into Next.js. Next.js is for the cloud dashboard. Python
stays responsible for camera capture, model inference, clips, and local edge
control.
