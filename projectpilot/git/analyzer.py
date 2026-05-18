from __future__ import annotations

from projectpilot.models.analysis import GitAnalysis
from projectpilot.models.git_status import GitStatus
from projectpilot.models.risk import RiskAssessment


def analyze_status(status: GitStatus) -> GitAnalysis:
    is_dirty = not status.is_clean
    has_upstream = status.upstream is not None
    is_ahead = status.ahead > 0
    is_behind = status.behind > 0
    is_diverged = is_ahead and is_behind
    needs_commit = bool(status.staged_files or status.unstaged_files or status.untracked_files)
    can_pull = has_upstream and not is_dirty and is_behind and status.state == "normal"
    can_push = has_upstream and is_ahead and not is_diverged and status.state == "normal"
    warnings = build_warnings(status, has_upstream, is_diverged)
    risk = assess_risk(status, has_upstream, is_diverged)
    explanation = build_explanation(status, has_upstream, is_dirty, is_ahead, is_behind, is_diverged)

    return GitAnalysis(
        is_dirty=is_dirty,
        has_upstream=has_upstream,
        is_ahead=is_ahead,
        is_behind=is_behind,
        is_diverged=is_diverged,
        needs_commit=needs_commit,
        can_pull=can_pull,
        can_push=can_push,
        risk=risk,
        explanation=explanation,
        warnings=warnings,
    )


def assess_risk(status: GitStatus, has_upstream: bool, is_diverged: bool) -> RiskAssessment:
    reasons: list[str] = []
    blocked_operations: list[str] = []
    allowed_operations = ["status", "diff", "log", "fetch", "report"]

    if status.state != "normal":
        reasons.append(f"Repository is in a {status.state} state.")
        blocked_operations.extend(["pull", "push", "reset", "clean"])
    if status.conflicted_files:
        reasons.append("There are conflicted files that must be resolved first.")
        blocked_operations.extend(["pull", "push", "commit"])
    if not has_upstream:
        reasons.append("The current branch has no upstream branch configured.")
        blocked_operations.extend(["pull", "push"])
    if is_diverged:
        reasons.append("Local and upstream branches have both moved; pulling or pushing needs extra care.")
        blocked_operations.extend(["push"])
    if status.unstaged_files:
        reasons.append("There are unstaged changes in the working tree.")
    if status.untracked_files:
        reasons.append("There are untracked files that may or may not belong in the commit.")

    blocked_operations = sorted(set(blocked_operations))

    if status.state != "normal" or status.conflicted_files or is_diverged:
        level = "high"
    elif status.unstaged_files or status.untracked_files or not has_upstream:
        level = "medium"
    else:
        level = "low"

    if not reasons:
        reasons.append("No immediate Git risks were detected.")

    return RiskAssessment(
        level=level,
        reasons=reasons,
        blocked_operations=blocked_operations,
        allowed_operations=allowed_operations,
    )


def build_warnings(status: GitStatus, has_upstream: bool, is_diverged: bool) -> list[str]:
    warnings: list[str] = []
    if status.state != "normal":
        warnings.append(f"Finish the current {status.state} operation before starting new Git operations.")
    if status.conflicted_files:
        warnings.append("Resolve conflicts before committing, pulling, or pushing.")
    if not has_upstream:
        warnings.append("Set an upstream branch before relying on pull or push suggestions.")
    if is_diverged:
        warnings.append("The branch has diverged from upstream; inspect history before integrating changes.")
    if status.untracked_files:
        warnings.append("Review untracked files before adding everything.")
    return warnings


def build_explanation(
    status: GitStatus,
    has_upstream: bool,
    is_dirty: bool,
    is_ahead: bool,
    is_behind: bool,
    is_diverged: bool,
) -> str:
    lines: list[str] = []
    branch = status.branch or "detached HEAD"
    lines.append(f"Current repository is on {branch}.")

    if has_upstream:
        lines.append(f"It tracks {status.upstream}.")
    else:
        lines.append("This branch does not have an upstream branch configured.")

    if status.state != "normal":
        lines.append(f"The repository is currently in a {status.state} state.")

    if status.conflicted_files:
        lines.append(f"There are {len(status.conflicted_files)} conflicted file(s).")

    if is_dirty:
        change_parts = []
        if status.staged_files:
            change_parts.append(f"{len(status.staged_files)} staged")
        if status.unstaged_files:
            change_parts.append(f"{len(status.unstaged_files)} unstaged")
        if status.untracked_files:
            change_parts.append(f"{len(status.untracked_files)} untracked")
        lines.append("The working tree is not clean: " + ", ".join(change_parts) + ".")
    else:
        lines.append("The working tree is clean.")

    if is_diverged:
        lines.append(f"The branch has diverged: local is ahead by {status.ahead} and behind by {status.behind}.")
    elif is_ahead:
        lines.append(f"The branch is ahead of upstream by {status.ahead} commit(s).")
    elif is_behind:
        lines.append(f"The branch is behind upstream by {status.behind} commit(s).")
    elif has_upstream:
        lines.append("The branch is aligned with upstream.")

    return " ".join(lines)
