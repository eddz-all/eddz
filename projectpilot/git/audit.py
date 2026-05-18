from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from projectpilot.git.inspector import inspect_repository
from projectpilot.models.audit_log import AuditEntry
from projectpilot.models.operation_plan import OperationResult
from projectpilot.utils.shell import run_git

SUMMARY_LIMIT = 500


def audit_log_path(repo_path: Path) -> Path:
    status = inspect_repository(repo_path)
    ensure_audit_is_git_excluded(status.repo_path)
    audit_dir = status.repo_path / ".projectpilot" / "audit"
    return audit_dir / "git-operations.jsonl"


def build_audit_entry(result: OperationResult) -> AuditEntry:
    return AuditEntry(
        timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
        operation=result.operation,
        risk=result.plan.risk,
        command=result.plan.command,
        success=result.success,
        repo_path=str(result.after_status.repo_path),
        branch=result.after_status.branch,
        before_commit=result.before_status.commit,
        after_commit=result.after_status.commit,
        before_clean=result.before_status.is_clean,
        after_clean=result.after_status.is_clean,
        stdout_summary=summarize_output(result.stdout),
        stderr_summary=summarize_output(result.stderr),
    )


def write_audit_entry(result: OperationResult) -> AuditEntry:
    entry = build_audit_entry(result)
    path = audit_log_path(result.after_status.repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    return entry


def read_audit_entries(
    repo_path: Path,
    limit: int = 20,
    operation: str | None = None,
) -> list[AuditEntry]:
    path = audit_log_path(repo_path)
    if not path.exists():
        return []

    entries: list[AuditEntry] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = AuditEntry.from_dict(json.loads(line))
            except json.JSONDecodeError:
                continue
            if operation and entry.operation != operation:
                continue
            entries.append(entry)

    safe_limit = max(1, min(limit, 100))
    return entries[-safe_limit:][::-1]


def summarize_output(text: str) -> str:
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines())
    if len(compact) <= SUMMARY_LIMIT:
        return compact
    return compact[: SUMMARY_LIMIT - 3] + "..."


def ensure_audit_is_git_excluded(repo_path: Path) -> None:
    exclude_path = Path(run_git(["rev-parse", "--git-path", "info/exclude"], cwd=repo_path).stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = repo_path / exclude_path
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    ignore_rule = ".projectpilot/audit/"
    if ignore_rule in existing.splitlines():
        return
    with exclude_path.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(ignore_rule + "\n")
