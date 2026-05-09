"""Root entry point for the school edge agent.

Run from the repository root:
    python run.py
"""

from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
EDGE_BACKEND = ROOT / "apps" / "edge-agent" / "backend"


EDGE_FRONTEND = ROOT / "apps" / "edge-agent" / "frontend"


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=[str(EDGE_BACKEND), str(EDGE_FRONTEND)],
        app_dir=str(EDGE_BACKEND),
    )
