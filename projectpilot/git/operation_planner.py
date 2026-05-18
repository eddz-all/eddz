from __future__ import annotations

from pathlib import Path

from projectpilot.git.commit_planner import build_commit_plan, suggest_commit_message
from projectpilot.git.inspector import inspect_repository
from projectpilot.models.commit_plan import CommitPlanItem
from projectpilot.models.operation_plan import OperationPlan


def build_add_plan(
    path: Path,
    include_paths: list[str] | None = None,
    force_include_paths: list[str] | None = None,
) -> OperationPlan:
    commit_plan = build_commit_plan(path)
    include_request = set(include_paths or [])
    force_request = set(force_include_paths or [])
    items_by_path = {item.path: item for item in [*commit_plan.include, *commit_plan.review, *commit_plan.exclude]}
    blockers: list[str] = []
    warnings = list(commit_plan.warnings)
    planned_paths: list[str] = []
    review_paths = [item.path for item in commit_plan.review]
    excluded_paths = [item.path for item in commit_plan.exclude]

    for requested in sorted(include_request | force_request):
        if requested not in items_by_path:
            blockers.append(f"Requested path is not changed or not visible to Git: {requested}")

    planned_paths.extend(addable_paths(commit_plan.include))

    for item in commit_plan.review:
        if item.path in include_request:
            planned_paths.append(item.path)
        else:
            warnings.append(f"Review file not staged by default: {item.path}")

    for item in commit_plan.exclude:
        if item.path in force_request:
            planned_paths.append(item.path)
            warnings.append(f"Force-including excluded path: {item.path}")
        else:
            warnings.append(f"Excluded file not staged by default: {item.path}")

    if not planned_paths and not blockers:
        blockers.append("No files are eligible to add.")

    command = ["git", "add", "--", *planned_paths] if planned_paths else []
    allowed = bool(planned_paths) and not blockers
    reason = build_add_reason(planned_paths, include_request, force_request)

    return OperationPlan(
        operation="add",
        repo_path=commit_plan.repo_path,
        risk="medium",
        allowed=allowed,
        requires_apply=True,
        command=command,
        reason=reason,
        blockers=blockers,
        warnings=warnings,
        planned_paths=planned_paths,
        review_paths=review_paths,
        excluded_paths=excluded_paths,
    )


def addable_paths(items: list[CommitPlanItem]) -> list[str]:
    return [item.path for item in items if item.status != "staged"]


def build_add_reason(planned_paths: list[str], include_request: set[str], force_request: set[str]) -> str:
    if not planned_paths:
        return "No files will be staged."
    if include_request or force_request:
        return "Stage default include files plus explicitly requested review or excluded files."
    return "Stage files that ProjectPilot classified as safe to include."


def build_commit_operation_plan(path: Path, message: str | None = None) -> OperationPlan:
    status = inspect_repository(path)
    commit_plan = build_commit_plan(path)
    staged_include = staged_items(commit_plan.include)
    staged_review = staged_items(commit_plan.review)
    staged_exclude = staged_items(commit_plan.exclude)
    staged_paths = [item.path for item in [*staged_include, *staged_review, *staged_exclude]]
    blockers: list[str] = []
    warnings: list[str] = []

    if status.state != "normal":
        blockers.append(f"Repository is in a {status.state} state.")
    if status.conflicted_files:
        blockers.append("Conflicted files must be resolved before committing.")
    if not staged_paths:
        blockers.append("No staged files are available to commit.")
    if staged_exclude:
        blockers.append("Excluded-category files are staged; unstage them before committing.")
    if status.unstaged_files:
        warnings.append("Unstaged changes will not be included in this commit.")
    if status.untracked_files:
        warnings.append("Untracked files will not be included in this commit.")
    for item in staged_review:
        warnings.append(f"Review-category file is staged: {item.path}")

    suggested_message = clean_message(message) or suggest_commit_message(staged_include, staged_review)
    if staged_paths and not suggested_message:
        blockers.append("A commit message is required.")

    command = ["git", "commit", "-m", suggested_message] if suggested_message and staged_paths else []

    return OperationPlan(
        operation="commit",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=bool(staged_paths) and not blockers,
        requires_apply=True,
        command=command,
        reason=build_commit_reason(staged_paths, suggested_message),
        suggested_message=suggested_message,
        blockers=blockers,
        warnings=warnings,
        planned_paths=staged_paths,
        review_paths=[item.path for item in staged_review],
        excluded_paths=[item.path for item in staged_exclude],
    )


def staged_items(items: list[CommitPlanItem]) -> list[CommitPlanItem]:
    return [item for item in items if item.status == "staged"]


def clean_message(message: str | None) -> str | None:
    if message is None:
        return None
    cleaned = message.strip()
    return cleaned or None


def build_commit_reason(staged_paths: list[str], suggested_message: str | None) -> str:
    if not staged_paths:
        return "No commit will be created because no files are staged."
    if suggested_message:
        return "Create a commit from currently staged files only."
    return "A commit message is needed before a commit can be created."
