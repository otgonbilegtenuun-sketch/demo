"""Root entry point for the school edge agent.

Run from the repository root:
    python run.py
"""

from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
EDGE_BACKEND = ROOT / "apps" / "edge-agent" / "backend"


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        app_dir=str(EDGE_BACKEND),
    )
