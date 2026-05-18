from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from projectpilot.git.inspector import NotGitRepositoryError, inspect_repository
from projectpilot.utils.shell import run_git


def detect_local_git_status(project_path: str) -> dict[str, Any]:
    """Return a backend-friendly Git status snapshot for a local project."""
    try:
        target_path = Path(project_path).expanduser()
        if not target_path.exists():
            return _failure("path_not_found", "The target path does not exist.")

        status = inspect_repository(target_path)
        last_commit = _last_commit(status.repo_path)

        return {
            "success": True,
            "repo_path": str(status.repo_path),
            "branch": status.branch,
            "upstream": status.upstream,
            "remote_url": _select_remote_url(status.upstream, status.remotes),
            "ahead": status.ahead,
            "behind": status.behind,
            "has_uncommitted_changes": not status.is_clean,
            "is_clean": status.is_clean,
            "state": status.state,
            "staged_count": len(status.staged_files),
            "unstaged_count": len(status.unstaged_files),
            "untracked_count": len(status.untracked_files),
            "conflicted_count": len(status.conflicted_files),
            "last_commit": last_commit,
        }
    except NotGitRepositoryError:
        return _failure("not_git_repository", "The target path is not a Git repository.")
    except FileNotFoundError as exc:
        if exc.filename == "git":
            return _failure("command_not_found", "Git command was not found.")
        return _failure("unknown_error", str(exc))
    except Exception as exc:
        return _failure("unknown_error", str(exc))


def detect_local_environment(project_path: str | None = None) -> dict[str, Any]:
    """Return a backend-friendly environment snapshot for the local machine."""
    try:
        disk_path = Path(project_path).expanduser() if project_path else Path.cwd()
        if project_path and not disk_path.exists():
            return _failure("path_not_found", "The target path does not exist.")
        if disk_path.is_file():
            disk_path = disk_path.parent

        commands = {
            "git": _version_command(["git", "--version"], strip_prefix="git version "),
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "python3": _version_command(["python3", "--version"], strip_prefix="Python "),
            "node": _version_command(["node", "--version"], strip_prefix="v"),
            "docker": _version_command(["docker", "--version"], strip_prefix="Docker version "),
        }
        docker_installed = shutil.which("docker") is not None
        docker_running = _command_succeeds(["docker", "info"], timeout=5) if docker_installed else False

        return {
            "success": True,
            "os": platform.system(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "node_version": commands["node"],
            "docker_installed": docker_installed,
            "docker_running": docker_running,
            "cuda_version": _detect_cuda_version(),
            "disk_usage": _disk_usage_percent(disk_path),
            "raw_data": {
                "project_path": str(disk_path.resolve()),
                "commands": commands,
            },
        }
    except Exception as exc:
        return _failure("unknown_error", str(exc))


def _failure(error_type: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": error_type,
        "message": message,
    }


def _last_commit(repo_path: Path) -> str | None:
    result = run_git(["log", "-1", "--pretty=%h %s"], cwd=repo_path, check=False)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _select_remote_url(upstream: str | None, remotes: dict[str, list[str]]) -> str | None:
    candidates: list[str] = []
    if upstream and "/" in upstream:
        candidates.append(upstream.split("/", 1)[0])
    candidates.append("origin")
    candidates.extend(remote for remote in remotes if remote not in candidates)

    for remote in candidates:
        urls = remotes.get(remote, [])
        if urls:
            return urls[0]
    return None


def _version_command(args: list[str], strip_prefix: str = "") -> str | None:
    try:
        result = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0 or not output:
        return None
    first_line = output.splitlines()[0].strip()
    if strip_prefix and first_line.startswith(strip_prefix):
        return first_line[len(strip_prefix) :].strip()
    return first_line


def _command_succeeds(args: list[str], timeout: int) -> bool:
    try:
        result = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _detect_cuda_version() -> str | None:
    version = _version_command(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
    )
    if version:
        return version.splitlines()[0].strip()
    return None


def _disk_usage_percent(path: Path) -> str:
    usage = shutil.disk_usage(path)
    if usage.total == 0:
        return "0%"
    return f"{round((usage.used / usage.total) * 100)}%"
