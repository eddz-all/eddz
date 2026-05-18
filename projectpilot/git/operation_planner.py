from __future__ import annotations

from pathlib import Path

from projectpilot.git.commit_planner import build_commit_plan
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
