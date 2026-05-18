from __future__ import annotations

from pathlib import Path

from projectpilot.git.audit import write_audit_entry
from projectpilot.git.inspector import inspect_repository
from projectpilot.git.operation_planner import (
    build_add_plan,
    build_commit_operation_plan,
    build_pull_operation_plan,
    build_push_operation_plan,
)
from projectpilot.models.operation_plan import OperationResult
from projectpilot.utils.shell import run_git


def run_add(
    path: Path,
    include_paths: list[str] | None = None,
    force_include_paths: list[str] | None = None,
) -> OperationResult:
    plan = build_add_plan(path, include_paths=include_paths, force_include_paths=force_include_paths)
    before_status = inspect_repository(Path(plan.repo_path))

    if not plan.allowed:
        raise RuntimeError("; ".join(plan.blockers) or "Add operation is not allowed.")

    result = run_git(plan.command[1:], cwd=Path(plan.repo_path))
    after_status = inspect_repository(Path(plan.repo_path))

    operation_result = OperationResult(
        operation="add",
        success=result.returncode == 0,
        stdout=result.stdout,
        stderr=result.stderr,
        before_status=before_status,
        after_status=after_status,
        plan=plan,
    )
    write_audit_entry(operation_result)
    return operation_result


def run_commit(path: Path, message: str | None = None) -> OperationResult:
    plan = build_commit_operation_plan(path, message=message)
    before_status = inspect_repository(Path(plan.repo_path))

    if not plan.allowed:
        raise RuntimeError("; ".join(plan.blockers) or "Commit operation is not allowed.")

    result = run_git(plan.command[1:], cwd=Path(plan.repo_path))
    after_status = inspect_repository(Path(plan.repo_path))

    operation_result = OperationResult(
        operation="commit",
        success=result.returncode == 0,
        stdout=result.stdout,
        stderr=result.stderr,
        before_status=before_status,
        after_status=after_status,
        plan=plan,
    )
    write_audit_entry(operation_result)
    return operation_result


def run_push(path: Path) -> OperationResult:
    plan = build_push_operation_plan(path)
    before_status = inspect_repository(Path(plan.repo_path))

    if not plan.allowed:
        raise RuntimeError("; ".join(plan.blockers) or "Push operation is not allowed.")

    result = run_git(plan.command[1:], cwd=Path(plan.repo_path))
    after_status = inspect_repository(Path(plan.repo_path))

    operation_result = OperationResult(
        operation="push",
        success=result.returncode == 0,
        stdout=result.stdout,
        stderr=result.stderr,
        before_status=before_status,
        after_status=after_status,
        plan=plan,
    )
    write_audit_entry(operation_result)
    return operation_result


def run_pull(path: Path) -> OperationResult:
    plan = build_pull_operation_plan(path)
    before_status = inspect_repository(Path(plan.repo_path))

    if not plan.allowed:
        raise RuntimeError("; ".join(plan.blockers) or "Pull operation is not allowed.")

    result = run_git(plan.command[1:], cwd=Path(plan.repo_path))
    after_status = inspect_repository(Path(plan.repo_path))

    operation_result = OperationResult(
        operation="pull",
        success=result.returncode == 0,
        stdout=result.stdout,
        stderr=result.stderr,
        before_status=before_status,
        after_status=after_status,
        plan=plan,
    )
    write_audit_entry(operation_result)
    return operation_result
