from __future__ import annotations

from pathlib import Path

from projectpilot.git.inspector import inspect_repository
from projectpilot.git.operation_planner import build_pull_operation_plan, build_push_operation_plan
from projectpilot.models.git_status import GitStatus
from projectpilot.models.operation_plan import OperationPlan
from projectpilot.models.sync_plan import BlockedOperation, GitSyncPlan


def build_sync_plan(path: Path) -> GitSyncPlan:
    status = inspect_repository(path)
    push_plan = build_push_operation_plan(status.repo_path)
    pull_plan = build_pull_operation_plan(status.repo_path)
    sync_state = determine_sync_state(status)
    working_tree_state = determine_working_tree_state(status)
    recommended_action = recommend_sync_action(status, sync_state, working_tree_state)
    operation_plans = allowed_operation_plans(push_plan, pull_plan)
    blocked_operations = blocked_sync_operations(push_plan, pull_plan)

    return GitSyncPlan(
        repo_path=str(status.repo_path),
        branch=status.branch,
        upstream=status.upstream,
        commit=status.commit,
        risk=sync_risk(status, sync_state, working_tree_state),
        sync_state=sync_state,
        working_tree_state=working_tree_state,
        ahead=status.ahead,
        behind=status.behind,
        can_push=push_plan.allowed,
        can_pull_ff_only=pull_plan.allowed,
        recommended_action=recommended_action,
        explanation=sync_explanation(status, sync_state, working_tree_state),
        operation_plans=operation_plans,
        blocked_operations=blocked_operations,
        next_steps=sync_next_steps(status, recommended_action),
        warnings=[*push_plan.warnings, *pull_plan.warnings],
    )


def determine_sync_state(status: GitStatus) -> str:
    if status.conflicted_files:
        return "conflict"
    if status.state != "normal":
        return "operation_in_progress"
    if not status.upstream:
        return "no_upstream"
    if status.ahead > 0 and status.behind > 0:
        return "diverged"
    if status.ahead > 0:
        return "ahead"
    if status.behind > 0:
        return "behind"
    return "up_to_date"


def determine_working_tree_state(status: GitStatus) -> str:
    if status.conflicted_files:
        return "conflict"
    if status.staged_files or status.unstaged_files or status.untracked_files:
        return "dirty"
    return "clean"


def sync_risk(status: GitStatus, sync_state: str, working_tree_state: str) -> str:
    if status.conflicted_files or status.state != "normal" or sync_state == "diverged":
        return "high"
    if sync_state != "up_to_date" or working_tree_state == "dirty":
        return "medium"
    return "low"


def recommend_sync_action(status: GitStatus, sync_state: str, working_tree_state: str) -> str:
    if sync_state == "conflict":
        return "resolve_conflicts"
    if sync_state == "operation_in_progress":
        return "continue_or_abort_operation"
    if sync_state == "no_upstream":
        return "set_upstream"
    if sync_state == "diverged" and working_tree_state == "dirty":
        return "commit_or_stash_then_choose_merge_or_rebase"
    if sync_state == "diverged":
        return "choose_merge_or_rebase"
    if sync_state == "behind" and working_tree_state == "clean":
        return "pull_ff_only"
    if sync_state == "behind":
        return "commit_or_stash_before_pull"
    if sync_state == "ahead" and working_tree_state == "dirty":
        return "commit_or_stash_before_push"
    if sync_state == "ahead":
        return "push"
    if working_tree_state == "dirty":
        return "review_and_commit_local_changes"
    return "no_action_needed"


def sync_explanation(status: GitStatus, sync_state: str, working_tree_state: str) -> str:
    if sync_state == "no_upstream":
        return "The current branch has no upstream, so ProjectPilot cannot safely push or pull."
    if sync_state == "diverged":
        return "Local and upstream branches both contain unique commits, so push and fast-forward pull are blocked."
    if sync_state == "behind" and working_tree_state == "clean":
        return f"The branch is behind upstream by {status.behind} commit(s), and a fast-forward pull is available."
    if sync_state == "behind":
        return "The branch is behind upstream, but local working tree changes must be protected first."
    if sync_state == "ahead" and working_tree_state == "clean":
        return f"The branch is ahead of upstream by {status.ahead} commit(s), and push is available."
    if sync_state == "ahead":
        return "The branch has local commits, but uncommitted changes should be reviewed before pushing."
    if sync_state == "conflict":
        return "The repository has conflicted files that must be resolved before sync."
    if sync_state == "operation_in_progress":
        return f"The repository is in a {status.state} state and needs to be continued or aborted first."
    if working_tree_state == "dirty":
        return "The branch is aligned with upstream, but the working tree has local changes."
    return "The branch is aligned with upstream and the working tree is clean."


def sync_next_steps(status: GitStatus, recommended_action: str) -> list[str]:
    actions = {
        "resolve_conflicts": ["Resolve conflicts, stage resolved files, then continue the current operation."],
        "continue_or_abort_operation": [f"Finish or abort the current {status.state} operation."],
        "set_upstream": ["Configure a remote upstream before push or pull."],
        "commit_or_stash_then_choose_merge_or_rebase": [
            "Commit or stash local changes.",
            "Fetch remote changes.",
            "Choose merge or rebase after reviewing remote commits.",
        ],
        "choose_merge_or_rebase": ["Review local and upstream commits, then choose merge or rebase."],
        "pull_ff_only": ["Run the approved fast-forward pull plan when ready."],
        "commit_or_stash_before_pull": ["Commit or stash local changes before pulling upstream commits."],
        "commit_or_stash_before_push": ["Review local changes before pushing committed work."],
        "push": ["Run the approved push plan when ready."],
        "review_and_commit_local_changes": ["Review and commit local changes."],
        "no_action_needed": ["No sync action needed right now."],
    }
    return actions[recommended_action]


def allowed_operation_plans(*plans: OperationPlan) -> list[dict]:
    return [plan.to_dict() for plan in plans if plan.allowed]


def blocked_sync_operations(*plans: OperationPlan) -> list[BlockedOperation]:
    blocked: list[BlockedOperation] = []
    for plan in plans:
        if plan.allowed:
            continue
        reason = "; ".join(plan.blockers) or plan.reason
        blocked.append(BlockedOperation(operation=plan.operation, reason=reason))
    return blocked

