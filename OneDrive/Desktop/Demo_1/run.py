"""Root entry point for the school edge agent.

Run from the repository root:
    python run.py [port]
"""

import socket
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
EDGE_BACKEND = ROOT / "apps" / "edge-agent" / "backend"
EDGE_FRONTEND = ROOT / "apps" / "edge-agent" / "frontend"


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _resolve_port(host: str, requested: int) -> int:
    if _port_is_free(host, requested):
        return requested
    print(f"\n[!] Port {requested} is already in use.")
    print(f"    Another Mergen AI instance is probably still running.")
    print(f"    Searching for a free port...")
    for p in range(requested + 1, requested + 20):
        if _port_is_free(host, p):
            print(f"    -> Using port {p} instead. Open http://localhost:{p}\n")
            return p
    print(f"[X] No free port found near {requested}. Close the old process and retry.\n")
    sys.exit(1)


if __name__ == "__main__":
    requested_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    host = "0.0.0.0"
    port = _resolve_port(host, requested_port)
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=[str(EDGE_BACKEND), str(EDGE_FRONTEND)],
        app_dir=str(EDGE_BACKEND),
    )
