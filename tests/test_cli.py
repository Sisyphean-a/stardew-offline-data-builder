from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from builder.cli import app

runner = CliRunner()


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


def test_build_help_exposes_only_official_inputs() -> None:
    result = runner.invoke(app, ["build", "--help"])

    assert result.exit_code == 0
    assert "--game-dir" in result.stdout
    assert "--unpacked-dir" in result.stdout
    assert "--community-data" not in result.stdout
