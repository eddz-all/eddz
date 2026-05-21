from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, TextIO

from projectpilot.executor.config import ExecutorConfig
from projectpilot.executor.remote import check_connection, detect_remote_environment, detect_remote_git_status
from projectpilot.executor.security import PathNotAllowedError, resolve_allowed_project_path
from projectpilot.integration.member_b import detect_local_environment, detect_local_git_status

EXECUTOR_CAPABILITIES = [
    "detect_git",
    "detect_environment",
    "check_connection",
    "detect_remote_git_status",
    "detect_remote_environment",
]


def poll_and_run_once(config: ExecutorConfig, timeout: int = 15) -> dict[str, Any]:
    poll_response = poll_for_task(config, timeout=timeout)
    task = poll_response.get("task")
    if task is None:
        return {"success": True, "task": None, "submitted": False}

    task_id = str(task.get("id", ""))
    result = execute_task(task, config)
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
        "result": result,
    }
    return request_json(config, "POST", f"/executor/tasks/{task_id}/result", payload, timeout=timeout)


def execute_task(task: dict[str, Any], config: ExecutorConfig) -> dict[str, Any]:
    task_type = task.get("type")
    project_path = task.get("project_path")

    if task_type not in EXECUTOR_CAPABILITIES:
        return failure("unsupported_task", f"Unsupported task type: {task_type}")

    if task_type == "check_connection":
        return execute_remote_task(task_type, task, config)
    if task_type in {"detect_remote_git_status", "detect_remote_environment"}:
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
    return failure("unsupported_task", f"Unsupported task type: {task_type}")


def execute_remote_task(task_type: str, task: dict[str, Any], config: ExecutorConfig) -> dict[str, Any]:
    try:
        host = extract_ssh_host(task)
        timeout = int(task.get("timeout") or 20)
        if task_type == "check_connection":
            return check_connection(host, timeout=timeout)

        project_path = task.get("project_path")
        if not project_path:
            return failure("missing_project_path", "Task is missing project_path.")

        if task_type == "detect_remote_git_status":
            return detect_remote_git_status(host, str(project_path), timeout=timeout)
        if task_type == "detect_remote_environment":
            return detect_remote_environment(host, str(project_path), timeout=timeout)
    except ValueError as exc:
        return failure("invalid_task", str(exc))

    return failure("unsupported_task", f"Unsupported task type: {task_type}")


def extract_ssh_host(task: dict[str, Any]) -> str:
    host = task.get("ssh_host") or task.get("host") or task.get("server")
    if not host:
        raise ValueError("Task is missing ssh_host.")
    return str(host)


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
