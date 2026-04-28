"""Edge-agent entry point.

Run from this directory:
    python run.py
"""

from pathlib import Path

import uvicorn


HERE = Path(__file__).resolve().parent


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        app_dir=str(HERE / "backend"),
    )
