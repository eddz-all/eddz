from __future__ import annotations

from pathlib import Path

from projectpilot.git.audit import write_audit_entry
from projectpilot.git.inspector import inspect_repository
from projectpilot.git.operation_planner import (
    build_add_plan,
    build_cherry_pick_operation_plan,
    build_commit_operation_plan,
    build_merge_operation_plan,
    build_pull_operation_plan,
    build_push_operation_plan,
    build_revert_operation_plan,
    build_stash_operation_plan,
    build_switch_operation_plan,
    build_tag_operation_plan,
)
from projectpilot.models.operation_plan import OperationPlan, OperationResult
from projectpilot.utils.shell import run_git


def run_add(
    path: Path,
    include_paths: list[str] | None = None,
    force_include_paths: list[str] | None = None,
) -> OperationResult:
    plan = build_add_plan(path, include_paths=include_paths, force_include_paths=force_include_paths)
    return execute_plan(plan)


def run_commit(path: Path, message: str | None = None) -> OperationResult:
    plan = build_commit_operation_plan(path, message=message)
    return execute_plan(plan)


def run_push(path: Path) -> OperationResult:
    plan = build_push_operation_plan(path)
    return execute_plan(plan)


def run_pull(path: Path) -> OperationResult:
    plan = build_pull_operation_plan(path)
    return execute_plan(plan)


def run_switch(path: Path, target: str, create: bool = False, start_point: str | None = None) -> OperationResult:
    plan = build_switch_operation_plan(path, target=target, create=create, start_point=start_point)
    return execute_plan(plan)


def run_merge(path: Path, source: str) -> OperationResult:
    plan = build_merge_operation_plan(path, source=source)
    return execute_plan(plan)


def run_stash(path: Path, message: str | None = None, include_untracked: bool = False) -> OperationResult:
    plan = build_stash_operation_plan(path, message=message, include_untracked=include_untracked)
    return execute_plan(plan)


def run_tag(path: Path, name: str, message: str | None = None) -> OperationResult:
    plan = build_tag_operation_plan(path, name=name, message=message)
    return execute_plan(plan)


def run_revert(path: Path, revision: str, commit: bool = False) -> OperationResult:
    plan = build_revert_operation_plan(path, revision=revision, commit=commit)
    return execute_plan(plan)


def run_cherry_pick(path: Path, revision: str, commit: bool = False) -> OperationResult:
    plan = build_cherry_pick_operation_plan(path, revision=revision, commit=commit)
    return execute_plan(plan)


def execute_plan(plan: OperationPlan) -> OperationResult:
    before_status = inspect_repository(Path(plan.repo_path))

    if not plan.allowed:
        raise RuntimeError("; ".join(plan.blockers) or f"{plan.operation} operation is not allowed.")

    result = run_git(plan.command[1:], cwd=Path(plan.repo_path))
    after_status = inspect_repository(Path(plan.repo_path))

    operation_result = OperationResult(
        operation=plan.operation,
        success=result.returncode == 0,
        stdout=result.stdout,
        stderr=result.stderr,
        before_status=before_status,
        after_status=after_status,
        plan=plan,
    )
    write_audit_entry(operation_result)
    return operation_result
