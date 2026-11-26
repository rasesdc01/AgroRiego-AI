"""
AgroRiego AI — Unified Local Server Launcher
Initializes/verifies SQLite DB and starts FastAPI + Dashboard on http://127.0.0.1:8000
"""

import os
import sys
import threading
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.database.seed import seed_all
from scripts.tinkercad_live_sync import run_sync_loop


if __name__ == "__main__":
    seed_all()
    if "--no-bridge" not in sys.argv and os.getenv("AGRORIEGO_DISABLE_BRIDGE") != "1":
        bridge_thread = threading.Thread(target=run_sync_loop, daemon=True)
        bridge_thread.start()
    host = os.getenv("AGRORIEGO_HOST", "127.0.0.1")
    port = int(os.getenv("AGRORIEGO_PORT", "8000"))
    print(f"Starting AgroRiego AI at http://{host}:{port}")
    uvicorn.run("backend.api.main:app", host=host, port=port, reload=False)
