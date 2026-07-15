from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_python_module_help() -> None:
    project_root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "builder", "--help"]

    completed = subprocess.run(
        command,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Usage:" in completed.stdout
    assert "Stardew Valley offline data builder." in completed.stdout
