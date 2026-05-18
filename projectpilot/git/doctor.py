from __future__ import annotations

from pathlib import Path

from projectpilot.git.analyzer import analyze_status
from projectpilot.git.audit import read_audit_entries
from projectpilot.git.inspector import inspect_repository
from projectpilot.git.operation_planner import (
    build_add_plan,
    build_commit_operation_plan,
    build_pull_operation_plan,
    build_push_operation_plan,
)
from projectpilot.models.audit_log import AuditEntry
from projectpilot.models.doctor import DoctorReport
from projectpilot.models.git_status import GitStatus


def build_doctor_report(path: Path) -> DoctorReport:
    status = inspect_repository(path)
    analysis = analyze_status(status)
    add_plan = build_add_plan(status.repo_path)
    commit_plan = build_commit_operation_plan(status.repo_path)
    push_plan = build_push_operation_plan(status.repo_path)
    pull_plan = build_pull_operation_plan(status.repo_path)
    audit_entries = read_audit_entries(status.repo_path, limit=1)
    last_audit = audit_entries[0] if audit_entries else None
    findings = build_findings(status, last_audit)
    health = determine_health(status, analysis.risk.level)

    return DoctorReport(
        repo_path=str(status.repo_path),
        health=health,
        risk=analysis.risk.level,
        branch=status.branch,
        upstream=status.upstream,
        is_clean=status.is_clean,
        ahead=status.ahead,
        behind=status.behind,
        findings=findings,
        recommended_next_step=recommend_next_step(status),
        last_audit_operation=last_audit.operation if last_audit else None,
        can_add=add_plan.allowed,
        can_commit=commit_plan.allowed,
        can_push=push_plan.allowed,
        can_pull=pull_plan.allowed,
    )


def determine_health(status: GitStatus, risk: str) -> str:
    if status.state != "normal" or status.conflicted_files or is_diverged(status):
        return "blocked"
    if status.behind > 0 and not status.is_clean:
        return "blocked"
    if (
        status.is_clean
        and status.upstream
        and status.remotes
        and status.ahead == 0
        and status.behind == 0
        and risk == "low"
    ):
        return "healthy"
    return "attention"


def build_findings(status: GitStatus, last_audit: AuditEntry | None) -> list[str]:
    findings: list[str] = []

    if status.state != "normal":
        findings.append(f"Repository is in a {status.state} state.")
    if status.conflicted_files:
        findings.append(f"There are {len(status.conflicted_files)} conflicted file(s).")
    if not status.remotes:
        findings.append("No Git remote is configured.")
    if not status.upstream:
        findings.append("Current branch has no upstream branch configured.")

    if status.is_clean:
        findings.append("Working tree is clean.")
    else:
        parts = []
        if status.staged_files:
            parts.append(f"{len(status.staged_files)} staged")
        if status.unstaged_files:
            parts.append(f"{len(status.unstaged_files)} unstaged")
        if status.untracked_files:
            parts.append(f"{len(status.untracked_files)} untracked")
        findings.append("Working tree is dirty: " + ", ".join(parts) + ".")

    if is_diverged(status):
        findings.append(f"Local and upstream branches have diverged: ahead {status.ahead}, behind {status.behind}.")
    elif status.ahead > 0:
        findings.append(f"Local branch is ahead of upstream by {status.ahead} commit(s).")
    elif status.behind > 0:
        findings.append(f"Local branch is behind upstream by {status.behind} commit(s).")
    elif status.upstream:
        findings.append("Branch is aligned with upstream.")

    if last_audit:
        audit_status = "success" if last_audit.success else "failed"
        findings.append(f"Recent ProjectPilot operation: {last_audit.operation} {audit_status} at {last_audit.timestamp}.")
    else:
        findings.append("No recent ProjectPilot operation recorded.")

    return findings


def recommend_next_step(status: GitStatus) -> str:
    if status.conflicted_files:
        return "Resolve conflicts before running more Git operations."
    if status.state != "normal":
        return f"Finish or abort the current {status.state} operation."
    if is_diverged(status):
        return "Inspect history and resolve divergence before push or pull."
    if not status.is_clean:
        return "Run projectpilot git commit-plan to review and prepare local changes."
    if status.behind > 0:
        return "Run projectpilot git pull --apply if the pull plan looks correct."
    if status.ahead > 0:
        return "Run projectpilot git push --apply if the push plan looks correct."
    if not status.upstream or not status.remotes:
        return "Configure a remote and upstream before using push or pull."
    return "No Git action needed right now."


def is_diverged(status: GitStatus) -> bool:
    return status.ahead > 0 and status.behind > 0
