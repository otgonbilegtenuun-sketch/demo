# Mergen AI

Edge-first school camera monitoring prototype.

Current version: `v0.1 Edge Demo`.

## Repository Layout

```text
apps/
  edge-agent/       Python/FastAPI camera AI app that runs inside a school
  cloud-api/        Future cloud metadata API
  web-dashboard/    Future Next.js cloud dashboard
  mobile-app/       Future mobile client
packages/
  shared-types/     Future shared API contracts
  shared-ui/        Future shared UI package
infra/              Deployment and Docker assets
docs/               Architecture, hardware, privacy, and versioning notes
```

## Run The Current App

```bash
pip install -r requirements.txt
python run.py
```

Open `http://localhost:8080`.

## Production Direction

Keep camera AI in the school edge agent. Send metadata to the cloud by default,
not raw classroom video. Build the cloud dashboard separately in
`apps/web-dashboard` when the edge flows are validated with real footage.
