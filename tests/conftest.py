from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
SRC_PATH = str(SRC_DIR)

if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)
