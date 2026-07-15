from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_external_command(executable: Path, args: list[str], cwd: Path) -> CommandResult:
    command = build_command(executable, args)
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_command(executable: Path, args: list[str]) -> list[str]:
    if executable.suffix.lower() == ".py":
        return [sys.executable, str(executable), *args]
    return [str(executable), *args]
