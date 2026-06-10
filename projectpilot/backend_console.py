from __future__ import annotations

import io
import json
import os
import re
import select
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable, TextIO

try:
    from rich import box
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.json import JSON as RichJSON
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    box = None
    Columns = None
    Console = None
    Group = None
    RichJSON = None
    Panel = None
    Table = None
    Text = None
    RICH_AVAILABLE = False


UI_BG = "#080c16"
UI_SIDEBAR = "#0a0f1b"
UI_PANEL = "#12192b"
UI_PANEL_ALT = "#171f35"
UI_BORDER = "#24304f"
UI_BORDER_MUTED = "#1d2638"
UI_PRIMARY = "#4b51f5"
UI_PURPLE = "#6e6cff"
UI_CYAN = "#24d4e8"
UI_TEXT = "#eaf0ff"
UI_MUTED = "#93a0b8"
UI_GREEN = "#76efac"
UI_YELLOW = "#f9c75d"
UI_RED = "#ff6d8f"
UI_WHITE = "#ffffff"
UI_NAV_TEXT = "#b9c4d9"
UI_BADGE_GREEN = "#132f28"
UI_BADGE_YELLOW = "#332817"
UI_BADGE_RED = "#351a29"
UI_BADGE_MUTED = "#1c2538"
ERROR_BODY_LIMIT = 220


@dataclass(frozen=True)
class BackendProfile:
    server_url: str
    token: str = ""
    default_project_id: int = 1
    default_server_id: int = 2
    timeout: int = 15


DEFAULT_BACKEND_PROFILE = BackendProfile(
    server_url="https://unique-painted-runner-last.trycloudflare.com",
    token="dev-token",
    default_project_id=1,
    default_server_id=2,
)

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("1", "Dashboard", "D"),
    ("3", "Projects", "P"),
    ("4", "Servers", "S"),
    ("b", "Bindings", "B"),
    ("a", "AI Ops", "A"),
    ("5", "Tasks", "T"),
    ("m", "API Map", "M"),
    ("g", "Settings", "G"),
)

NAV_KEYS = tuple(key for key, _, _ in NAV_ITEMS)
NAV_SHORTCUTS = {
    shortcut.lower(): marker.lower()
    for marker, _label, icon in NAV_ITEMS
    for shortcut in (marker, icon)
}
NAV_SHORTCUTS["0"] = "0"
NAV_SHORTCUTS["q"] = "0"
_PENDING_TERMINAL_KEYS: list[str] = []

