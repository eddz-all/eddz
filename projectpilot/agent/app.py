from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from projectpilot.agent.client import poll_and_run_once
from projectpilot.agent.config import AgentConfig, build_config, default_config_path, load_config, save_config


class AgentBackgroundRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: AgentConfig) -> None:
        with self._lock:
            if self.running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, args=(config,), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self, config: AgentConfig) -> None:
        while not self._stop_event.is_set():
            try:
                self.last_result = poll_and_run_once(config)
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
            self._stop_event.wait(config.interval)


class AgentAppState:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or default_config_path()
        self.runner = AgentBackgroundRunner()

    def snapshot(self) -> dict[str, Any]:
        config = load_optional_config(self.config_path)
        return {
            "configured": config is not None,
            "config_path": str(self.config_path.expanduser()),
            "config": config.to_dict(mask_token=True) if config else None,
            "running": self.runner.running,
            "last_result": self.runner.last_result,
            "last_error": self.runner.last_error,
        }


def create_agent_app_server(host: str = "127.0.0.1", port: int = 8765, config_path: Path | None = None) -> ThreadingHTTPServer:
    state = AgentAppState(config_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/index.html":
                self.write_html(render_index_html())
                return
            if self.path == "/api/state":
                self.write_json(state.snapshot())
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path == "/api/config":
                self.handle_save_config(state)
                return
            if self.path == "/api/poll-once":
                self.handle_poll_once(state)
                return
            if self.path == "/api/start":
                self.handle_start(state)
                return
            if self.path == "/api/stop":
                state.runner.stop()
                self.write_json(state.snapshot())
                return
            self.send_error(404)

        def handle_save_config(self, app_state: AgentAppState) -> None:
            try:
                payload = self.read_json()
                existing = load_optional_config(app_state.config_path)
                token = str(payload.get("token") or (existing.token if existing else "")).strip()
                config = build_config(
                    server_url=str(payload.get("server_url", "")).strip(),
                    token=token,
                    machine_id=str(payload.get("machine_id") or "").strip() or None,
                    allowed_root=str(payload.get("allowed_root") or Path.cwd()),
                    interval=float(payload.get("interval") or 5.0),
                )
                save_config(config, app_state.config_path)
                self.write_json(app_state.snapshot())
            except Exception as exc:
                self.write_json({"success": False, "error_type": "config_error", "message": str(exc)}, status=400)

        def handle_poll_once(self, app_state: AgentAppState) -> None:
            try:
                result = poll_and_run_once(load_config(app_state.config_path))
                app_state.runner.last_result = result
                app_state.runner.last_error = None
                self.write_json(app_state.snapshot())
            except Exception as exc:
                app_state.runner.last_error = str(exc)
                self.write_json({"success": False, "error_type": "poll_error", "message": str(exc)}, status=400)

        def handle_start(self, app_state: AgentAppState) -> None:
            try:
                app_state.runner.start(load_config(app_state.config_path))
                self.write_json(app_state.snapshot())
            except Exception as exc:
                self.write_json({"success": False, "error_type": "start_error", "message": str(exc)}, status=400)

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def write_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def write_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def run_agent_app(
    host: str = "127.0.0.1",
    port: int = 8765,
    config_path: Path | None = None,
    open_browser: bool = True,
) -> None:
    server = create_agent_app_server(host=host, port=port, config_path=config_path)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}"
    if open_browser:
        webbrowser.open(url)
    print(f"ProjectPilot Agent app: {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def load_optional_config(path: Path) -> AgentConfig | None:
    try:
        return load_config(path)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        return None


def render_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ProjectPilot Agent</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #627089;
      --line: #d9dfeb;
      --primary: #2563eb;
      --primary-dark: #1d4ed8;
      --success: #0f766e;
      --danger: #b42318;
      --code: #111827;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 28px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
    }
    main {
      width: min(1080px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      grid-template-columns: minmax(320px, 440px) 1fr;
      gap: 20px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 15px;
      font-weight: 700;
    }
    label {
      display: block;
      margin: 12px 0 6px;
      font-size: 13px;
      font-weight: 600;
      color: var(--muted);
    }
    input {
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      color: var(--text);
      font: inherit;
      background: #fff;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 120px;
      gap: 10px;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }
    button {
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 12px;
      font: inherit;
      font-weight: 650;
      background: #fff;
      color: var(--text);
      cursor: pointer;
    }
    button.primary {
      border-color: var(--primary);
      background: var(--primary);
      color: #fff;
    }
    button.primary:hover { background: var(--primary-dark); }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
      background: #eef2ff;
      color: var(--primary-dark);
    }
    .badge.running {
      background: #ccfbf1;
      color: var(--success);
    }
    .stack {
      display: grid;
      gap: 14px;
    }
    dl {
      display: grid;
      grid-template-columns: 130px 1fr;
      gap: 8px 12px;
      margin: 0;
      font-size: 14px;
    }
    dt { color: var(--muted); }
    dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    pre {
      margin: 0;
      min-height: 260px;
      max-height: 520px;
      overflow: auto;
      border-radius: 6px;
      padding: 14px;
      color: #e5e7eb;
      background: var(--code);
      font-size: 12px;
      line-height: 1.55;
    }
    .error { color: var(--danger); }
    @media (max-width: 780px) {
      header { padding: 16px; }
      main {
        width: calc(100vw - 24px);
        grid-template-columns: 1fr;
        margin: 12px auto;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>ProjectPilot Agent</h1>
    <span id="statusBadge" class="badge">Stopped</span>
  </header>
  <main>
    <section>
      <h2>Connection</h2>
      <form id="configForm">
        <label for="serverUrl">Backend URL</label>
        <input id="serverUrl" name="server_url" placeholder="http://127.0.0.1:8000" autocomplete="off">
        <label for="token">Agent Token</label>
        <input id="token" name="token" type="password" placeholder="Leave blank to keep saved token" autocomplete="off">
        <label for="machineId">Machine ID</label>
        <input id="machineId" name="machine_id" placeholder="eddz-mac" autocomplete="off">
        <div class="row">
          <div>
            <label for="allowedRoot">Allowed Root</label>
            <input id="allowedRoot" name="allowed_root" placeholder="/Users/eddz/work" autocomplete="off">
          </div>
          <div>
            <label for="interval">Interval</label>
            <input id="interval" name="interval" type="number" min="1" step="1" value="5">
          </div>
        </div>
        <div class="actions">
          <button class="primary" type="submit">Save</button>
          <button type="button" id="pollOnceButton">Poll Once</button>
          <button type="button" id="startButton">Start</button>
          <button type="button" id="stopButton">Stop</button>
        </div>
      </form>
    </section>
    <div class="stack">
      <section>
        <h2>Status</h2>
        <dl>
          <dt>Config</dt><dd id="configPath">-</dd>
          <dt>Server</dt><dd id="serverText">-</dd>
          <dt>Machine</dt><dd id="machineText">-</dd>
          <dt>Allowed root</dt><dd id="rootText">-</dd>
          <dt>Last error</dt><dd id="errorText">-</dd>
        </dl>
      </section>
      <section>
        <h2>Result</h2>
        <pre id="resultBox">{}</pre>
      </section>
    </div>
  </main>
  <script>
    const form = document.querySelector("#configForm");
    const badge = document.querySelector("#statusBadge");
    const resultBox = document.querySelector("#resultBox");

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        ...options
      });
      const data = await response.json();
      if (!response.ok) throw data;
      return data;
    }

    function setText(id, value) {
      document.querySelector("#" + id).textContent = value || "-";
    }

    function render(state) {
      badge.textContent = state.running ? "Running" : "Stopped";
      badge.classList.toggle("running", state.running);
      setText("configPath", state.config_path);
      setText("serverText", state.config && state.config.server_url);
      setText("machineText", state.config && state.config.machine_id);
      setText("rootText", state.config && state.config.allowed_root);
      setText("errorText", state.last_error);
      document.querySelector("#errorText").classList.toggle("error", Boolean(state.last_error));
      if (state.config) {
        form.server_url.value = state.config.server_url || "";
        form.machine_id.value = state.config.machine_id || "";
        form.allowed_root.value = state.config.allowed_root || "";
        form.interval.value = state.config.interval || 5;
      }
      resultBox.textContent = JSON.stringify(state.last_result || {}, null, 2);
    }

    async function refresh() {
      render(await api("/api/state"));
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(form).entries());
      render(await api("/api/config", { method: "POST", body: JSON.stringify(payload) }));
      form.token.value = "";
    });

    document.querySelector("#pollOnceButton").addEventListener("click", async () => {
      render(await api("/api/poll-once", { method: "POST", body: "{}" }));
    });
    document.querySelector("#startButton").addEventListener("click", async () => {
      render(await api("/api/start", { method: "POST", body: "{}" }));
    });
    document.querySelector("#stopButton").addEventListener("click", async () => {
      render(await api("/api/stop", { method: "POST", body: "{}" }));
    });

    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""
