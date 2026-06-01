from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import base64
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from projectpilot.executor.config import ExecutorConfig
from projectpilot.executor.git_tasks import execute_local_git_operation, extract_params
from projectpilot.executor.remote import (
    apply_remote_git_operation,
    check_connection,
    detect_remote_environment,
    detect_remote_git_status,
    normalize_interpreter,
    normalize_script,
    normalize_script_args,
    normalize_script_env,
    run_remote_script,
    sha256_text,
)
from projectpilot.executor.security import PathNotAllowedError, resolve_allowed_project_path, validate_remote_project_path
from projectpilot.integration.member_b import detect_local_environment, detect_local_git_status

EXECUTOR_CAPABILITIES = [
    "detect_git",
    "detect_environment",
    "smart_git_analyze",
    "apply_git_operation",
    "run_local_script",
    "apply_local_script",
    "execute_local_script",
    "check_connection",
    "detect_remote_git_status",
    "detect_remote_environment",
    "apply_remote_git_operation",
    "run_remote_script",
    "apply_remote_script",
    "execute_remote_script",
]


def poll_and_run_once(config: ExecutorConfig, timeout: int = 15) -> dict[str, Any]:
    poll_response = poll_for_task(config, timeout=timeout)
    task = poll_response.get("task")
    if task is None:
        return {"success": True, "task": None, "submitted": False}

    task_id = str(task.get("id", ""))
    result = execute_task_with_metadata(task, config)
    submit_response = submit_task_result(config, task_id, result, timeout=timeout)
    return {
        "success": True,
        "task": task,
        "result": result,
        "submitted": True,
        "submit_response": submit_response,
    }


def run_connect_loop(
    config: ExecutorConfig,
    once: bool = False,
    timeout: int = 15,
    output: TextIO | None = None,
) -> None:
    stream = output or sys.stdout
    print(f"ProjectPilot Executor connected to {config.server_url}", file=stream)
    print(f"Executor: {config.executor_id}", file=stream)
    print(f"Allowed root: {config.allowed_root}", file=stream)
    print("Press Ctrl+C to stop.", file=stream)
    print(file=stream)

    while True:
        try:
            result = poll_and_run_once(config, timeout=timeout)
            task = result.get("task")
            if task is None:
                print("No task. Waiting...", file=stream)
            else:
                task_id = task.get("id", "(unknown)")
                task_type = task.get("type", "(unknown)")
                task_success = result.get("result", {}).get("success", False)
                print(f"Task {task_id} {task_type}: {'success' if task_success else 'failed'}", file=stream)
        except urllib.error.URLError as exc:
            print(f"Connection error: {exc}", file=stream)

        if once:
            return
        time.sleep(config.interval)


def poll_for_task(config: ExecutorConfig, timeout: int = 15) -> dict[str, Any]:
    payload = {
        "executor_id": config.executor_id,
        "mode": config.mode,
        "capabilities": EXECUTOR_CAPABILITIES,
        "status": "online",
    }
    return request_json(config, "POST", "/executor/poll", payload, timeout=timeout)


