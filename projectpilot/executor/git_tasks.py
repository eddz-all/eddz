from __future__ import annotations

from pathlib import Path
from typing import Any

from projectpilot.git.executor import run_fetch
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
from projectpilot.git.safe_executor import execute_plan
from projectpilot.models.operation_plan import OperationPlan
from projectpilot.utils.shell import CommandError

GIT_APPLY_OPERATIONS = {
    "fetch",
    "add",
    "commit",
    "pull",
    "push",
    "switch",
    "merge",
    "stash",
    "tag",
    "revert",
    "cherry-pick",
}


def execute_local_git_operation(task: dict[str, Any], repo_path: Path) -> dict[str, Any]:
    if not task.get("approved"):
        return failure("approval_required", "Git execution tasks require approved: true.")

    operation = normalize_operation(task.get("operation"))
    if operation not in GIT_APPLY_OPERATIONS:
        return failure("unsupported_git_operation", f"Unsupported Git operation: {operation}")

    try:
        params = extract_params(task)
        if operation == "fetch":
            return execute_fetch(repo_path, params, task)

        plan = build_local_operation_plan(repo_path, operation, params)
        command_error = validate_expected_command(task, plan.command)
        if command_error:
            return command_error
        if not plan.allowed:
            return failure("operation_not_allowed", "; ".join(plan.blockers), plan=plan.to_dict())

        result = execute_plan(plan)
        return {
            "success": result.success,
            "operation": operation,
            "plan": plan.to_dict(),
            "result": result.to_dict(),
        }
    except (CommandError, RuntimeError, ValueError) as exc:
        return failure("git_operation_failed", str(exc))


def execute_fetch(repo_path: Path, params: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    command = ["git", "fetch"]
    if bool(params.get("prune", False)):
        command.append("--prune")
    remote = optional_str(params.get("remote"))
    if remote:
        command.append(remote)

    command_error = validate_expected_command(task, command)
    if command_error:
        return command_error

    result, status = run_fetch(repo_path, remote=remote, prune=bool(params.get("prune", False)))
    return {
        "success": result.returncode == 0,
        "operation": "fetch",
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
        "status": status.to_dict(),
    }


def build_local_operation_plan(repo_path: Path, operation: str, params: dict[str, Any]) -> OperationPlan:
    if operation == "add":
        return build_add_plan(
            repo_path,
            include_paths=string_list(params.get("include_paths") or params.get("include")),
            force_include_paths=string_list(params.get("force_include_paths") or params.get("force_include")),
        )
    if operation == "commit":
        return build_commit_operation_plan(repo_path, message=optional_str(params.get("message")))
    if operation == "pull":
        return build_pull_operation_plan(repo_path)
    if operation == "push":
        return build_push_operation_plan(repo_path)
    if operation == "switch":
        return build_switch_operation_plan(
            repo_path,
            target=required_str(params, "target"),
            create=bool(params.get("create", False)),
            start_point=optional_str(params.get("start_point")),
        )
    if operation == "merge":
        return build_merge_operation_plan(repo_path, source=required_str(params, "source"))
    if operation == "stash":
        return build_stash_operation_plan(
            repo_path,
            message=optional_str(params.get("message")),
            include_untracked=bool(params.get("include_untracked", False)),
        )
    if operation == "tag":
        return build_tag_operation_plan(
            repo_path,
            name=required_str(params, "name"),
            message=optional_str(params.get("message")),
        )
    if operation == "revert":
        return build_revert_operation_plan(
            repo_path,
            revision=required_str(params, "revision"),
            commit=bool(params.get("commit", False)),
        )
    if operation == "cherry-pick":
        return build_cherry_pick_operation_plan(
            repo_path,
            revision=required_str(params, "revision"),
            commit=bool(params.get("commit", False)),
        )
    raise ValueError(f"Unsupported Git operation: {operation}")


def extract_params(task: dict[str, Any]) -> dict[str, Any]:
    raw = task.get("params")
    if raw is None:
        raw = task.get("arguments")
    if raw is None:
        raw = task.get("args")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Git task params must be an object.")
    return raw


def validate_expected_command(task: dict[str, Any], command: list[str]) -> dict[str, Any] | None:
    expected = task.get("expected_command")
    if expected is None:
        return None
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        return failure("invalid_expected_command", "expected_command must be a string array.")
    if expected != command:
        return failure(
            "command_mismatch",
            "Approved command does not match the command generated by the executor.",
            expected_command=expected,
            generated_command=command,
        )
    return None


def normalize_operation(raw_operation: Any) -> str:
    return str(raw_operation or "").strip().replace("_", "-")


def required_str(params: dict[str, Any], key: str) -> str:
    value = optional_str(params.get(key))
    if not value:
        raise ValueError(f"Missing required Git parameter: {key}")
    return value


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ValueError("Expected a string array.")
    return [str(item) for item in value]


def failure(error_type: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "error_type": error_type,
        "message": message,
    }
    payload.update(extra)
    return payload
