from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


DEFAULT_SMART_GIT_ANALYSES = ["map", "sync-plan", "commit-plan"]


@dataclass(frozen=True)
class PublishTarget:
    server_url: str
    token: str
    timeout: int = 15


def build_task_payload(
    *,
    task_type: str,
    executor_id: str | None = None,
    project_path: str | None = None,
    analyses: list[str] | None = None,
    ssh_host: str | None = None,
    operation: str | None = None,
    approved: bool = False,
    expected_command: list[str] | None = None,
    params: dict[str, Any] | None = None,
    script: str | None = None,
    interpreter: str | None = None,
) -> dict[str, Any]:
    task_type = task_type.strip()
    if not task_type:
        raise ValueError("task type is required.")

    payload: dict[str, Any] = {"type": task_type}
    if executor_id:
        payload["executor_id"] = executor_id
    if project_path:
        payload["project_path"] = project_path
    if task_type == "smart_git_analyze":
        payload["analyses"] = analyses or list(DEFAULT_SMART_GIT_ANALYSES)
    if ssh_host:
        payload["ssh_host"] = ssh_host
    if operation:
        payload["operation"] = operation
    if approved:
        payload["approved"] = True
    if expected_command:
        payload["expected_command"] = expected_command
    if params:
        payload["params"] = params
    if script is not None:
        payload["script"] = script
    if interpreter:
        payload["interpreter"] = interpreter
    return payload


def build_project_detect_path(project_id: int, server_id: int) -> str:
    if project_id <= 0:
        raise ValueError("project_id must be greater than 0.")
    if server_id <= 0:
        raise ValueError("server_id must be greater than 0.")
    return f"/projects/{project_id}/servers/{server_id}/detect"


def publish_json(
    target: PublishTarget,
    *,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    url = f"{target.server_url.rstrip('/')}{path}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if target.token:
        headers["Authorization"] = f"Bearer {target.token}"
    request = urllib.request.Request(url=url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=target.timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed with HTTP {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"POST {url} failed: {exc}") from exc
    if not raw.strip():
        return {}
    return json.loads(raw)


def read_script(script: str | None, script_file: Path | None) -> str | None:
    if script is not None and script_file is not None:
        raise ValueError("Use either --script or --script-file, not both.")
    if script_file is not None:
        return script_file.expanduser().read_text(encoding="utf-8")
    return script


def parse_json_object(raw: str | None, *, label: str) -> dict[str, Any] | None:
    if not raw:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def render_payload_preview(path: str, payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "path": path,
            "payload": payload,
        },
        ensure_ascii=False,
        indent=2,
    )


def run_publish_console(defaults: dict[str, Any], output: TextIO | None = None) -> dict[str, Any]:
    stream = output or sys.stdout
    print("ProjectPilot Task Publisher", file=stream)
    print("===========================", file=stream)
    print("1. Direct executor task  (POST /tasks)", file=stream)
    print("2. Project detect task   (POST /projects/{project_id}/servers/{server_id}/detect)", file=stream)
    print("3. Print payload only", file=stream)
    print(file=stream)
    choice = prompt("Mode [1]", default="1")

    if choice == "2":
        project_id = int(prompt("Project ID"))
        server_id = int(prompt("Server ID"))
        return {
            "mode": "project-detect",
            "path": build_project_detect_path(project_id, server_id),
            "payload": {},
            "print_only": False,
        }

    task_type = prompt("Task type [smart_git_analyze]", default="smart_git_analyze")
    executor_id = prompt("Executor ID", default=str(defaults.get("executor_id") or ""))
    project_path = prompt("Project path", default=str(defaults.get("project_path") or ""))
    analyses: list[str] | None = None
    if task_type == "smart_git_analyze":
        raw = prompt("Analyses [map sync-plan commit-plan]", default="map sync-plan commit-plan")
        analyses = [item for item in raw.split() if item]
    payload = build_task_payload(
        task_type=task_type,
        executor_id=executor_id or None,
        project_path=project_path or None,
        analyses=analyses,
    )
    return {
        "mode": "direct-task",
        "path": "/tasks",
        "payload": payload,
        "print_only": choice == "3",
    }


def prompt(label: str, *, default: str | None = None) -> str:
    suffix = ": " if default is None else " "
    value = input(f"{label}{suffix}").strip()
    if value:
        return value
    return default or ""
