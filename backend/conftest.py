"""Pytest configuration for the Primnox backend.

The backend modules import each other by bare name (`from logger import
get_logger`), which only works when `backend/` itself is on `sys.path`. Adding
it here means the suite runs from the repo root as well as from `backend/`.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
