from __future__ import annotations

import json
import shutil
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

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"


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
    ui = ConsoleUI(stream, enable_color=interactive)

    ui.render_header(profile)

    if not interactive:
        ui.info("Run `projectpilot` in an interactive terminal, or use `projectpilot backend ...` commands.")
        return {"success": True, "interactive": False}

    while True:
        ui.render_menu()
        choice = prompt(ui.prompt("Choose [1]: ")).strip() or "1"
        print(file=stream)

        if choice == "0":
            return {"success": True, "interactive": True}
        try:
            if choice == "1":
                render_dashboard(profile, stream, ui)
            elif choice == "2":
                print_json(get_health(profile), stream)
            elif choice == "3":
                print_projects(list_projects(profile), stream)
            elif choice == "4":
                print_servers(list_servers(profile), stream)
            elif choice == "5":
                print_tasks(list_tasks(profile), stream)
            elif choice == "6":
                project_id = int(prompt(ui.prompt(f"Project ID [{profile.default_project_id}]: ")).strip() or profile.default_project_id)
                server_id = int(prompt(ui.prompt(f"Server ID [{profile.default_server_id}]: ")).strip() or profile.default_server_id)
                print_json(trigger_detect(profile, project_id, server_id), stream)
            else:
                ui.warn(f"Unknown choice: {choice}")
        except Exception as exc:
            ui.error(str(exc))
        print(file=stream)


class ConsoleUI:
    def __init__(self, stream: TextIO, *, enable_color: bool = False) -> None:
        self.stream = stream
        self.enable_color = enable_color
        self.width = max(72, min(96, shutil.get_terminal_size((88, 24)).columns))

    def style(self, text: str, color: str) -> str:
        if not self.enable_color:
            return text
        return f"{color}{text}{RESET}"

    def prompt(self, text: str) -> str:
        return self.style(text, BOLD + CYAN)

    def info(self, text: str) -> None:
        print(self.style(text, DIM), file=self.stream)

    def warn(self, text: str) -> None:
        print(self.style(f"Warning: {text}", YELLOW), file=self.stream)

    def error(self, text: str) -> None:
        print(self.style(f"Error: {text}", RED), file=self.stream)

    def rule(self, title: str = "") -> None:
        if title:
            label = f" {title} "
            remaining = max(2, self.width - len(label))
            left = remaining // 2
            right = remaining - left
            print(self.style("-" * left + label + "-" * right, DIM), file=self.stream)
        else:
            print(self.style("-" * self.width, DIM), file=self.stream)

    def render_header(self, profile: BackendProfile) -> None:
        title = "ProjectPilot Backend Console"
        subtitle = "Backend control plane for projects, servers, executor tasks"
        print(self.style(title, BOLD + CYAN), file=self.stream)
        print(self.style(subtitle, DIM), file=self.stream)
        self.rule()
        print(f"{self.style('Backend', BOLD)}        {profile.server_url}", file=self.stream)
        print(
            f"{self.style('Default target', BOLD)} {profile.default_project_id}:{profile.default_server_id}",
            file=self.stream,
        )
        print(f"{self.style('Role', BOLD)}           Control console. Executor runs via `projectpilot executor server-b`.", file=self.stream)
        print(file=self.stream)

    def render_menu(self) -> None:
        self.rule("Actions")
        rows = [
            ("1", "Dashboard", "health, projects, servers, recent tasks"),
            ("2", "Health", "check backend availability"),
            ("3", "Projects", "list project bindings"),
            ("4", "Servers", "list server executors"),
            ("5", "Tasks", "show queued/running/completed executor tasks"),
            ("6", "Detect", "trigger project/server detection"),
            ("0", "Exit", "leave the console"),
        ]
        for key, label, detail in rows:
            key_text = self.style(f"[{key}]", BOLD + BLUE)
            print(f"  {key_text} {label:<10} {self.style(detail, DIM)}", file=self.stream)
        print(file=self.stream)


def render_dashboard(profile: BackendProfile, stream: TextIO, ui: ConsoleUI) -> None:
    ui.rule("Dashboard")
    health = get_health(profile)
    projects = list_projects(profile)
    servers = list_servers(profile)
    tasks = list_tasks(profile)

    health_label = health.get("status", "unknown") if isinstance(health, dict) else "unknown"
    health_color = GREEN if health_label == "ok" else YELLOW
    print(f"Health   {ui.style(str(health_label), BOLD + health_color)}", file=stream)
    print(f"Projects {len(projects) if isinstance(projects, list) else '-'}", file=stream)
    print(f"Servers  {len(servers) if isinstance(servers, list) else '-'}", file=stream)
    if isinstance(tasks, list):
        counts = count_task_statuses(tasks)
        print(
            "Tasks    "
            f"queued={counts.get('queued', 0)}  "
            f"running={counts.get('running', 0)}  "
            f"done={counts.get('succeeded', 0) + counts.get('completed', 0)}  "
            f"failed={counts.get('failed', 0)}",
            file=stream,
        )
    print(file=stream)
    print_tasks(tasks, stream, limit=8)


def print_json(data: Any, stream: TextIO) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2), file=stream)


def print_projects(data: Any, stream: TextIO) -> None:
    if not isinstance(data, list):
        print_json(data, stream)
        return
    if not data:
        print("No projects.", file=stream)
        return
    print(f"{'ID':<5} {'Name':<22} Path", file=stream)
    print(f"{'-' * 5} {'-' * 22} {'-' * 36}", file=stream)
    for project in data:
        print(
            f"{str(project.get('id')):<5} {clip(project.get('name'), 22):<22} {project.get('path')}",
            file=stream,
        )


def print_servers(data: Any, stream: TextIO) -> None:
    if not isinstance(data, list):
        print_json(data, stream)
        return
    if not data:
        print("No servers.", file=stream)
        return
    print(f"{'ID':<5} {'Name':<18} {'Mode':<12} Host", file=stream)
    print(f"{'-' * 5} {'-' * 18} {'-' * 12} {'-' * 30}", file=stream)
    for server in data:
        print(
            f"{str(server.get('id')):<5} {clip(server.get('name'), 18):<18} "
            f"{clip(server.get('connection_mode'), 12):<12} {server.get('host')}",
            file=stream,
        )


def print_tasks(data: Any, stream: TextIO, limit: int = 20) -> None:
    if not isinstance(data, list):
        print_json(data, stream)
        return
    if not data:
        print("No executor tasks.", file=stream)
        return
    counts = count_task_statuses(data)
    summary = "  ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(f"Summary: {summary}", file=stream)
    print(file=stream)
    print(f"{'Status':<10} {'Type':<20} {'Executor':<12} Task", file=stream)
    print(f"{'-' * 10} {'-' * 20} {'-' * 12} {'-' * 28}", file=stream)
    for task in data[:limit]:
        task_type = task.get("task_type") or task.get("type")
        print(
            f"{clip(task.get('status'), 10):<10} {clip(task_type, 20):<20} "
            f"{clip(task.get('executor_id'), 12):<12} {task.get('id')}",
            file=stream,
        )
    if len(data) > limit:
        print(f"... {len(data) - limit} more tasks", file=stream)


def count_task_statuses(tasks: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def clip(value: Any, width: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "~"
