# Architecture

Mergen AI should remain edge-first.

```text
Camera -> School Edge Agent -> Local DB / Local Clips
                          -> Cloud API: metadata only
Cloud Dashboard -> Cloud API
Authorized clip review -> temporary request to school edge agent
```

## Current App

`apps/edge-agent` is the current working app:

- Python/FastAPI backend
- OpenCV/MediaPipe/YOLO/DeepFace camera pipeline
- Static local dashboard
- SQLite local storage
- Local clip storage
- Eval workflow for real-footage validation

## Future Apps

- `apps/cloud-api`: receives event metadata and device health from schools.
- `apps/web-dashboard`: Next.js/React SaaS dashboard.
- `apps/mobile-app`: optional parent/admin mobile client.

## Rule

Do not stream every classroom video to the cloud by default. Keep raw video and
clips on-premise unless the school explicitly enables secure cloud clip storage.
