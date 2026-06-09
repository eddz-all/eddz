from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PathNotAllowedError(ValueError):
    pass


class ApprovalError(ValueError):
    pass


EXECUTION_TASK_TYPES = {
    "apply_git_operation",
    "apply_remote_git_operation",
    "run_local_script",
    "apply_local_script",
    "execute_local_script",
    "run_remote_script",
    "apply_remote_script",
    "execute_remote_script",
}
SCRIPT_TASK_TYPES = {
    "run_local_script",
    "apply_local_script",
    "execute_local_script",
    "run_remote_script",
    "apply_remote_script",
    "execute_remote_script",
}
GIT_EXECUTION_TASK_TYPES = {"apply_git_operation", "apply_remote_git_operation"}


def resolve_allowed_project_path(project_path: str, allowed_root: Path) -> Path:
    root = allowed_root.expanduser().resolve()
    target = Path(project_path).expanduser()
    if not target.is_absolute():
        target = root / target
    resolved = target.resolve(strict=False)

    if not resolved.is_relative_to(root):
        raise PathNotAllowedError(f"Project path is outside allowed root: {resolved}")
    return resolved


def validate_remote_project_path(project_path: str, allowed_paths: Any = None) -> str:
    """Validate an absolute remote project path and optional allowed path prefixes."""
    value = str(project_path or "").strip()
    if not value:
        raise ValueError("project_path is required.")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("project_path contains invalid characters.")
    if not value.startswith("/"):
        raise ValueError("project_path must be an absolute remote path.")

    if allowed_paths is None:
        return value
    if not isinstance(allowed_paths, list):
        raise ValueError("allowed_paths must be a string array.")

    normalized_roots: list[str] = []
    for raw_root in allowed_paths:
        root = str(raw_root or "").strip().rstrip("/")
        if not root:
            continue
        if "\x00" in root or "\n" in root or "\r" in root:
            raise ValueError("allowed_paths contains invalid characters.")
        if not root.startswith("/"):
            raise ValueError("allowed_paths entries must be absolute remote paths.")
        normalized_roots.append(root or "/")

    for root in normalized_roots:
        if root == "/" or value == root or value.startswith(f"{root}/"):
            return value

    raise PathNotAllowedError(f"Remote project path is outside allowed paths: {value}")


def validate_execution_approval(
    task: dict[str, Any],
    *,
    task_type: str,
    script_sha256: str | None = None,
) -> None:
    """Validate explicit human approval metadata for executor execution tasks."""
    if not task.get("approved"):
        raise ApprovalError(f"{task_type} tasks require approved: true.")

    approval = task.get("approval")
    approval_data = approval if isinstance(approval, dict) else task
    approval_id = str(approval_data.get("approval_id") or "").strip()
    approved_by = str(approval_data.get("approved_by") or "").strip()
    approved_at_raw = approval_data.get("approved_at")
    expires_at_raw = approval_data.get("approval_expires_at") or approval_data.get("expires_at")

    if not approval_id:
        raise ApprovalError("Execution approval requires approval_id.")
    if not approved_by:
        raise ApprovalError("Execution approval requires approved_by.")
    approved_at = parse_approval_timestamp(approved_at_raw, "approved_at")
    expires_at = parse_approval_timestamp(expires_at_raw, "approval_expires_at")
    now = datetime.now(timezone.utc)
    if approved_at > now:
        raise ApprovalError("Execution approval approved_at is in the future.")
    if expires_at <= now:
        raise ApprovalError("Execution approval has expired.")

    if task_type in GIT_EXECUTION_TASK_TYPES and not task.get("expected_command"):
        raise ApprovalError("Git execution approval requires expected_command.")

    if task_type in SCRIPT_TASK_TYPES:
        expected_hash = (
            task.get("script_sha256")
            or task.get("expected_sha256")
            or approval_data.get("script_sha256")
            or approval_data.get("expected_sha256")
        )
        if not expected_hash:
            raise ApprovalError("Script execution approval requires script_sha256.")
        if script_sha256 and str(expected_hash) != script_sha256:
            raise ApprovalError("Script execution approval hash does not match the script payload.")


def parse_approval_timestamp(value: Any, field_name: str) -> datetime:
    if not value:
        raise ApprovalError(f"Execution approval requires {field_name}.")
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ApprovalError(f"Execution approval {field_name} must be an ISO timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
