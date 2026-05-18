from __future__ import annotations

from pathlib import Path

from projectpilot.git.inspector import inspect_repository
from projectpilot.utils.shell import CommandResult, run_git


def get_diff(path: Path, cached: bool = False, stat: bool = False, name_only: bool = False) -> CommandResult:
    status = inspect_repository(path)
    args = ["diff"]
    if cached:
        args.append("--cached")
    if stat:
        args.append("--stat")
    if name_only:
        args.append("--name-only")
    return run_git(args, cwd=status.repo_path)


def get_log(path: Path, limit: int = 10) -> CommandResult:
    status = inspect_repository(path)
    safe_limit = max(1, min(limit, 100))
    return run_git(
        ["log", "--oneline", "--decorate", "--graph", f"-n{safe_limit}"],
        cwd=status.repo_path,
    )


def run_fetch(path: Path, remote: str | None = None, prune: bool = False) -> tuple[CommandResult, object]:
    status = inspect_repository(path)
    if not status.remotes:
        raise RuntimeError("No Git remotes are configured for this repository.")

    args = ["fetch"]
    if prune:
        args.append("--prune")
    if remote:
        if remote not in status.remotes:
            available = ", ".join(sorted(status.remotes))
            raise RuntimeError(f"Remote '{remote}' is not configured. Available remotes: {available}")
        args.append(remote)

    result = run_git(args, cwd=status.repo_path)
    refreshed_status = inspect_repository(status.repo_path)
    return result, refreshed_status
