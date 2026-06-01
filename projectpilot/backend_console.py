from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, TextIO


@dataclass(frozen=True)
class BackendProfile:
    server_url: str
    token: str = ""
    default_project_id: int = 1
    default_server_id: int = 2
    timeout: int = 15


DEFAULT_BACKEND_PROFILE = BackendProfile(
    server_url="https://printable-played-chances-response.trycloudflare.com",
    token="dev-token",
    default_project_id=1,
    default_server_id=2,
)


def request_backend_json(
    profile: BackendProfile,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if profile.token:
        headers["Authorization"] = f"Bearer {profile.token}"

    request = urllib.request.Request(
        url=f"{profile.server_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=profile.timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc

    if not raw.strip():
        return {}
    return json.loads(raw)


def get_health(profile: BackendProfile) -> Any:
    return request_backend_json(profile, "GET", "/health")


def list_projects(profile: BackendProfile) -> Any:
    return request_backend_json(profile, "GET", "/projects")


def list_servers(profile: BackendProfile) -> Any:
    return request_backend_json(profile, "GET", "/servers")


def list_tasks(profile: BackendProfile) -> Any:
    return request_backend_json(profile, "GET", "/executor/tasks")


def trigger_detect(profile: BackendProfile, project_id: int, server_id: int) -> Any:
    if project_id <= 0:
        raise ValueError("project_id must be greater than 0.")
    if server_id <= 0:
        raise ValueError("server_id must be greater than 0.")
    return request_backend_json(profile, "POST", f"/projects/{project_id}/servers/{server_id}/detect", {})


def run_backend_console(
    profile: BackendProfile = DEFAULT_BACKEND_PROFILE,
    *,
    output: TextIO | None = None,
    input_fn: Callable[[str], str] | None = None,
    interactive: bool | None = None,
) -> dict[str, Any]:
    stream = output or sys.stdout
    prompt = input_fn or input
    if interactive is None:
        interactive = sys.stdin.isatty()

    print("ProjectPilot Backend Console", file=stream)
    print("============================", file=stream)
    print(f"Backend: {profile.server_url}", file=stream)
    print(f"Default project/server: {profile.default_project_id}/{profile.default_server_id}", file=stream)
    print(file=stream)

    if not interactive:
        print("Run `projectpilot` in an interactive terminal, or use `projectpilot backend ...` commands.", file=stream)
        return {"success": True, "interactive": False}

    while True:
        print("1. Check backend health", file=stream)
        print("2. List projects", file=stream)
        print("3. List servers", file=stream)
        print("4. List executor tasks", file=stream)
        print("5. Trigger project/server detect", file=stream)
        print("0. Exit", file=stream)
        choice = prompt("Choose [1]: ").strip() or "1"
        print(file=stream)

        if choice == "0":
            return {"success": True, "interactive": True}
        try:
            if choice == "1":
                print_json(get_health(profile), stream)
            elif choice == "2":
                print_projects(list_projects(profile), stream)
            elif choice == "3":
                print_servers(list_servers(profile), stream)
            elif choice == "4":
                print_tasks(list_tasks(profile), stream)
            elif choice == "5":
                project_id = int(prompt(f"Project ID [{profile.default_project_id}]: ").strip() or profile.default_project_id)
                server_id = int(prompt(f"Server ID [{profile.default_server_id}]: ").strip() or profile.default_server_id)
                print_json(trigger_detect(profile, project_id, server_id), stream)
            else:
                print(f"Unknown choice: {choice}", file=stream)
        except Exception as exc:
            print(f"Error: {exc}", file=stream)
        print(file=stream)


def print_json(data: Any, stream: TextIO) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2), file=stream)


def print_projects(data: Any, stream: TextIO) -> None:
    if not isinstance(data, list):
        print_json(data, stream)
        return
    if not data:
        print("No projects.", file=stream)
        return
    for project in data:
        print(
            f"[{project.get('id')}] {project.get('name')}  path={project.get('path')}",
            file=stream,
        )


def print_servers(data: Any, stream: TextIO) -> None:
    if not isinstance(data, list):
        print_json(data, stream)
        return
    if not data:
        print("No servers.", file=stream)
        return
    for server in data:
        print(
            f"[{server.get('id')}] {server.get('name')}  mode={server.get('connection_mode')}  host={server.get('host')}",
            file=stream,
        )


def print_tasks(data: Any, stream: TextIO, limit: int = 20) -> None:
    if not isinstance(data, list):
        print_json(data, stream)
        return
    if not data:
        print("No executor tasks.", file=stream)
        return
    for task in data[:limit]:
        task_type = task.get("task_type") or task.get("type")
        print(
            f"[{task.get('id')}] {task_type}  status={task.get('status')}  executor={task.get('executor_id')}",
            file=stream,
        )
    if len(data) > limit:
        print(f"... {len(data) - limit} more tasks", file=stream)
