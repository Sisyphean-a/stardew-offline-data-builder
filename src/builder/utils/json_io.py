from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson


def load_json_file(path: Path) -> Any:
    return orjson.loads(path.read_bytes())


def dump_json_file(path: Path, payload: Any) -> None:
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
