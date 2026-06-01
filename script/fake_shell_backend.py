#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from projectpilot.executor.backend import ExecutorBackendStore  # noqa: E402


DEFAULT_SCRIPT = """set -euo pipefail
echo PROJECTPILOT_FAKE_BACKEND_OK
whoami
pwd
uname -a
date
"""


class FakeShellBackend:
    def __init__(self, *, token: str, storage_path: Path, default_project_path: Path) -> None:
        self.token = token
        self.store = ExecutorBackendStore(storage_path)
        self.default_project_path = default_project_path


def create_server(host: str, port: int, state: FakeShellBackend) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.write_json({"success": True, "status": "ok"})
                return
            if self.path in {"/", "/index.html"}:
                self.write_html(render_index(state))
                return
            if self.path == "/tasks":
                self.write_json({"success": True, "tasks": state.store.list_tasks()})
                return
            if self.path == "/state":
                self.write_json({"success": True, "state": state.store.snapshot()})
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path == "/executor/poll":
                if not self.require_auth(state):
                    return
                self.handle_executor_poll(state)
                return

            match = re.fullmatch(r"/executor/tasks/([^/]+)/result", self.path)
            if match:
                if not self.require_auth(state):
                    return
                self.handle_task_result(state, match.group(1))
                return

            if self.path in {"/send-shell", "/tasks"}:
                self.handle_send_shell(state)
                return

            self.send_error(404)

        def handle_executor_poll(self, app_state: FakeShellBackend) -> None:
            try:
                payload = self.read_json()
                executor = app_state.store.record_executor_poll(payload)
                task = app_state.store.claim_next_task(
                    executor["executor_id"],
                    [str(item) for item in payload.get("capabilities") or []],
                )
                self.write_json({"task": task})
            except ValueError as exc:
                self.write_json({"success": False, "error_type": "invalid_poll", "message": str(exc)}, status=400)

        def handle_task_result(self, app_state: FakeShellBackend, task_id: str) -> None:
            try:
                payload = self.read_json()
                task = app_state.store.complete_task(task_id, payload)
                self.write_json({"success": True, "task": task})
            except KeyError:
                self.write_json({"success": False, "error_type": "task_not_found", "message": task_id}, status=404)
            except PermissionError as exc:
                self.write_json({"success": False, "error_type": "executor_mismatch", "message": str(exc)}, status=403)

        def handle_send_shell(self, app_state: FakeShellBackend) -> None:
            try:
                payload = self.read_payload()
                task = build_shell_task(payload, app_state.default_project_path)
                created = app_state.store.create_task(task)
            except ValueError as exc:
                self.write_response({"success": False, "error_type": "invalid_task", "message": str(exc)}, status=400)
                return

            if self.accepts_html():
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
                return
            self.write_json({"success": True, "task": created}, status=201)

        def read_payload(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "")
            raw = self.read_body()
            if "application/json" in content_type:
                if not raw.strip():
                    return {}
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("JSON payload must be an object.")
                return payload
            values = urllib.parse.parse_qs(raw, keep_blank_values=True)
            return {key: items[-1] if items else "" for key, items in values.items()}

        def read_json(self) -> dict[str, Any]:
            raw = self.read_body()
            if not raw.strip():
                return {}
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("JSON payload must be an object.")
            return payload

        def read_body(self) -> str:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return ""
            return self.rfile.read(length).decode("utf-8")

        def require_auth(self, app_state: FakeShellBackend) -> bool:
            expected = app_state.token
            auth = self.headers.get("Authorization", "")
            if expected and auth != f"Bearer {expected}":
                self.write_json(
                    {"success": False, "error_type": "unauthorized", "message": "Invalid executor token."},
                    status=401,
                )
                return False
            return True

        def accepts_html(self) -> bool:
            return "text/html" in self.headers.get("Accept", "")

        def write_response(self, payload: dict[str, Any], status: int = 200) -> None:
            if self.accepts_html():
                self.write_html(render_message(payload), status=status)
            else:
                self.write_json(payload, status=status)

        def write_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def write_html(self, body: str, status: int = 200) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def build_shell_task(payload: dict[str, Any], default_project_path: Path) -> dict[str, Any]:
    script = str(payload.get("script") or "").strip("\r\n")
    if not script.strip():
        raise ValueError("script is required.")

    project_path = str(payload.get("project_path") or default_project_path).strip()
    if not project_path.startswith("/"):
        raise ValueError("project_path must be an absolute path.")

    task_type = str(payload.get("type") or "run_script").strip() or "run_script"
    if task_type not in {"run_script", "apply_script", "execute_script"}:
        raise ValueError("fake shell backend only creates local shell task types.")

    task: dict[str, Any] = {
        "type": task_type,
        "approved": True,
        "project_path": project_path,
        "interpreter": str(payload.get("interpreter") or "bash"),
        "script": script + "\n",
        "params": {"env": {}, "args": []},
    }
    executor_id = str(payload.get("executor_id") or "").strip()
    if executor_id:
        task["executor_id"] = executor_id
    return task


