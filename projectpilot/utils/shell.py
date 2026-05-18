from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    def __init__(self, result: CommandResult):
        self.result = result
        command = " ".join(result.args)
        message = result.stderr.strip() or result.stdout.strip() or f"Command failed: {command}"
        super().__init__(message)


def run_command(args: list[str], cwd: Path | None = None, check: bool = True) -> CommandResult:
    process = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    result = CommandResult(
        args=args,
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
    )
    if check and result.returncode != 0:
        raise CommandError(result)
    return result


def run_git(args: list[str], cwd: Path, check: bool = True) -> CommandResult:
    return run_command(["git", *args], cwd=cwd, check=check)
