from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, TextIO

try:
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.json import JSON as RichJSON
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    box = None
    Align = None
    Columns = None
    Console = None
    Group = None
    RichJSON = None
    Panel = None
    Table = None
    Text = None
    RICH_AVAILABLE = False


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
    ui = ConsoleUI(stream, rich_enabled=interactive and RICH_AVAILABLE)

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
    def __init__(self, stream: TextIO, *, rich_enabled: bool = False) -> None:
        self.stream = stream
        self.rich_enabled = bool(rich_enabled and RICH_AVAILABLE)
        self.width = 96
        self.console = (
            Console(
                file=stream,
                force_terminal=self.rich_enabled,
                color_system="auto" if self.rich_enabled else None,
                width=self.width,
            )
            if RICH_AVAILABLE
            else None
        )

    def prompt(self, text: str) -> str:
        return text

    def info(self, text: str) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(Text(text, style="dim"))
            return
        print(text, file=self.stream)

    def warn(self, text: str) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(Panel(Text(text, style="yellow"), title="Warning", border_style="yellow"))
            return
        print(f"Warning: {text}", file=self.stream)

    def error(self, text: str) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(Panel(Text(text, style="red"), title="Error", border_style="red"))
            return
        print(f"Error: {text}", file=self.stream)

    def rule(self, title: str = "") -> None:
        if self.rich_enabled and self.console is not None:
            self.console.rule(title, style="dim cyan" if title else "dim")
            return
        if title:
            label = f" {title} "
            remaining = max(2, self.width - len(label))
            left = remaining // 2
            right = remaining - left
            print("-" * left + label + "-" * right, file=self.stream)
        else:
            print("-" * self.width, file=self.stream)

    def render_header(self, profile: BackendProfile) -> None:
        if self.rich_enabled and self.console is not None:
            title = Text("ProjectPilot", style="bold cyan")
            title.append("  Backend Control", style="bold white")
            subtitle = Text("AI project command center for projects, servers, and executor tasks", style="dim")
            meta = Table.grid(padding=(0, 2))
            meta.add_column(style="bold", no_wrap=True)
            meta.add_column()
            meta.add_row("Backend", profile.server_url)
            meta.add_row("Target", f"project {profile.default_project_id}  /  server {profile.default_server_id}")
            meta.add_row("Executor", "start with `projectpilot executor server-b`")
            self.console.print(
                Panel(
                    Group(title, subtitle, Text(""), meta),
                    box=box.ROUNDED,
                    border_style="cyan",
                    padding=(1, 2),
                )
            )
            return

        print("ProjectPilot Backend Console", file=self.stream)
        print("Backend control plane for projects, servers, executor tasks", file=self.stream)
        self.rule()
        print(f"Backend        {profile.server_url}", file=self.stream)
        print(f"Default target {profile.default_project_id}:{profile.default_server_id}", file=self.stream)
        print("Role           Control console. Executor runs via `projectpilot executor server-b`.", file=self.stream)
        print(file=self.stream)

    def render_menu(self) -> None:
        rows = [
            ("1", "Dashboard", "health, projects, servers, recent tasks"),
            ("2", "Health", "check backend availability"),
            ("3", "Projects", "list project bindings"),
            ("4", "Servers", "list server executors"),
            ("5", "Tasks", "queued, running, completed, failed"),
            ("6", "Detect", "trigger project/server detection"),
            ("0", "Exit", "leave the console"),
        ]
        if self.rich_enabled and self.console is not None:
            table = Table.grid(padding=(0, 2))
            table.add_column(justify="right", style="bold cyan", no_wrap=True)
            table.add_column(style="bold")
            table.add_column(style="dim")
            for key, label, detail in rows:
                table.add_row(key, label, detail)
            self.console.print(Panel(table, title="Actions", border_style="blue", box=box.ROUNDED))
            return

        self.rule("Actions")
        for key, label, detail in rows:
            print(f"  [{key}] {label:<10} {detail}", file=self.stream)
        print(file=self.stream)

    def render_dashboard(self, profile: BackendProfile) -> None:
        health = get_health(profile)
        projects = list_projects(profile)
        servers = list_servers(profile)
        tasks = list_tasks(profile)

        if self.rich_enabled and self.console is not None:
            self.console.rule("Dashboard", style="cyan")
            health_label = health.get("status", "unknown") if isinstance(health, dict) else "unknown"
            health_style = "green" if health_label == "ok" else "yellow"
            counts = count_task_statuses(tasks) if isinstance(tasks, list) else {}
            cards = [
                metric_card("Backend", str(health_label), "health", health_style),
                metric_card("Projects", str(len(projects)) if isinstance(projects, list) else "-", "registered"),
                metric_card("Servers", str(len(servers)) if isinstance(servers, list) else "-", "targets"),
                metric_card(
                    "Tasks",
                    str(len(tasks)) if isinstance(tasks, list) else "-",
                    f"queued {counts.get('queued', 0)} / failed {counts.get('failed', 0)}",
                ),
            ]
            self.console.print(Columns(cards, equal=True, expand=True))
            self.console.print()
            self.render_tasks(tasks, limit=8, title="Recent Tasks")
            return

        self.rule("Dashboard")
        health_label = health.get("status", "unknown") if isinstance(health, dict) else "unknown"
        print(f"Health   {health_label}", file=self.stream)
        print(f"Projects {len(projects) if isinstance(projects, list) else '-'}", file=self.stream)
        print(f"Servers  {len(servers) if isinstance(servers, list) else '-'}", file=self.stream)
        if isinstance(tasks, list):
            counts = count_task_statuses(tasks)
            print(
                "Tasks    "
                f"queued={counts.get('queued', 0)}  "
                f"running={counts.get('running', 0)}  "
                f"done={counts.get('succeeded', 0) + counts.get('completed', 0)}  "
                f"failed={counts.get('failed', 0)}",
                file=self.stream,
            )
        print(file=self.stream)
        self.render_tasks(tasks, limit=8)

    def render_json(self, data: Any) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(Panel(RichJSON.from_data(data), title="Response", border_style="cyan"))
            return
        print(json.dumps(data, ensure_ascii=False, indent=2), file=self.stream)

    def render_projects(self, data: Any) -> None:
        if not isinstance(data, list):
            self.render_json(data)
            return
        if self.rich_enabled and self.console is not None:
            table = Table(title="Projects", box=box.ROUNDED, border_style="cyan")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Name", style="bold")
            table.add_column("Path", style="dim")
            table.add_column("Description", style="dim")
            for project in data:
                table.add_row(
                    str(project.get("id") or ""),
                    str(project.get("name") or ""),
                    str(project.get("path") or ""),
                    str(project.get("description") or ""),
                )
            self.console.print(table if data else Panel("No projects.", border_style="cyan"))
            return
        self.render_plain_projects(data)

    def render_servers(self, data: Any) -> None:
        if not isinstance(data, list):
            self.render_json(data)
            return
        if self.rich_enabled and self.console is not None:
            table = Table(title="Servers", box=box.ROUNDED, border_style="cyan")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Name", style="bold")
            table.add_column("Mode")
            table.add_column("Host", style="dim")
            table.add_column("User", style="dim")
            for server in data:
                table.add_row(
                    str(server.get("id") or ""),
                    str(server.get("name") or ""),
                    str(server.get("connection_mode") or ""),
                    str(server.get("host") or ""),
                    str(server.get("username") or ""),
                )
            self.console.print(table if data else Panel("No servers.", border_style="cyan"))
            return
        self.render_plain_servers(data)

    def render_tasks(self, data: Any, limit: int = 20, title: str = "Executor Tasks") -> None:
        if not isinstance(data, list):
            self.render_json(data)
            return
        if self.rich_enabled and self.console is not None:
            counts = count_task_statuses(data)
            summary = "  ".join(f"{key} {value}" for key, value in sorted(counts.items())) or "empty"
            table = Table(title=f"{title}  ({summary})", box=box.ROUNDED, border_style="cyan")
            table.add_column("Status", no_wrap=True)
            table.add_column("Type")
            table.add_column("Executor")
            table.add_column("Task", style="dim")
            for task in data[:limit]:
                task_type = str(task.get("task_type") or task.get("type") or "")
                status = str(task.get("status") or "unknown")
                table.add_row(
                    Text(status, style=task_status_style(status)),
                    task_type,
                    str(task.get("executor_id") or ""),
                    str(task.get("id") or ""),
                )
            if len(data) > limit:
                table.caption = f"{len(data) - limit} more tasks hidden"
            self.console.print(table if data else Panel("No executor tasks.", border_style="cyan"))
            return
        self.render_plain_tasks(data, limit=limit)

    def render_plain_projects(self, data: list[Any]) -> None:
        if not data:
            print("No projects.", file=self.stream)
            return
        print(f"{'ID':<5} {'Name':<22} Path", file=self.stream)
        print(f"{'-' * 5} {'-' * 22} {'-' * 36}", file=self.stream)
        for project in data:
            print(f"{str(project.get('id')):<5} {clip(project.get('name'), 22):<22} {project.get('path')}", file=self.stream)

    def render_plain_servers(self, data: list[Any]) -> None:
        if not data:
            print("No servers.", file=self.stream)
            return
        print(f"{'ID':<5} {'Name':<18} {'Mode':<12} Host", file=self.stream)
        print(f"{'-' * 5} {'-' * 18} {'-' * 12} {'-' * 30}", file=self.stream)
        for server in data:
            print(
                f"{str(server.get('id')):<5} {clip(server.get('name'), 18):<18} "
                f"{clip(server.get('connection_mode'), 12):<12} {server.get('host')}",
                file=self.stream,
            )

    def render_plain_tasks(self, data: list[Any], limit: int = 20) -> None:
        if not data:
            print("No executor tasks.", file=self.stream)
            return
        counts = count_task_statuses(data)
        summary = "  ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        print(f"Summary: {summary}", file=self.stream)
        print(file=self.stream)
        print(f"{'Status':<10} {'Type':<20} {'Executor':<12} Task", file=self.stream)
        print(f"{'-' * 10} {'-' * 20} {'-' * 12} {'-' * 28}", file=self.stream)
        for task in data[:limit]:
            task_type = task.get("task_type") or task.get("type")
            print(
                f"{clip(task.get('status'), 10):<10} {clip(task_type, 20):<20} "
                f"{clip(task.get('executor_id'), 12):<12} {task.get('id')}",
                file=self.stream,
            )
        if len(data) > limit:
            print(f"... {len(data) - limit} more tasks", file=self.stream)


def render_dashboard(profile: BackendProfile, stream: TextIO, ui: ConsoleUI) -> None:
    ui.render_dashboard(profile)


def print_json(data: Any, stream: TextIO) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_json(data)


def print_projects(data: Any, stream: TextIO) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_projects(data)


def print_servers(data: Any, stream: TextIO) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_servers(data)


def print_tasks(data: Any, stream: TextIO, limit: int = 20) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_tasks(data, limit=limit)


def metric_card(label: str, value: str, caption: str, style: str = "cyan") -> Any:
    body = Group(
        Align.center(Text(value, style=f"bold {style}")),
        Align.center(Text(label, style="bold")),
        Align.center(Text(caption, style="dim")),
    )
    return Panel(body, box=box.ROUNDED, border_style=style, padding=(1, 2))


def task_status_style(status: str) -> str:
    normalized = status.lower()
    if normalized in {"succeeded", "completed", "success", "done"}:
        return "green"
    if normalized in {"running", "claimed", "in_progress"}:
        return "cyan"
    if normalized in {"queued", "pending"}:
        return "yellow"
    if normalized in {"failed", "error"}:
        return "red"
    return "dim"


def stream_is_tty(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


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
