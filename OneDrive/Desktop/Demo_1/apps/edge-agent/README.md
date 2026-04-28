# Edge Agent

The edge agent is the school-local application. It owns camera streams,
AI inference, local incident clips, attendance, safety alerts, and the local
review dashboard.

## Run

From the repository root:

```bash
python run.py
```

From this directory:

```bash
python run.py
```

## Structure

```text
backend/    FastAPI API, camera processor, detectors, SQLite access
frontend/   Local single-page dashboard
eval/       Ground-truth clip labeling and detector evaluation
```

Runtime data such as `classroom.db`, clips, uploads, photos, model weights, and
eval videos are intentionally ignored by git.