def submit_task_result(config: ExecutorConfig, task_id: str, result: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    payload = {
        "task_id": task_id,
        "executor_id": config.executor_id,
        "success": bool(result.get("success", False)),
        "error_type": result.get("error_type"),
        "message": result.get("message"),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "duration_ms": result.get("duration_ms"),
        "result": result,
    }
    return request_json(config, "POST", f"/executor/tasks/{task_id}/result", payload, timeout=timeout)


def execute_task_with_metadata(task: dict[str, Any], config: ExecutorConfig) -> dict[str, Any]:
    started_at = utc_now()
    started = time.perf_counter()
    result = execute_task(task, config)
    duration_ms = int((time.perf_counter() - started) * 1000)
    finished_at = utc_now()

    payload = dict(result)
    payload.setdefault("task_id", str(task.get("id", "")))
    payload.setdefault("task_type", str(task.get("type", "")))
    payload["started_at"] = started_at
    payload["finished_at"] = finished_at
    payload["duration_ms"] = duration_ms
    return payload


def execute_task(task: dict[str, Any], config: ExecutorConfig) -> dict[str, Any]:
    task_type = task.get("type")
    project_path = task.get("project_path")

    if task_type not in EXECUTOR_CAPABILITIES:
        return failure("unsupported_task", f"Unsupported task type: {task_type}")

    if task_type == "check_connection":
        return execute_remote_task(task_type, task, config)
    if task_type in {
        "detect_remote_git_status",
        "detect_remote_environment",
        "apply_remote_git_operation",
        "run_remote_script",
        "apply_remote_script",
        "execute_remote_script",
    }:
        return execute_remote_task(task_type, task, config)

    if not project_path:
        return failure("missing_project_path", "Task is missing project_path.")

    try:
        resolved_path = resolve_allowed_project_path(str(project_path), config.allowed_root)
    except PathNotAllowedError as exc:
        return failure("path_not_allowed", str(exc))

    if task_type == "detect_git":
        return detect_local_git_status(str(resolved_path))
    if task_type == "detect_environment":
        return detect_local_environment(str(resolved_path))
    if task_type == "smart_git_analyze":
        return execute_smart_git_analyze(task, resolved_path)
    if task_type == "apply_git_operation":
        return execute_local_git_operation(task, resolved_path)
    if task_type in {"run_local_script", "apply_local_script", "execute_local_script"}:
        if not task.get("approved"):
            return failure("approval_required", "Local script execution tasks require approved: true.")
        return execute_local_script_task(task, resolved_path)
    return failure("unsupported_task", f"Unsupported task type: {task_type}")


def execute_smart_git_analyze(task: dict[str, Any], resolved_path) -> dict[str, Any]:
    raw_analyses = task.get("analyses")
    analyses: list[str] | None = None
    if raw_analyses is not None:
        if not isinstance(raw_analyses, list) or not all(isinstance(item, str) for item in raw_analyses):
            return failure("invalid_analyses", "analyses must be a string array.")
        analyses = [str(item) for item in raw_analyses]

    from projectpilot.integration.smart_git import analyze_repository

    return analyze_repository(resolved_path, analyses=analyses)


def execute_local_script_task(task: dict[str, Any], resolved_path: Path) -> dict[str, Any]:
    try:
        script = normalize_script(extract_script(task))
        script_sha256 = sha256_text(script)
        expected_sha256 = script_expected_hash(task, extract_params(task))
        if expected_sha256 and expected_sha256 != script_sha256:
            return {
                "success": False,
                "error_type": "script_hash_mismatch",
                "project_path": str(resolved_path),
                "message": "Approved script hash does not match the script payload.",
                "expected_sha256": expected_sha256,
                "script_sha256": script_sha256,
            }

        interpreter = normalize_interpreter(str(task.get("interpreter") or "bash"))
        args = normalize_script_args(task.get("args", []))
        env = normalize_script_env(task.get("env", {}))
        command = [interpreter, "-s", "--", *args]
        result = subprocess.run(
            command,
            input=script,
            text=True,
            cwd=str(resolved_path),
            env={**os.environ, **env},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=int(task.get("timeout") or 60),
        )
        success = result.returncode == 0
        return {
            "success": success,
            "error_type": None if success else "local_script_failed",
            "project_path": str(resolved_path),
            "interpreter": interpreter,
            "command": command,
            "script_sha256": script_sha256,
            "script_size": len(script.encode("utf-8")),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "message": "Script executed successfully" if success else result.stderr.strip() or "Local script failed.",
        }
    except subprocess.TimeoutExpired:
        return failure("local_script_timeout", "Local script execution timed out.")
    except ValueError as exc:
        return failure("invalid_task", str(exc))


def execute_remote_task(task_type: str, task: dict[str, Any], config: ExecutorConfig) -> dict[str, Any]:
    try:
        host = extract_ssh_host(task)
        timeout = int(task.get("timeout") or 20)
        params = extract_params(task)
        ssh_auth_mode = extract_ssh_auth_mode(task, params)
        if task_type == "check_connection":
            return check_connection(host, timeout=timeout, auth_mode=ssh_auth_mode)

        project_path = task.get("project_path")
        if not project_path:
            return failure("missing_project_path", "Task is missing project_path.")
        try:
            project_path = validate_remote_project_path(
                str(project_path),
                task.get("allowed_paths") if "allowed_paths" in task else task.get("allowed_remote_paths"),
            )
        except PathNotAllowedError as exc:
            return failure("path_not_allowed", str(exc))

        if task_type == "detect_remote_git_status":
            return detect_remote_git_status(host, project_path, timeout=timeout, auth_mode=ssh_auth_mode)
        if task_type == "detect_remote_environment":
            return detect_remote_environment(host, project_path, timeout=timeout, auth_mode=ssh_auth_mode)
        if task_type == "apply_remote_git_operation":
            if not task.get("approved"):
                return failure("approval_required", "Remote Git execution tasks require approved: true.")
            expected_command = task.get("expected_command")
            if expected_command is not None and (
                not isinstance(expected_command, list) or not all(isinstance(item, str) for item in expected_command)
            ):
                return failure("invalid_expected_command", "expected_command must be a string array.")
            return apply_remote_git_operation(
                host,
                project_path,
                operation=str(task.get("operation") or ""),
                params=params,
                expected_command=expected_command,
                timeout=timeout,
                auth_mode=ssh_auth_mode,
            )
        if task_type in {"run_remote_script", "apply_remote_script", "execute_remote_script"}:
            if not task.get("approved"):
                return failure("approval_required", "Remote script execution tasks require approved: true.")
            return run_remote_script(
                host,
                extract_script(task),
                project_path=project_path,
                interpreter=str(task.get("interpreter") or params.get("interpreter") or "bash"),
                args=script_args(task, params),
                env=script_env(task, params),
                expected_sha256=script_expected_hash(task, params),
                auth_mode=ssh_auth_mode,
                timeout=timeout,
            )
    except ValueError as exc:
        return failure("invalid_task", str(exc))

    return failure("unsupported_task", f"Unsupported task type: {task_type}")


def extract_ssh_host(task: dict[str, Any]) -> str:
    host = task.get("ssh_host") or task.get("host") or task.get("server")
    if not host:
        raise ValueError("Task is missing ssh_host.")
    return str(host)


def extract_ssh_auth_mode(task: dict[str, Any], params: dict[str, Any]) -> str:
    return str(task.get("ssh_auth_mode") or task.get("auth_mode") or params.get("ssh_auth_mode") or "key")


def extract_script(task: dict[str, Any]) -> str:
    for key in ("script", "script_content", "script_body"):
        value = task.get(key)
        if value is not None:
            return str(value)
    encoded = task.get("script_base64")
    if encoded is not None:
        try:
            return base64.b64decode(str(encoded), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("script_base64 must be valid UTF-8 base64.") from exc
    raise ValueError("Task is missing script.")


def script_args(task: dict[str, Any], params: dict[str, Any]) -> list[str]:
    raw = task.get("args", params.get("args", []))
    if not isinstance(raw, list):
        raise ValueError("script args must be a string array.")
    return [str(item) for item in raw]


def script_env(task: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    raw = task.get("env", params.get("env", {}))
    if not isinstance(raw, dict):
        raise ValueError("script env must be an object.")
    return raw


def script_expected_hash(task: dict[str, Any], params: dict[str, Any]) -> str | None:
    value = task.get("script_sha256") or task.get("expected_sha256") or params.get("script_sha256") or params.get("expected_sha256")
    return str(value) if value else None


def request_json(
    config: ExecutorConfig,
    method: str,
    path: str,
    payload: dict[str, Any],
    timeout: int = 15,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url=f"{config.server_url}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {config.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    if not raw.strip():
        return {}
    return json.loads(raw)


def failure(error_type: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": error_type,
        "message": message,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