def render_index(state: FakeShellBackend) -> str:
    tasks = state.store.list_tasks()
    rows = "\n".join(render_task_row(task) for task in reversed(tasks[-20:]))
    default_path = html.escape(str(state.default_project_path))
    default_script = html.escape(DEFAULT_SCRIPT)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>ProjectPilot Fake Shell Backend</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 28px; max-width: 1120px; }}
    label {{ display: block; font-weight: 650; margin: 14px 0 6px; }}
    input, textarea, select {{ width: 100%; box-sizing: border-box; font: 14px ui-monospace, SFMono-Regular, Menlo, monospace; padding: 8px; }}
    textarea {{ min-height: 260px; }}
    button {{ margin-top: 14px; padding: 8px 14px; font-weight: 650; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 28px; }}
    th, td {{ text-align: left; border-bottom: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .hint {{ color: #555; }}
  </style>
</head>
<body>
  <h1>ProjectPilot Fake Shell Backend</h1>
  <p class="hint">这个假后端只下发 shell 任务。TUI 用 token <code>{html.escape(state.token)}</code> 连接。</p>

  <form method="post" action="/send-shell">
    <label>Task Type</label>
    <select name="type">
      <option value="run_script">run_script</option>
      <option value="apply_script">apply_script</option>
      <option value="execute_script">execute_script</option>
    </select>

    <label>Executor ID，可空</label>
    <input name="executor_id" placeholder="ubuntu">

    <label>Project Path</label>
    <input name="project_path" value="{default_path}">

    <label>Shell Script</label>
    <textarea name="script">{default_script}</textarea>

    <button type="submit">Send Shell Task</button>
  </form>

  <h2>最近任务</h2>
  <table>
    <thead><tr><th>ID</th><th>Status</th><th>Executor</th><th>Path</th><th>Result</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="5">No tasks yet.</td></tr>'}</tbody>
  </table>
</body>
</html>"""


def render_task_row(task: dict[str, Any]) -> str:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    summary = ""
    if result:
        summary = f"exit={result.get('exit_code')} success={result.get('success')}"
    return (
        "<tr>"
        f"<td><code>{html.escape(str(task.get('id', '')))}</code></td>"
        f"<td>{html.escape(str(task.get('status', '')))}</td>"
        f"<td>{html.escape(str(task.get('executor_id', '')))}</td>"
        f"<td><code>{html.escape(str(task.get('project_path', '')))}</code></td>"
        f"<td>{html.escape(summary)}</td>"
        "</tr>"
    )


def render_message(payload: dict[str, Any]) -> str:
    return f"""<!doctype html>
<meta charset="utf-8">
<pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2))}</pre>
<p><a href="/">Back</a></p>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local fake backend that only sends shell tasks.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--token", default="dev-token")
    parser.add_argument("--storage", type=Path, default=Path("/tmp/projectpilot-fake-shell-backend.json"))
    parser.add_argument("--project-path", type=Path, default=ROOT_DIR)
    args = parser.parse_args()

    state = FakeShellBackend(
        token=args.token,
        storage_path=args.storage,
        default_project_path=args.project_path.expanduser().resolve(),
    )
    server = create_server(args.host, args.port, state)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}"
    print(f"ProjectPilot fake shell backend: {url}")
    print(f"Storage: {args.storage.expanduser()}")
    print(f"Token: {args.token}")
    print()
    print("TUI command:")
    print(f"  ./dist/projectpilot-executor/bin/projectpilot-tui --server-url {url} --token {args.token} --executor-id local-demo --execution-mode local")
    print()
    print("Open the form:")
    print(f"  {url}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