API_CONTRACT: tuple[tuple[str, str, str, str], ...] = (
    ("GET", "/projects", "已接入", "项目列表"),
    ("POST", "/projects", "已接入", "创建项目"),
    ("GET", "/servers", "已接入", "服务器列表"),
    ("POST", "/servers", "已接入", "创建服务器"),
    ("GET", "/servers/{id}/status", "已接入", "服务器综合状态"),
    ("GET", "/projects/{id}/status", "已接入", "项目综合状态"),
    ("POST", "/projects/{id}/ai/analyze-env", "已接入", "AI 环境分析"),
    ("POST", "/projects/{id}/ai/config-plan", "已接入", "AI 配置计划"),
    ("POST", "/projects/{id}/ai/analyze-git", "已接入", "AI Git 分析"),
    ("POST", "/projects/{id}/bind-server", "已接入", "绑定项目服务器"),
    ("DELETE", "/projects/{id}/servers/{server_id}", "已接入", "解除项目服务器绑定"),
    ("POST", "/reports/project", "已接入", "Markdown 报告"),
    ("POST", "/servers/{id}/check-connection", "已接入", "服务器连接检测"),
    ("GET", "/projects/{id}/servers", "已接入", "项目绑定服务器"),
    ("POST", "/projects/{id}/servers/{server_id}/detect", "已接入", "单服务器检测"),
    ("POST", "/projects/{id}/servers/{server_id}/execute-config-plan", "已接入", "执行配置计划"),
    ("GET", "/operation-logs", "已接入", "操作日志"),
    ("GET", "/executor/tasks", "已接入", "Executor 任务流"),
    ("GET", "/executor/tasks/{task_id}", "已接入", "Executor 单任务"),
    ("GET", "/ai/settings", "已接入", "AI 配置状态"),
    ("POST", "/projects/{id}/ai/plan-action", "已接入", "AI 主动执行计划"),
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
        exc.close()
        raise RuntimeError(format_backend_http_error(method, path, exc.code, raw)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc

    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON response: {summarize_backend_response_body(raw)}") from exc


def format_backend_http_error(method: str, path: str, status_code: int, raw_body: str) -> str:
    return f"{method} {path} failed with HTTP {status_code}: {summarize_backend_response_body(raw_body)}"


def summarize_backend_response_body(raw_body: str) -> str:
    body = raw_body.strip()
    if not body:
        return "empty response body"

    json_detail = json_error_detail(body)
    if json_detail:
        return json_detail

    html_detail = html_error_detail(body)
    if html_detail:
        return html_detail

    return compact_error_text(body, ERROR_BODY_LIMIT)


def json_error_detail(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if value:
                return compact_error_text(value, ERROR_BODY_LIMIT)
    return compact_error_text(payload, ERROR_BODY_LIMIT)


def html_error_detail(body: str) -> str:
    title = html_tag_text(body, "title")
    heading = html_tag_text(body, "h1")
    if title:
        if heading and heading not in title:
            return compact_error_text(f"{title} - {heading}", ERROR_BODY_LIMIT)
        return compact_error_text(title, ERROR_BODY_LIMIT)
    if looks_like_html(body):
        return compact_error_text(strip_html_tags(body), ERROR_BODY_LIMIT)
    return ""


def html_tag_text(body: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", body, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        return ""
    return compact_error_text(strip_html_tags(match.group(1)), ERROR_BODY_LIMIT)


def looks_like_html(body: str) -> bool:
    head = body[:200].lower()
    return "<!doctype html" in head or "<html" in head or "<body" in head


def strip_html_tags(value: Any) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", str(value), flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return compact_error_text(unescape(text), ERROR_BODY_LIMIT)


def compact_error_text(value: Any, limit: int = ERROR_BODY_LIMIT) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "~"


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


def dashboard_backend_json(
    profile: BackendProfile,
    method: str,
    path: str,
    fallback: Any,
    payload: dict[str, Any] | None = None,
) -> tuple[Any, str | None]:
    try:
        return request_backend_json(profile, method, path, payload), None
    except Exception as exc:
        return fallback, str(exc)


def read_action_key(input_fn: Callable[[str], str] | None = None) -> str:
    if input_fn is not None:
        return normalize_action_key(input_fn(""))

    if not sys.stdin.isatty():
        return normalize_action_key(input(""))

    try:
        import termios

        fd = sys.stdin.fileno()
        original = termios.tcgetattr(fd)
        current = termios.tcgetattr(fd)
        current[3] = current[3] & ~(termios.ICANON | termios.ECHO)
        current[6][termios.VMIN] = 1
        current[6][termios.VTIME] = 0
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, current)
            key = read_terminal_char(fd)
            if key in {"\x03", "\x04", "q", "Q"}:
                return "0"
            if key in {"\r", "\n"}:
                return "enter"
            if key == " ":
                return "enter"
            if key == "\x1b":
                pending = read_escape_sequence(fd)
                return map_escape_sequence(pending) if pending else "esc"
            return normalize_action_key(key)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)
    except KeyboardInterrupt:
        return "0"
    except Exception:
        return normalize_action_key(input(""))


def normalize_action_key(value: str) -> str:
    raw = value or ""
    if raw in {"\r", "\n"}:
        return ""
    if raw == "\t":
        return "down"
    if raw == "\x0e":
        return "down"
    if raw == "\x10":
        return "up"
    if raw == "\x12":
        return "refresh"
    if raw == "\x1b":
        return "esc"
    if raw.startswith("\x1b"):
        return map_escape_sequence(raw[1:])
    if raw.strip() in {"[", "A", "B", "C", "D", "O"}:
        return ""
    key = raw.strip().lower()
    if key in {"home"}:
        return "home"
    if key in {"ctrl+r", "refresh"}:
        return "refresh"
    if key in {"enter", "return", "space"}:
        return "enter"
    if key in {"esc", "escape"}:
        return "esc"
    if key in {"up"}:
        return "up"
    if key in {"down"}:
        return "down"
    if key in {"left"}:
        return "up"
    if key in {"right"}:
        return "down"
    if key == "q":
        return "0"
    if not key:
        return "1"
    return key[0]


def map_escape_sequence(sequence: str) -> str:
    if sequence in {"[A", "OA"}:
        return "up"
    if sequence in {"[B", "OB"}:
        return "down"
    if sequence in {"[D", "OD"}:
        return "up"
    if sequence in {"[C", "OC"}:
        return "down"
    if sequence in {"[H", "OH", "[1~"}:
        return "home"
    if sequence in {"[F", "OF", "[4~"}:
        return "end"
    if sequence == "[Z":
        return "up"
    return ""


def read_terminal_char(fd: int) -> str:
    if _PENDING_TERMINAL_KEYS:
        return _PENDING_TERMINAL_KEYS.pop(0)
    return os.read(fd, 1).decode("utf-8", "ignore")


def read_escape_sequence(fd: int) -> str:
    prefix = read_timed_terminal_char(fd, timeout=0.12)
    if not prefix:
        return ""
    if prefix not in {"[", "O"}:
        _PENDING_TERMINAL_KEYS.append(prefix)
        return ""

    sequence = prefix
    for _ in range(8):
        char = read_timed_terminal_char(fd, timeout=0.03)
        if not char:
            break
        sequence += char
        if char == "~" or char.isalpha():
            break
    return sequence


def read_timed_terminal_char(fd: int, *, timeout: float) -> str:
    if _PENDING_TERMINAL_KEYS:
        return _PENDING_TERMINAL_KEYS.pop(0)
    try:
        if not select.select([fd], [], [], timeout)[0]:
            return ""
    except Exception:
        return ""
    return read_terminal_char(fd)


def read_pending_stdin(
    initial_timeout: float = 0.12,
    subsequent_timeout: float = 0.01,
    *,
    fd: int | None = None,
    max_chars: int = 32,
) -> str:
    chars: list[str] = []
    timeout = initial_timeout
    input_target: int | TextIO = fd if fd is not None else sys.stdin
    try:
        while len(chars) < max_chars and select.select([input_target], [], [], timeout)[0]:
            if fd is not None:
                chars.append(read_terminal_char(fd))
            else:
                chars.append(sys.stdin.read(1))
            timeout = subsequent_timeout
    except Exception:
        return "".join(chars)
    return "".join(chars)


def move_selection(selected: str, step: int) -> str:
    normalized = normalize_nav_key(selected) or "1"
    try:
        index = NAV_KEYS.index(normalized)
    except ValueError:
        index = 0
    return NAV_KEYS[(index + step) % len(NAV_KEYS)]


def normalize_nav_key(value: str) -> str:
    key = (value or "1").strip().lower()
    return NAV_SHORTCUTS.get(key, "")


def nav_label(value: str) -> str:
    key = normalize_nav_key(value) or "1"
    if key == "0":
        return "Quit"
    for marker, label, _ in NAV_ITEMS:
        if marker == key:
            return label
    return "Dashboard"


def execute_detect_action(profile: BackendProfile) -> tuple[Any, str | None]:
    return dashboard_backend_json(
        profile,
        "POST",
        f"/projects/{profile.default_project_id}/servers/{profile.default_server_id}/detect",
        {},
        payload={},
    )


def load_dashboard_snapshot(profile: BackendProfile) -> dict[str, Any]:
    errors: list[str] = []
    health, error = dashboard_backend_json(profile, "GET", "/health", {"status": "offline"})
    if error is not None:
        errors.append(error)
        projects: Any = []
        servers: Any = []
        tasks: Any = []
        status: Any = {}
        activities: Any = []
    else:
        projects, error = dashboard_backend_json(profile, "GET", "/projects", [])
        if error is not None:
            errors.append(error)
        servers, error = dashboard_backend_json(profile, "GET", "/servers", [])
        if error is not None:
            errors.append(error)
        tasks, error = dashboard_backend_json(profile, "GET", "/executor/tasks", [])
        if error is not None:
            errors.append(error)
        status, error = dashboard_backend_json(
            profile,
            "GET",
            f"/projects/{profile.default_project_id}/status",
            {},
        )
        if error is not None:
            errors.append(error)
        activities, error = dashboard_backend_json(profile, "GET", "/operation-logs?limit=8", [])
        if error is not None:
            errors.append(error)
    return build_dashboard_data(profile, health, projects, servers, tasks, status, activities, errors=errors)


def run_backend_console(
    profile: BackendProfile = DEFAULT_BACKEND_PROFILE,
    *,
    output: TextIO | None = None,
    input_fn: Callable[[str], str] | None = None,
    interactive: bool | None = None,
) -> dict[str, Any]:
    stream = output or sys.stdout
    if interactive is None:
        interactive = sys.stdin.isatty()
    ui = ConsoleUI(stream, rich_enabled=interactive and RICH_AVAILABLE)

    if not interactive:
        ui.render_header(profile)
        ui.info("Run `projectpilot` in an interactive terminal, or use `projectpilot backend ...` commands.")
        return {"success": True, "interactive": False}

    def run_loop() -> dict[str, Any]:
        active = "1"
        selected = "1"
        detect_result: tuple[Any, str | None] | None = None
        page_cache: dict[str, Any] = {}
        cached_payload: Any = None

        def refresh_active_page(*, force: bool = False) -> None:
            nonlocal cached_payload, detect_result
            if not force and active in page_cache:
                cached_payload = page_cache[active]
                return
            if active == "1":
                cached_payload = load_dashboard_snapshot(profile)
            elif active == "3":
                cached_payload = dashboard_backend_json(profile, "GET", "/projects", [])
            elif active == "4":
                cached_payload = dashboard_backend_json(profile, "GET", "/servers", [])
            elif active == "5":
                cached_payload = dashboard_backend_json(profile, "GET", "/executor/tasks", [])
            elif active == "b":
                cached_payload = dashboard_backend_json(profile, "GET", f"/projects/{profile.default_project_id}/servers", [])
            elif active == "a":
                cached_payload = dashboard_backend_json(profile, "GET", "/ai/settings", {})
            elif active == "m":
                cached_payload = (API_CONTRACT, None)
            elif active == "g":
                health, error = dashboard_backend_json(profile, "GET", "/health", {"status": "offline"})
                cached_payload = (
                    {
                        "server_url": profile.server_url,
                        "token": "configured" if profile.token else "not configured",
                        "default_project_id": profile.default_project_id,
                        "default_server_id": profile.default_server_id,
                        "timeout": profile.timeout,
                        "health": health,
                    },
                    error,
                )
            elif active == "r":
                if detect_result is None:
                    detect_result = execute_detect_action(profile)
                cached_payload = detect_result
            else:
                cached_payload = None
            page_cache[active] = cached_payload

        def render_active_page() -> None:
            if active == "1":
                ui.render_dashboard_snapshot(cached_payload, selected=selected)
            elif active == "3":
                data, error = cached_payload
                ui.render_endpoint_data_page(
                    profile,
                    title="Projects",
                    active="3",
                    selected=selected,
                    data=data,
                    error=error,
                    body_builder=render_projects_panel,
                )
            elif active == "4":
                data, error = cached_payload
                ui.render_endpoint_data_page(
                    profile,
                    title="Servers",
                    active="4",
                    selected=selected,
                    data=data,
                    error=error,
                    body_builder=render_servers_panel,
                )
            elif active == "5":
                data, error = cached_payload
                ui.render_endpoint_data_page(
                    profile,
                    title="Executor Tasks",
                    active="5",
                    selected=selected,
                    data=data,
                    error=error,
                    body_builder=lambda value: render_tasks_panel(value, title="Executor Tasks"),
                )
            elif active == "b":
                data, error = cached_payload
                ui.render_endpoint_data_page(
                    profile,
                    title="Bindings",
                    active="b",
                    selected=selected,
                    data=data,
                    error=error,
                    body_builder=render_bindings_panel,
                )
            elif active == "a":
                data, error = cached_payload
                ui.render_endpoint_data_page(
                    profile,
                    title="AI Ops",
                    active="a",
                    selected=selected,
                    data=data,
                    error=error,
                    body_builder=render_ai_ops_panel,
                )
            elif active == "m":
                data, error = cached_payload
                ui.render_endpoint_data_page(
                    profile,
                    title="API Map",
                    active="m",
                    selected=selected,
                    data=data,
                    error=error,
                    body_builder=render_api_map_panel,
                )
            elif active == "g":
                data, error = cached_payload
                ui.render_endpoint_data_page(
                    profile,
                    title="Settings",
                    active="g",
                    selected=selected,
                    data=data,
                    error=error,
                    body_builder=render_settings_panel,
                )
            elif active == "r":
                data, error = cached_payload
                ui.render_detect_result_page(profile, data, error, selected=selected)

        while True:
            if active == "0":
                return {"success": True, "interactive": True}
            ui.begin_frame()
            try:
                try:
                    refresh_active_page()
                    ui.clear()
                    render_active_page()
                except Exception as exc:
                    ui.error(str(exc))
                ui.render_footer()
            finally:
                ui.end_frame()
            while True:
                next_choice = read_action_key(input_fn)
                if next_choice:
                    if next_choice == "up":
                        selected = move_selection(selected, -1)
                        active = selected
                    elif next_choice == "down":
                        selected = move_selection(selected, 1)
                        active = selected
                    elif next_choice == "enter":
                        page_cache.pop(active, None)
                    elif next_choice == "refresh":
                        page_cache.pop(active, None)
                    elif next_choice == "home":
                        selected = "1"
                        active = selected
                    elif next_choice == "end":
                        selected = NAV_KEYS[-1]
                        active = selected
                    elif next_choice == "esc":
                        selected = "1"
                        active = selected
                    elif next_choice in {"6", "r"}:
                        detect_result = execute_detect_action(profile)
                        page_cache.pop("r", None)
                        active = "r"
                    else:
                        normalized = normalize_nav_key(next_choice)
                        if not normalized:
                            continue
                        selected = normalized
                        if normalized == "0":
                            active = "0"
                        else:
                            active = normalized
                    break

    if ui.rich_enabled and ui.console is not None and input_fn is None and output is None:
        with ui.console.screen(hide_cursor=True, style=f"on {UI_BG}"):
            return run_loop()
    return run_loop()


class ConsoleUI:
    def __init__(self, stream: TextIO, *, rich_enabled: bool = False) -> None:
        self._target_stream = stream
        self.stream = stream
        self.rich_enabled = bool(rich_enabled and RICH_AVAILABLE)
        self.width = 96
        self.height = 30
        self._frame_stream: io.StringIO | None = None
        self._frame_footer_lines = 0
        self._last_rendered_size: tuple[int, int] | None = None
        self.refresh_terminal_size()
        self.console = self._make_console(stream) if RICH_AVAILABLE else None

    def refresh_terminal_size(self) -> None:
        if not self.rich_enabled:
            self.width = 96
            self.height = 30
            return
        detected_size = shutil.get_terminal_size((120, 30))
        self.width = max(20, detected_size.columns)
        self.height = max(1, detected_size.lines)

    def _make_console(self, stream: TextIO) -> Any:
        return Console(
            file=stream,
            force_terminal=self.rich_enabled,
            color_system="truecolor" if self.rich_enabled else None,
            width=self.width,
            height=self.height,
            _environ={"COLUMNS": str(self.width), "LINES": str(self.height)},
        )

    def prompt(self, text: str) -> str:
        return text

    def begin_frame(self) -> None:
        if not self.rich_enabled or self.console is None or self._frame_stream is not None:
            return
        self.refresh_terminal_size()
        self._frame_stream = io.StringIO()
        self._frame_footer_lines = 0
        self.stream = self._frame_stream
        self.console = self._make_console(self._frame_stream)

    def end_frame(self) -> None:
        if self._frame_stream is None:
            return
        frame = self._frame_stream.getvalue()
        self._frame_stream = None
        footer_lines = self._frame_footer_lines
        self._frame_footer_lines = 0
        self.stream = self._target_stream
        self.console = self._make_console(self._target_stream) if RICH_AVAILABLE else None
        self.write_frame(frame, footer_lines=footer_lines)

    def write_frame(self, frame: str, *, footer_lines: int = 0) -> None:
        if not self.rich_enabled:
            self._target_stream.write(frame)
            flush = getattr(self._target_stream, "flush", None)
            if flush is not None:
                flush()
            return

        lines = frame.splitlines()
        height = max(1, self.height)
        size = (self.width, height)
        if footer_lines > 0 and len(lines) > height:
            footer_count = min(footer_lines, height, len(lines))
            body_count = max(0, height - footer_count)
            lines = lines[:body_count] + lines[-footer_count:]
        target = self._target_stream
        target.write("\x1b[?25l")
        if self._last_rendered_size is not None and self._last_rendered_size != size:
            target.write("\x1b[2J\x1b[H")
        for row in range(height):
            line = lines[row] if row < len(lines) else ""
            target.write(f"\x1b[{row + 1};1H{line}\x1b[K")
        self._last_rendered_size = size
        flush = getattr(target, "flush", None)
        if flush is not None:
            flush()

    def clear(self) -> None:
        if self._frame_stream is not None:
            return
        if self.rich_enabled and self.console is not None:
            self.stream.write("\x1b[2J\x1b[H")
            flush = getattr(self.stream, "flush", None)
            if flush is not None:
                flush()

    def render_footer(self) -> None:
        if self.width < 80:
            shortcuts = "↑/↓ Pages  Enter Refresh  q Quit"
        elif self.width < 120:
            shortcuts = "↑/↓ Pages  Enter Refresh  R Detect  q Quit  ·  D/P/S/B/A/T/M/G"
        else:
            shortcuts = "↑/↓ Switch Pages  Enter/Ctrl+R Refresh  Esc Dashboard  R/6 Detect  q/0 Quit"
        status_line = clip(shortcuts, max(20, self.width - 2))
        if self.rich_enabled and self.console is not None:
            self.console.print(Text(f" {status_line} ", style=f"bold {UI_MUTED} on {UI_PANEL_ALT}"))
            if self._frame_stream is not None:
                self._frame_footer_lines = 1
            return
        print(file=self.stream)
        print(status_line, file=self.stream)

    def info(self, text: str) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(Text(text, style=UI_MUTED))
            return
        print(text, file=self.stream)

    def warn(self, text: str) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(gui_panel(Text(text, style=UI_YELLOW), title="Warning", border_style=UI_YELLOW))
            return
        print(f"Warning: {text}", file=self.stream)

    def error(self, text: str) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(gui_panel(Text(text, style=UI_RED), title="Error", border_style=UI_RED))
            return
        print(f"Error: {text}", file=self.stream)

    def rule(self, title: str = "") -> None:
        if self.rich_enabled and self.console is not None:
            self.console.rule(title, style=UI_BORDER if title else UI_BORDER_MUTED)
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
            title = Text("ProjectPilot", style=f"bold {UI_TEXT}")
            title.append("  Console", style=f"bold {UI_MUTED}")
            subtitle = Text("AI Project Health Monitor", style=UI_MUTED)
            meta = Table.grid(padding=(0, 2))
            meta.add_column(style=f"bold {UI_TEXT}", no_wrap=True)
            meta.add_column(style=UI_MUTED)
            meta.add_row("Backend", profile.server_url)
            meta.add_row("Target", f"project {profile.default_project_id}  /  server {profile.default_server_id}")
            meta.add_row("Executor", "start with `projectpilot executor server-b`")
            self.console.print(
                gui_panel(
                    Group(title, subtitle, Text(""), meta),
                    border_style=UI_BORDER,
                    style=f"{UI_TEXT} on {UI_PANEL}",
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

    def render_dashboard(self, profile: BackendProfile, *, selected: str = "1") -> None:
        self.render_dashboard_snapshot(load_dashboard_snapshot(profile), selected=selected)

    def render_dashboard_snapshot(self, dashboard: dict[str, Any], *, selected: str = "1") -> None:
        if self.rich_enabled and self.console is not None:
            compact = self.width < 130
            main = Group(
                render_compact_nav_bar(active="1", selected=selected, width=self.width) if compact else Text(""),
                render_topbar_panel(dashboard, title="Dashboard"),
                render_backend_errors_panel(dashboard),
                render_compact_dashboard_summary(dashboard) if compact else render_metric_cards(dashboard),
                Text(""),
                render_dashboard_content(dashboard, compact=compact, short=compact and self.height < 38),
            )
            if compact:
                self.console.print(main)
            else:
                shell = Table.grid(expand=True, padding=(0, 2))
                shell.add_column(width=28)
                shell.add_column(ratio=1)
                shell.add_row(render_sidebar_panel(dashboard, active="1", selected=selected), main)
                self.console.print(shell)
            return

        self.render_plain_dashboard(dashboard)

    def render_health_page(self, profile: BackendProfile, *, selected: str = "2") -> None:
        self.render_endpoint_page(
            profile,
            title="Health",
            active="2",
            selected=selected,
            method="GET",
            path="/health",
            fallback={"status": "offline"},
            body_builder=lambda data: render_json_panel(data, title="Health Response"),
        )

    def render_projects_page(self, profile: BackendProfile, *, selected: str = "3") -> None:
        self.render_endpoint_page(
            profile,
            title="Projects",
            active="3",
            selected=selected,
            method="GET",
            path="/projects",
            fallback=[],
            body_builder=render_projects_panel,
        )

    def render_servers_page(self, profile: BackendProfile, *, selected: str = "4") -> None:
        self.render_endpoint_page(
            profile,
            title="Servers",
            active="4",
            selected=selected,
            method="GET",
            path="/servers",
            fallback=[],
            body_builder=render_servers_panel,
        )

    def render_tasks_page(self, profile: BackendProfile, *, selected: str = "5") -> None:
        self.render_endpoint_page(
            profile,
            title="Executor Tasks",
            active="5",
            selected=selected,
            method="GET",
            path="/executor/tasks",
            fallback=[],
            body_builder=lambda data: render_tasks_panel(data, title="Executor Tasks"),
        )

    def render_detect_result_page(self, profile: BackendProfile, data: Any, error: str | None, *, selected: str = "6") -> None:
        errors = [error] if error else []
        backend_status = "offline" if error else "ok"
        body = render_json_panel(data, title="Detection Response") if self.rich_enabled else data
        self.render_page_shell(
            profile,
            title="Run Detection",
            active="r",
            selected=selected,
            body=body,
            errors=errors,
            backend_status=backend_status,
        )

    def render_placeholder_page(self, profile: BackendProfile, title: str, active: str, message: str, *, selected: str | None = None) -> None:
        body = gui_panel(Text(message, style=UI_MUTED), title=title, border_style=UI_BORDER) if self.rich_enabled else message
        self.render_page_shell(profile, title=title, active=active, selected=selected or active, body=body)

    def render_endpoint_page(
        self,
        profile: BackendProfile,
        *,
        title: str,
        active: str,
        selected: str,
        method: str,
        path: str,
        fallback: Any,
        body_builder: Callable[[Any], Any],
        payload: dict[str, Any] | None = None,
    ) -> None:
        data, error = dashboard_backend_json(profile, method, path, fallback, payload=payload)
        self.render_endpoint_data_page(
            profile,
            title=title,
            active=active,
            selected=selected,
            data=data,
            error=error,
            body_builder=body_builder,
        )

    def render_endpoint_data_page(
        self,
        profile: BackendProfile,
        *,
        title: str,
        active: str,
        selected: str,
        data: Any,
        error: str | None,
        body_builder: Callable[[Any], Any],
    ) -> None:
        errors = [error] if error else []
        backend_status = "offline" if error else "ok"
        body = body_builder(data) if self.rich_enabled else data
        self.render_page_shell(profile, title=title, active=active, selected=selected, body=body, errors=errors, backend_status=backend_status)

    def render_page_shell(
        self,
        profile: BackendProfile,
        *,
        title: str,
        active: str,
        selected: str,
        body: Any,
        errors: list[str] | None = None,
        backend_status: str = "checking",
    ) -> None:
        if self.rich_enabled and self.console is not None:
            compact = self.width < 130
            chrome = build_page_chrome(profile, title=title, backend_status=backend_status, errors=errors)
            main = Group(
                render_compact_nav_bar(active=active, selected=selected, width=self.width) if compact else Text(""),
                render_topbar_panel(chrome, title=title),
                render_backend_errors_panel(chrome),
                body,
            )
            if compact:
                self.console.print(main)
            else:
                shell = Table.grid(expand=True, padding=(0, 2))
                shell.add_column(width=28)
                shell.add_column(ratio=1)
                shell.add_row(render_sidebar_panel(chrome, active=active, selected=selected), main)
                self.console.print(shell)
            return

        self.rule(title)
        print(f"ProjectPilot | {title}", file=self.stream)
        if errors:
            print("Backend Error", file=self.stream)
            for error in errors:
                print(f"  {error}", file=self.stream)
            print(file=self.stream)
        if isinstance(body, (dict, list)):
            print(json.dumps(body, ensure_ascii=False, indent=2), file=self.stream)
        else:
            print(body, file=self.stream)

    def render_json(self, data: Any) -> None:
        if self.rich_enabled and self.console is not None:
            self.console.print(render_json_panel(data, title="Response"))
            return
        print(json.dumps(data, ensure_ascii=False, indent=2), file=self.stream)

    def render_projects(self, data: Any) -> None:
        if not isinstance(data, list):
            self.render_json(data)
            return
        if self.rich_enabled and self.console is not None:
            self.console.print(render_projects_panel(data))
            return
        self.render_plain_projects(data)

    def render_servers(self, data: Any) -> None:
        if not isinstance(data, list):
            self.render_json(data)
            return
        if self.rich_enabled and self.console is not None:
            self.console.print(render_servers_panel(data))
            return
        self.render_plain_servers(data)

    def render_tasks(self, data: Any, limit: int = 20, title: str = "Executor Tasks") -> None:
        if not isinstance(data, list):
            self.render_json(data)
            return
        if self.rich_enabled and self.console is not None:
            self.console.print(render_tasks_panel(data, limit=limit, title=title))
            return
        self.render_plain_tasks(data, limit=limit)

    def render_plain_projects(self, data: list[Any]) -> None:
        if not data:
            print("No projects.", file=self.stream)
            return
        print(f"{'ID':<5} {'Name':<22} Path", file=self.stream)
        print(f"{'-' * 5} {'-' * 22} {'-' * 36}", file=self.stream)
        for project in data:
            if not isinstance(project, dict):
                print(f"{'':<5} {clip(project, 22):<22}", file=self.stream)
                continue
            print(f"{str(project.get('id')):<5} {clip(project.get('name'), 22):<22} {project.get('path')}", file=self.stream)

    def render_plain_servers(self, data: list[Any]) -> None:
        if not data:
            print("No servers.", file=self.stream)
            return
        print(f"{'ID':<5} {'Name':<18} {'Mode':<12} Host", file=self.stream)
        print(f"{'-' * 5} {'-' * 18} {'-' * 12} {'-' * 30}", file=self.stream)
        for server in data:
            if not isinstance(server, dict):
                print(f"{'':<5} {clip(server, 18):<18}", file=self.stream)
                continue
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
            if not isinstance(task, dict):
                print(f"{'unknown':<10} {clip(task, 20):<20}", file=self.stream)
                continue
            task_type = task.get("task_type") or task.get("type")
            print(
                f"{clip(task.get('status'), 10):<10} {clip(task_type, 20):<20} "
                f"{clip(task.get('executor_id'), 12):<12} {task.get('id')}",
                file=self.stream,
            )
        if len(data) > limit:
            print(f"... {len(data) - limit} more tasks", file=self.stream)

    def render_plain_dashboard(self, dashboard: dict[str, Any]) -> None:
        self.rule("Dashboard")
        print("ProjectPilot | Dashboard", file=self.stream)
        print(f"Backend      {dashboard['backend_status']}", file=self.stream)
        print(f"Project      {dashboard['project_name']}", file=self.stream)
        print(f"Target       project {dashboard['project_id']} / server {dashboard['server_id']}", file=self.stream)
        print(file=self.stream)

        print("Metrics", file=self.stream)
        print(f"  Health Score       {dashboard['health_score']} / 100", file=self.stream)
        print(f"  Total Projects     {dashboard['project_count']}", file=self.stream)
        print(f"  Total Servers      {dashboard['server_count']}", file=self.stream)
        print(f"  Git Risks          {dashboard['git_risk_count']}", file=self.stream)
        print(f"  Environment Issues {dashboard['env_issue_count']}", file=self.stream)
        print(file=self.stream)

        if dashboard["errors"]:
            print("Backend Error", file=self.stream)
            for error in dashboard["errors"]:
                print(f"  {error}", file=self.stream)
            print(file=self.stream)

        print("Server Health Overview", file=self.stream)
        self.render_plain_server_health(dashboard["status_servers"])
        print(file=self.stream)

        print("Git & Environment Matrix", file=self.stream)
        self.render_plain_status_matrix(dashboard["status_servers"])
        print(file=self.stream)

        print("Recent Activity", file=self.stream)
        self.render_plain_activity(dashboard["activities"])
        print(file=self.stream)

        print("AI Recommendation", file=self.stream)
        for step in dashboard["steps"]:
            print(f"  {step['order']}. {step['title']} - {step['detail']} [{step['risk']}]", file=self.stream)

    def render_plain_server_health(self, servers: list[dict[str, Any]]) -> None:
        if not servers:
            print("No bound servers returned.", file=self.stream)
            return
        print(f"{'Server':<18} {'Status':<9} {'Branch':<14} {'Python':<12} {'Docker':<10} Last Scan", file=self.stream)
        print(f"{'-' * 18} {'-' * 9} {'-' * 14} {'-' * 12} {'-' * 10} {'-' * 18}", file=self.stream)
        for server in servers:
            git = git_display(server)
            env = environment_display(server)
            print(
                f"{clip(server_name(server), 18):<18} {status_tone(server):<9} "
                f"{clip(git['branch'], 14):<14} {clip(env['python'], 12):<12} "
                f"{clip(env['docker'], 10):<10} {compact_time(latest_server_scan_time(server))}",
                file=self.stream,
            )

    def render_plain_status_matrix(self, servers: list[dict[str, Any]]) -> None:
        if not servers:
            print("No status matrix returned.", file=self.stream)
            return
        print(f"{'Environment':<18} {'Project Path':<30} {'Branch':<14} {'Commit':<14} {'Node':<10}", file=self.stream)
        print(f"{'-' * 18} {'-' * 30} {'-' * 14} {'-' * 14} {'-' * 10}", file=self.stream)
        for server in servers:
            git = git_display(server)
            env = environment_display(server)
            print(
                f"{clip(server_name(server), 18):<18} {clip(server_project_path(server), 30):<30} "
                f"{clip(git['branch'], 14):<14} {clip(git['commit'], 14):<14} {clip(env['node'], 10):<10}",
                file=self.stream,
            )

    def render_plain_activity(self, activities: list[dict[str, Any]]) -> None:
        if not activities:
            print("No recent activity returned.", file=self.stream)
            return
        for item in activities[:8]:
            print(
                f"  [{display_value(item.get('risk_level'))}] {display_value(item.get('summary'))} "
                f"({display_value(item.get('operation_type'))}, {display_value(item.get('status'))})",
                file=self.stream,
            )


def render_dashboard(profile: BackendProfile, stream: TextIO, ui: ConsoleUI, *, selected: str = "1") -> None:
    ui.render_dashboard(profile, selected=selected)


def print_json(data: Any, stream: TextIO) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_json(data)


def print_projects(data: Any, stream: TextIO) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_projects(data)


def print_servers(data: Any, stream: TextIO) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_servers(data)


def print_tasks(data: Any, stream: TextIO, limit: int = 20) -> None:
    ConsoleUI(stream, rich_enabled=stream_is_tty(stream) and RICH_AVAILABLE).render_tasks(data, limit=limit)


def build_dashboard_data(
    profile: BackendProfile,
    health: Any,
    projects: Any,
    servers: Any,
    tasks: Any,
    status: Any,
    activities: Any,
    *,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    status_available = isinstance(status, dict) and isinstance(status.get("servers"), list)
    status_servers = current_status_servers(status, servers)
    git_risk_count = sum(1 for server in status_servers if git_display(server)["is_risk"]) if status_available else None
    env_issue_count = sum(1 for server in status_servers if environment_display(server)["is_issue"]) if status_available else None
    health_score = (
        "-"
        if not status_available or not status_servers
        else str(max(35, 100 - int(git_risk_count) * 9 - int(env_issue_count) * 12))
    )
    backend_status = display_value(health.get("status") if isinstance(health, dict) else None)
    selected_project = selected_project_summary(profile, projects, status)

    return {
        "title": "Dashboard",
        "backend_status": backend_status,
        "project_id": selected_project.get("id", profile.default_project_id),
        "project_name": display_value(selected_project.get("name")),
        "server_id": profile.default_server_id,
        "project_count": str(len(projects)) if isinstance(projects, list) else "-",
        "server_count": str(len(servers)) if isinstance(servers, list) else "-",
        "task_count": str(len(tasks)) if isinstance(tasks, list) else "-",
        "status_servers": status_servers,
        "git_risk_count": str(git_risk_count) if git_risk_count is not None else "-",
        "env_issue_count": str(env_issue_count) if env_issue_count is not None else "-",
        "health_score": health_score,
        "health_style": health_score_style(health_score),
        "activities": activities if isinstance(activities, list) else [],
        "errors": errors or [],
        "steps": dashboard_steps(profile, git_risk_count or 0, env_issue_count or 0),
        "last_sync": latest_dashboard_time(status_servers, activities if isinstance(activities, list) else []),
    }


def build_page_chrome(
    profile: BackendProfile,
    *,
    title: str,
    backend_status: str = "checking",
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "backend_status": backend_status,
        "project_id": profile.default_project_id,
        "project_name": f"Project {profile.default_project_id}",
        "server_id": profile.default_server_id,
        "task_count": "-",
        "errors": errors or [],
        "last_sync": None,
    }


def current_status_servers(status: Any, servers: Any) -> list[dict[str, Any]]:
    if isinstance(status, dict) and isinstance(status.get("servers"), list):
        return [item for item in status["servers"] if isinstance(item, dict)]
    if isinstance(servers, list):
        return [item for item in servers if isinstance(item, dict)]
    return []


def selected_project_summary(profile: BackendProfile, projects: Any, status: Any) -> dict[str, Any]:
    if isinstance(status, dict) and isinstance(status.get("project"), dict):
        return status["project"]
    if isinstance(projects, list):
        for project in projects:
            if isinstance(project, dict) and project.get("id") == profile.default_project_id:
                return project
        for project in projects:
            if isinstance(project, dict):
                return project
    return {"id": profile.default_project_id, "name": None}


def dashboard_steps(profile: BackendProfile, git_risks: int, env_issues: int) -> list[dict[str, str]]:
    risk = "medium" if git_risks or env_issues else "low"
    return [
        {
            "order": "1",
            "title": "Run Detection",
            "detail": f"project {profile.default_project_id} / server {profile.default_server_id}",
            "risk": risk,
        },
        {
            "order": "2",
            "title": "Review Task Stream",
            "detail": "check queued, running, failed executor work",
            "risk": "low",
        },
        {
            "order": "3",
            "title": "Open AI Ops",
            "detail": "refresh analysis and configuration plan in the GUI",
            "risk": "low",
        },
    ]


def health_score_style(score: str) -> str:
    if score == "-":
        return UI_YELLOW
    try:
        value = int(score)
    except ValueError:
        return UI_YELLOW
    if value >= 80:
        return UI_GREEN
    if value >= 55:
        return UI_YELLOW
    return UI_RED


def gui_panel(
    body: Any,
    *,
    title: str | None = None,
    border_style: str = UI_BORDER,
    style: str = f"{UI_TEXT} on {UI_PANEL}",
    padding: tuple[int, int] = (1, 2),
) -> Any:
    return Panel(
        body,
        title=title,
        border_style=border_style,
        box=box.SQUARE,
        style=style,
        padding=padding,
    )


def badge_text(label: str, tone: str) -> Any:
    color, background = {
        "healthy": (UI_GREEN, UI_BADGE_GREEN),
        "online": (UI_GREEN, UI_BADGE_GREEN),
        "ok": (UI_GREEN, UI_BADGE_GREEN),
        "warning": (UI_YELLOW, UI_BADGE_YELLOW),
        "checking": (UI_YELLOW, UI_BADGE_YELLOW),
        "offline": (UI_RED, UI_BADGE_RED),
        "error": (UI_RED, UI_BADGE_RED),
        "danger": (UI_RED, UI_BADGE_RED),
        "unknown": (UI_MUTED, UI_BADGE_MUTED),
        "muted": (UI_MUTED, UI_BADGE_MUTED),
    }.get(tone, (UI_MUTED, UI_BADGE_MUTED))
    return Text(f" {label} ", style=f"bold {color} on {background}")


def backend_badge(dashboard: dict[str, Any]) -> Any:
    status = str(dashboard["backend_status"]).lower()
    if status == "ok":
        return badge_text("Backend online", "online")
    if status in {"offline", "error"}:
        return badge_text("Backend error", "error")
    return badge_text("Checking API", "checking")


def docker_style(value: str) -> str:
    if value == "running":
        return UI_GREEN
    if value in {"missing", "stopped"}:
        return UI_YELLOW
    return UI_MUTED


def git_branch_style(server: dict[str, Any]) -> str:
    git = git_display(server)
    if git["is_risk"]:
        return UI_YELLOW
    if git["is_missing"]:
        return UI_MUTED
    return UI_TEXT


def server_meta(server: dict[str, Any]) -> str:
    host = display_value(server.get("host"))
    port = display_value(server.get("port"))
    mode = display_value(server.get("connection_mode"))
    if host == "-" and mode == "-":
        return server_project_path(server)
    if port != "-":
        host = f"{host}:{port}"
    return " / ".join(part for part in [host, mode] if part and part != "-") or "-"


def render_sidebar_panel(dashboard: dict[str, Any], *, active: str = "1", selected: str = "1") -> Any:
    brand = Table.grid(padding=(0, 1))
    brand.add_column(width=4, no_wrap=True)
    brand.add_column(ratio=1)
    brand.add_row(
        Text(" P ", style=f"bold #06110f on {UI_GREEN}"),
        Group(
            Text("ProjectPilot", style=f"bold {UI_TEXT}"),
            Text("AI Project Health Monitor", style=UI_MUTED),
        ),
    )

    nav = Table.grid()
    nav.add_column(width=22, no_wrap=True)
    _ = active
    selected_key = normalize_nav_key(selected) or "1"
    for marker, label, icon in NAV_ITEMS:
        normalized_marker = marker.lower()
        prefix = marker if marker.isdigit() else icon
        cursor = ">" if normalized_marker == selected_key else " "
        text = f"{cursor}{prefix:<2} {label:<14}"
        if normalized_marker == selected_key:
            style = f"bold {UI_WHITE} on {UI_PRIMARY}"
        else:
            style = f"{UI_NAV_TEXT} on {UI_SIDEBAR}"
        nav.add_row(Text(text, style=style))

    side_version = gui_panel(
        Group(
            Text("Desktop Preview", style=f"bold {UI_TEXT}"),
            Text("v0.1.0", style=UI_MUTED),
            Text(f"Tasks {dashboard['task_count']}", style=UI_MUTED),
            Text(f"Selected {nav_label(selected_key)}", style=UI_MUTED),
        ),
        border_style=UI_BORDER_MUTED,
        style=f"{UI_TEXT} on {UI_PANEL}",
        padding=(1, 1),
    )

    side = Group(
        brand,
        Text(""),
        nav,
        Text(""),
        side_version,
    )
    return gui_panel(
        side,
        border_style=UI_BORDER_MUTED,
        style=f"{UI_TEXT} on {UI_SIDEBAR}",
        padding=(1, 1),
    )


def render_compact_nav_bar(*, active: str = "1", selected: str = "1", width: int = 120) -> Any:
    _ = active
    selected_key = normalize_nav_key(selected) or "1"
    line = Text()
    used_width = 0
    content_width = max(20, width - 6)
    labels = {
        "Dashboard": "Dash",
        "Projects": "Proj",
        "Servers": "Serv",
        "Bindings": "Bind",
        "AI Ops": "AI",
        "Tasks": "Tasks",
        "API Map": "Map",
        "Settings": "Set",
    }
    for marker, label, icon in NAV_ITEMS:
        key = marker.lower()
        prefix = marker if marker.isdigit() else icon
        if width < 90:
            segment = f" {prefix} "
        else:
            visible_label = labels.get(label, label) if width < 110 else label
            segment = f" {prefix} {visible_label} "
        if used_width + len(segment) > content_width:
            break
        if key == selected_key:
            line.append(segment, style=f"bold {UI_WHITE} on {UI_PRIMARY}")
        else:
            line.append(segment, style=f"{UI_MUTED} on {UI_BG}")
        used_width += len(segment)
    return gui_panel(line, border_style=UI_BORDER_MUTED, style=f"{UI_TEXT} on {UI_BG}", padding=(0, 1))


def render_topbar_panel(dashboard: dict[str, Any], *, title: str | None = None) -> Any:
    page_title = title or str(dashboard.get("title") or "Dashboard")
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(justify="right", no_wrap=True)
    title = Group(
        Text(f"LAST SYNC {compact_time(dashboard['last_sync'])}", style=UI_MUTED),
        Text(f"ProjectPilot | {page_title}", style=f"bold {UI_TEXT}"),
    )
    actions = Table.grid(padding=(0, 1))
    actions.add_column(no_wrap=True)
    actions.add_column(no_wrap=True)
    actions.add_column(no_wrap=True)
    actions.add_row(
        Text(f" {dashboard['project_name']} ", style=f"{UI_TEXT} on {UI_PANEL}"),
        backend_badge(dashboard),
        Text(" EP  Admin ", style=f"bold {UI_TEXT} on {UI_PANEL_ALT}"),
    )
    grid.add_row(title, actions)
    return gui_panel(grid, border_style=UI_BORDER_MUTED, style=f"{UI_TEXT} on {UI_BG}", padding=(1, 2))


def render_backend_errors_panel(dashboard: dict[str, Any]) -> Any:
    errors = dashboard.get("errors") or []
    if not errors:
        return Text("")
    message = "\n".join(f"- {error}" for error in errors[:3])
    return Group(
        gui_panel(
            Text(message, style=UI_YELLOW),
            title="Backend Error",
            border_style=UI_YELLOW,
            style=f"{UI_YELLOW} on {UI_PANEL}",
        ),
        Text(""),
    )


def render_json_panel(data: Any, *, title: str = "Response") -> Any:
    return gui_panel(RichJSON.from_data(data), title=title, border_style=UI_BORDER)


def render_projects_panel(data: Any) -> Any:
    if not isinstance(data, list):
        return render_json_panel(data, title="Projects Response")
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("ID", style=UI_CYAN, no_wrap=True)
    table.add_column("Name", style=f"bold {UI_TEXT}")
    table.add_column("Path", style=UI_MUTED)
    table.add_column("Description", style=UI_MUTED)
    for project in data:
        if not isinstance(project, dict):
            table.add_row("", display_value(project), "", "")
            continue
        table.add_row(
            str(project.get("id") or ""),
            str(project.get("name") or ""),
            str(project.get("path") or ""),
            str(project.get("description") or ""),
        )
    body = table if data else Text("No projects returned.", style=UI_MUTED)
    return gui_panel(body, title="Projects", border_style=UI_BORDER)


def render_servers_panel(data: Any) -> Any:
    if not isinstance(data, list):
        return render_json_panel(data, title="Servers Response")
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("ID", style=UI_CYAN, no_wrap=True)
    table.add_column("Name", style=f"bold {UI_TEXT}")
    table.add_column("Mode", style=UI_TEXT)
    table.add_column("Host", style=UI_MUTED)
    table.add_column("User", style=UI_MUTED)
    for server in data:
        if not isinstance(server, dict):
            table.add_row("", display_value(server), "", "", "")
            continue
        table.add_row(
            str(server.get("id") or ""),
            str(server.get("name") or ""),
            str(server.get("connection_mode") or ""),
            str(server.get("host") or ""),
            str(server.get("username") or ""),
        )
    body = table if data else Text("No servers returned.", style=UI_MUTED)
    return gui_panel(body, title="Servers", border_style=UI_BORDER)


def render_tasks_panel(data: Any, *, limit: int = 20, title: str = "Executor Tasks") -> Any:
    if not isinstance(data, list):
        return render_json_panel(data, title=f"{title} Response")
    counts = count_task_statuses(data)
    summary = "  ".join(f"{key} {value}" for key, value in sorted(counts.items())) or "empty"
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("Status", no_wrap=True)
    table.add_column("Type", style=UI_TEXT)
    table.add_column("Executor", style=UI_TEXT)
    table.add_column("Task", style=UI_MUTED)
    for task in data[:limit]:
        if not isinstance(task, dict):
            table.add_row(badge_text("unknown", "muted"), display_value(task), "", "")
            continue
        task_type = str(task.get("task_type") or task.get("type") or "")
        status = str(task.get("status") or "unknown")
        table.add_row(
            badge_text(status, task_status_tone(status)),
            task_type,
            str(task.get("executor_id") or ""),
            str(task.get("id") or ""),
        )
    if len(data) > limit:
        table.caption = f"{len(data) - limit} more tasks hidden"
    body = table if data else Text("No executor tasks returned.", style=UI_MUTED)
    return gui_panel(body, title=f"{title} ({summary})", border_style=UI_BORDER)


def render_bindings_panel(data: Any) -> Any:
    if not isinstance(data, list):
        return render_json_panel(data, title="Bindings Response")
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("Server", style=f"bold {UI_TEXT}", ratio=2)
    table.add_column("Host", style=UI_TEXT, ratio=2)
    table.add_column("User", style=UI_MUTED, ratio=1)
    table.add_column("Mode", no_wrap=True)
    table.add_column("Project Path", style=UI_MUTED, ratio=3)
    table.add_column("Bound At", style=UI_MUTED, ratio=1)
    for binding in data:
        if not isinstance(binding, dict):
            table.add_row(display_value(binding), "", "", "", "", "")
            continue
        host = display_value(binding.get("host"))
        port = display_value(binding.get("port"))
        host_label = f"{host}:{port}" if host != "-" and port != "-" else host
        server_label = display_value(binding.get("server_name") or binding.get("name") or binding.get("server_id"))
        server_id = display_value(binding.get("server_id"))
        table.add_row(
            Text.assemble((server_label, f"bold {UI_TEXT}"), "\n", (f"ID {server_id}", UI_MUTED)),
            host_label,
            display_value(binding.get("username")),
            badge_text(display_value(binding.get("connection_mode")), "muted"),
            display_value(binding.get("project_path")),
            compact_time(binding.get("created_at")),
        )
    body = table if data else Text("No project-server bindings returned.", style=UI_MUTED)
    bind_help = gui_panel(
        Group(
            Text("Bind Server", style=f"bold {UI_TEXT}"),
            Text("POST /projects/{id}/bind-server", style=UI_MUTED),
            Text("Payload: server_id, project_path", style=UI_MUTED),
        ),
        title="Actions",
        border_style=UI_BORDER_MUTED,
        padding=(1, 1),
    )
    return Columns(
        [
            gui_panel(body, title="Project Server Bindings", border_style=UI_BORDER),
            bind_help,
        ],
        padding=(0, 1),
        expand=True,
    )


def render_ai_ops_panel(data: Any) -> Any:
    if not isinstance(data, dict):
        return render_json_panel(data, title="AI Settings Response")
    settings = Table.grid(padding=(0, 2))
    settings.add_column(style=UI_MUTED, no_wrap=True)
    settings.add_column(style=f"bold {UI_TEXT}")
    settings.add_row("Provider", display_value(data.get("provider") or data.get("ai_provider")))
    settings.add_row("Model", display_value(data.get("model") or data.get("ai_model")))
    settings.add_row("API Key", boolean_display(data.get("api_key_configured", data.get("has_api_key"))))
    settings.add_row("Status", display_value(data.get("status")))

    action_plan = gui_panel(
        Group(
            Text("AI Action Plan", style=f"bold {UI_TEXT}"),
            Text("POST /projects/{id}/ai/plan-action", style=UI_MUTED),
            Text("Goal, source server, target server, confirmation", style=UI_MUTED),
        ),
        title="AI Action Plan",
        border_style=UI_BORDER,
        padding=(1, 1),
    )
    config_plan = gui_panel(
        Group(
            Text("Config Plan", style=f"bold {UI_TEXT}"),
            Text("POST /projects/{id}/ai/config-plan", style=UI_MUTED),
            Text("Generate and execute server configuration plans.", style=UI_MUTED),
        ),
        title="Config Plan",
        border_style=UI_BORDER,
        padding=(1, 1),
    )
    git_ai = gui_panel(
        Group(
            Text("Git AI", style=f"bold {UI_TEXT}"),
            Text("POST /projects/{id}/ai/analyze-git", style=UI_MUTED),
            Text("Analyze repository risk before executor work.", style=UI_MUTED),
        ),
        title="Git AI",
        border_style=UI_BORDER,
        padding=(1, 1),
    )
    report = gui_panel(
        Group(
            Text("AI Report", style=f"bold {UI_TEXT}"),
            Text("POST /reports/project", style=UI_MUTED),
            Text("Markdown report output is generated by the backend.", style=UI_MUTED),
        ),
        title="AI Report",
        border_style=UI_BORDER,
        padding=(1, 1),
    )
    return Group(
        Columns(
            [
                gui_panel(settings, title="AI Settings", border_style=UI_BORDER),
                action_plan,
            ],
            padding=(0, 1),
            expand=True,
        ),
        Text(""),
        Columns([config_plan, git_ai, report], padding=(0, 1), expand=True),
    )


def render_api_map_panel(data: Any) -> Any:
    rows = data if isinstance(data, (list, tuple)) else API_CONTRACT
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("Method", no_wrap=True, style=UI_CYAN)
    table.add_column("Endpoint", style=UI_TEXT, ratio=3)
    table.add_column("Status", no_wrap=True)
    table.add_column("Use", style=UI_MUTED, ratio=2)
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            table.add_row("", display_value(row), "", "")
            continue
        method, endpoint, status, use = row[:4]
        status_text = display_value(status)
        tone = "healthy" if status_text in {"connected", "已接入"} else "warning"
        table.add_row(
            Text(display_value(method), style=f"bold {UI_CYAN}"),
            Text(display_value(endpoint), style=UI_TEXT),
            badge_text(status_text, tone),
            display_value(use),
        )
    return gui_panel(table, title="Frontend API Contract", border_style=UI_BORDER)


def render_settings_panel(data: Any) -> Any:
    if not isinstance(data, dict):
        return render_json_panel(data, title="Settings Response")
    health = data.get("health") if isinstance(data.get("health"), dict) else {}
    backend = Table.grid(padding=(0, 2))
    backend.add_column(style=UI_MUTED, no_wrap=True)
    backend.add_column(style=f"bold {UI_TEXT}")
    backend.add_row("API Base URL", display_value(data.get("server_url")))
    backend.add_row("Token", display_value(data.get("token")))
    backend.add_row("Default Project", display_value(data.get("default_project_id")))
    backend.add_row("Default Server", display_value(data.get("default_server_id")))
    backend.add_row("Timeout", f"{display_value(data.get('timeout'))}s")
    backend.add_row("Health", display_value(health.get("status")))

    session = Table.grid(padding=(0, 2))
    session.add_column(style=UI_MUTED, no_wrap=True)
    session.add_column(style=f"bold {UI_TEXT}")
    session.add_row("Session", "Local console")
    session.add_row("Role", "EP Admin")
    session.add_row("Executor", "projectpilot executor server-b")
    session.add_row("Detection", "R or 6")
    return Columns(
        [
            gui_panel(backend, title="Backend Connection", border_style=UI_BORDER),
            gui_panel(session, title="Session", border_style=UI_BORDER),
        ],
        padding=(0, 1),
        expand=True,
    )


def render_metric_cards(dashboard: dict[str, Any], *, compact: bool = False) -> Any:
    cards = [
        metric_card("Health Score", dashboard["health_score"], "/ 100", dashboard["health_style"]),
        metric_card("Total Projects", dashboard["project_count"], "Active projects", UI_PURPLE),
        metric_card("Total Servers", dashboard["server_count"], "Monitored servers", UI_PURPLE),
        metric_card("Git Risks", dashboard["git_risk_count"], "Repositories at risk", UI_YELLOW),
        metric_card("Environment Issues", dashboard["env_issue_count"], "Servers with issues", UI_RED),
    ]
    if not compact:
        return Columns(cards, padding=(0, 1), expand=True)

    first_row = Columns(cards[:3], equal=True, expand=True)
    second_row = Columns(cards[3:], equal=True, expand=True)
    return Group(first_row, second_row)


def render_compact_dashboard_summary(dashboard: dict[str, Any]) -> Any:
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("Health", style=f"bold {dashboard['health_style']}", justify="right")
    table.add_column("Projects", style=UI_TEXT, justify="right")
    table.add_column("Servers", style=UI_TEXT, justify="right")
    table.add_column("Git Risks", style=UI_YELLOW, justify="right")
    table.add_column("Env Issues", style=UI_RED, justify="right")
    table.add_row(
        str(dashboard["health_score"]),
        str(dashboard["project_count"]),
        str(dashboard["server_count"]),
        str(dashboard["git_risk_count"]),
        str(dashboard["env_issue_count"]),
    )
    return gui_panel(table, title="Overview", border_style=UI_BORDER)


def render_dashboard_content(dashboard: dict[str, Any], *, compact: bool = False, short: bool = False) -> Any:
    if compact:
        content = [
            render_server_health_panel(dashboard["status_servers"], compact=True),
            Text(""),
            render_activity_panel(dashboard["activities"], limit=3),
        ]
        if not short:
            content.extend([Text(""), render_insight_panel(dashboard)])
        return Group(*content)

    insight_row = Table.grid(expand=True, padding=(0, 1))
    insight_row.add_column(ratio=1)
    insight_row.add_column(ratio=1)
    insight_row.add_row(render_insight_panel(dashboard), render_activity_panel(dashboard["activities"]))

    return Group(
        render_server_health_panel(dashboard["status_servers"]),
        Text(""),
        render_matrix_panel(dashboard["status_servers"]),
        Text(""),
        insight_row,
        Text(""),
        render_steps_panel(dashboard["steps"]),
    )


def render_server_health_panel(servers: list[dict[str, Any]], *, compact: bool = False) -> Any:
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("Server", style=f"bold {UI_TEXT}", ratio=2)
    table.add_column("Status", no_wrap=True, style=UI_TEXT)
    table.add_column("Branch", ratio=1, style=UI_TEXT)
    table.add_column("Python", ratio=1, style=UI_TEXT)
    if not compact:
        table.add_column("Docker", ratio=1, style=UI_TEXT)
        table.add_column("Last Scan", ratio=1, style=UI_MUTED)
    for server in servers[:8]:
        git = git_display(server)
        env = environment_display(server)
        tone = status_tone(server)
        server_cell = Text.assemble(
            (server_name(server), f"bold {UI_TEXT}"),
            "\n",
            (server_meta(server), UI_MUTED),
        )
        row = [
            server_cell,
            badge_text(tone.title(), tone),
            Text(git["branch"], style=git_branch_style(server)),
            env["python"],
        ]
        if not compact:
            row.extend(
                [
                    Text(env["docker"], style=docker_style(env["docker"])),
                    compact_time(latest_server_scan_time(server)),
                ]
            )
        table.add_row(*row)
    body = table if servers else Text("No bound servers returned.", style=UI_MUTED)
    return gui_panel(body, title="Server Health Overview", border_style=UI_BORDER)


def render_insight_panel(dashboard: dict[str, Any]) -> Any:
    issues: list[str] = []
    if dashboard["git_risk_count"] not in {"-", "0"}:
        issues.append(f"{dashboard['git_risk_count']} repositories need Git review.")
    if dashboard["env_issue_count"] not in {"-", "0"}:
        issues.append(f"{dashboard['env_issue_count']} servers have environment issues.")
    if not issues:
        issues.append("No active server matrix issues were returned.")

    body = Group(
        Text(f"{dashboard['project_name']} current risk", style=f"bold {UI_TEXT}"),
        Text("\n".join(f"- {issue}" for issue in issues), style=UI_MUTED),
        badge_text(f"Risk Level: {risk_level_label(dashboard)}", risk_level_label(dashboard)),
    )
    return gui_panel(body, title="AI Insight", border_style=UI_PURPLE, style=f"{UI_TEXT} on #20204b")


def render_matrix_panel(servers: list[dict[str, Any]], *, compact: bool = False) -> Any:
    table = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, show_edge=False)
    table.add_column("Environment", style=f"bold {UI_TEXT}", ratio=2)
    table.add_column("Project Path", ratio=3, style=UI_TEXT)
    table.add_column("Branch", ratio=1, style=UI_TEXT)
    if not compact:
        table.add_column("Commit", ratio=1, style=UI_MUTED)
    table.add_column("Python", ratio=1, style=UI_TEXT)
    if not compact:
        table.add_column("Node", ratio=1, style=UI_TEXT)
    table.add_column("Status", ratio=1, style=UI_TEXT)
    for server in servers[:8]:
        git = git_display(server)
        env = environment_display(server)
        tone = status_tone(server)
        if compact:
            table.add_row(
                server_name(server),
                server_project_path(server),
                Text(git["branch"], style=git_branch_style(server)),
                env["python"],
                badge_text(tone.title(), tone),
            )
        else:
            table.add_row(
                server_name(server),
                server_project_path(server),
                Text(git["branch"], style=git_branch_style(server)),
                git["commit"],
                env["python"],
                env["node"],
                badge_text(tone.title(), tone),
            )
    body = table if servers else Text("No status matrix returned.", style=UI_MUTED)
    return gui_panel(body, title="Git & Environment Matrix", border_style=UI_BORDER)


def render_activity_panel(activities: list[dict[str, Any]], *, limit: int = 8) -> Any:
    if not activities:
        return gui_panel(Text("No recent activity returned.", style=UI_MUTED), title="Recent Activity", border_style=UI_BORDER)
    rows = []
    for item in activities[:limit]:
        risk = display_value(item.get("risk_level"))
        summary = display_value(item.get("summary"))
        operation = display_value(item.get("operation_type"))
        status = display_value(item.get("status"))
        rows.append(
            Text.assemble(
                ("o ", risk_style(risk)),
                (f"{summary}\n", f"bold {UI_TEXT}"),
                ("  " + f"{operation} / {status}", UI_MUTED),
            )
        )
    return gui_panel(Group(*rows), title="Recent Activity", border_style=UI_BORDER)


def render_steps_panel(steps: list[dict[str, str]], *, compact: bool = False) -> Any:
    cards = []
    for step in steps:
        layout = Table.grid(expand=True, padding=(0, 1))
        layout.add_column(width=4, no_wrap=True)
        layout.add_column(ratio=1)
        layout.add_column(justify="right", no_wrap=True)
        layout.add_row(
            Text(f" {step['order']} ", style=f"bold {UI_WHITE} on #5145c6"),
            Group(
                Text(step["title"], style=f"bold {UI_TEXT}"),
                Text(step["detail"], style=UI_MUTED),
            ),
            Text(step["risk"], style=f"bold {risk_style(step['risk'])}"),
        )
        cards.append(gui_panel(layout, border_style=UI_BORDER_MUTED, style=f"{UI_TEXT} on #141b32", padding=(1, 1)))
    content = Group(*cards) if compact else Columns(cards, padding=(0, 1), width=38, expand=True)
    return gui_panel(content, title="AI Recommendation", border_style=UI_BORDER)


def metric_card(label: str, value: str, caption: str, style: str = UI_CYAN) -> Any:
    body = Group(
        Text(label, style=f"bold {UI_GREEN}"),
        Text(str(value), style=f"bold {style}"),
        Text(caption, style=UI_MUTED),
    )
    return gui_panel(body, border_style=UI_BORDER, style=f"{UI_TEXT} on {UI_PANEL}", padding=(0, 1))


def task_status_tone(status: str) -> str:
    normalized = status.lower()
    if normalized in {"succeeded", "completed", "success", "done"}:
        return "healthy"
    if normalized in {"running", "claimed", "in_progress"}:
        return "warning"
    if normalized in {"queued", "pending"}:
        return "warning"
    if normalized in {"failed", "error"}:
        return "danger"
    return "muted"


def display_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def boolean_display(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return display_value(value)


def server_name(server: dict[str, Any]) -> str:
    return display_value(server.get("server_name") or server.get("name"))


def server_project_path(server: dict[str, Any]) -> str:
    return display_value(server.get("project_path") or server.get("path"))


def git_display(server: dict[str, Any]) -> dict[str, Any]:
    git_status = server.get("latest_git_status")
    if not isinstance(git_status, dict):
        git_status = server.get("git_status") if isinstance(server.get("git_status"), dict) else {}
    branch = display_value(git_status.get("branch") or server.get("branch"))
    commit = display_value(git_status.get("last_commit") or git_status.get("commit") or server.get("last_commit"))
    ahead = numeric_value(git_status.get("ahead") or server.get("ahead"))
    behind = numeric_value(git_status.get("behind") or server.get("behind"))
    dirty = bool(git_status.get("has_uncommitted_changes") or server.get("has_uncommitted_changes"))
    missing = branch == "-"
    return {
        "branch": branch,
        "commit": commit,
        "is_risk": not missing and (dirty or ahead > 0 or behind > 0),
        "is_missing": missing,
    }


def environment_display(server: dict[str, Any]) -> dict[str, Any]:
    snapshot = server.get("latest_environment_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = server.get("environment") if isinstance(server.get("environment"), dict) else {}
    python = display_value(snapshot.get("python_version"))
    node = display_value(snapshot.get("node_version"))
    docker_installed = snapshot.get("docker_installed")
    docker_running = snapshot.get("docker_running")
    if docker_running is True:
        docker = "running"
    elif docker_installed is True:
        docker = "stopped"
    elif docker_installed is False:
        docker = "missing"
    else:
        docker = "-"
    return {
        "python": python,
        "node": node,
        "docker": docker,
        "is_issue": python == "-" or docker in {"missing", "stopped"},
    }


def status_tone(server: dict[str, Any]) -> str:
    git = git_display(server)
    env = environment_display(server)
    if git["is_missing"] or env["python"] == "-":
        return "unknown"
    if git["is_risk"] or env["is_issue"]:
        return "warning"
    return "healthy"


def risk_level_label(dashboard: dict[str, Any]) -> str:
    if dashboard["git_risk_count"] in {"-", "0"} and dashboard["env_issue_count"] in {"-", "0"}:
        return "low"
    if dashboard["git_risk_count"] == "-" and dashboard["env_issue_count"] == "-":
        return "unknown"
    return "medium"


def risk_style(risk: str) -> str:
    normalized = risk.lower()
    if normalized in {"low", "healthy", "completed", "success", "ok"}:
        return UI_GREEN
    if normalized in {"medium", "warning", "queued", "running"}:
        return UI_YELLOW
    if normalized in {"high", "danger", "failed", "error"}:
        return UI_RED
    return UI_MUTED


def numeric_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def latest_server_scan_time(server: dict[str, Any]) -> Any:
    git_status = server.get("latest_git_status")
    snapshot = server.get("latest_environment_snapshot")
    candidates = []
    if isinstance(git_status, dict):
        candidates.append(git_status.get("created_at"))
    if isinstance(snapshot, dict):
        candidates.append(snapshot.get("created_at"))
    candidates.append(server.get("updated_at"))
    candidates.append(server.get("created_at"))
    return next((item for item in candidates if item), None)


def latest_dashboard_time(servers: list[dict[str, Any]], activities: list[dict[str, Any]]) -> Any:
    candidates = [latest_server_scan_time(server) for server in servers]
    candidates.extend(activity.get("created_at") for activity in activities if isinstance(activity, dict))
    return next((item for item in candidates if item), None)


def compact_time(value: Any) -> str:
    text = display_value(value)
    if text == "-":
        return "-"
    if "T" in text:
        date, rest = text.split("T", 1)
        return f"{date} {rest[:5]}"
    if len(text) > 16:
        return text[:16]
    return text


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
