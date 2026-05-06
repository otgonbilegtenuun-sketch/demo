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
frontend/   Legacy local single-page dashboard
web/        Next.js + TypeScript dashboard
eval/       Ground-truth clip labeling and detector evaluation
```

## Next.js frontend

The new frontend lives in `web/` and talks to the local FastAPI edge backend.

```bash
npm install --prefix apps/edge-agent/web
npm run dev --prefix apps/edge-agent/web
```

By default it expects the backend at `http://127.0.0.1:8080`. Override this with:

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8080
MERGEN_BACKEND_ORIGIN=http://127.0.0.1:8080
```

From the repository root, Windows users can launch both services with:

```powershell
.\start_edge_agent_next.ps1
```

Runtime data such as `classroom.db`, clips, uploads, photos, model weights, and
eval videos are intentionally ignored by git.
