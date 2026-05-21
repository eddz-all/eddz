from __future__ import annotations

import json
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from projectpilot.executor.app import create_executor_app_server
from projectpilot.executor.config import load_config
from projectpilot.cli import main as cli_main


class ExecutorAppTests(unittest.TestCase):
    def test_executor_app_help_lists_app_command(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as exc:
                cli_main(["executor", "app", "--help"])

        self.assertEqual(exc.exception.code, 0)
        self.assertIn("Open the local ProjectPilot Executor app", output.getvalue())

    def test_app_index_renders(self) -> None:
        with TemporaryDirectory() as temp_dir:
            server = start_app_server(Path(temp_dir) / "executor.json")
            try:
                body = get_text(server, "/")

                self.assertIn("ProjectPilot Executor", body)
                self.assertIn("Backend URL", body)
            finally:
                stop_server(server)

    def test_app_saves_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "executor.json"
            server = start_app_server(config_path)
            try:
                result = post_json(
                    server,
                    "/api/config",
                    {
                        "server_url": "http://127.0.0.1:8000",
                        "token": "secret-token",
                        "executor_id": "eddz-mac-local",
                        "allowed_root": temp_dir,
                        "interval": 7,
                    },
                )

                config = load_config(config_path)
                self.assertTrue(result["configured"])
                self.assertEqual(result["config"]["token"], "secr...oken")
                self.assertEqual(config.server_url, "http://127.0.0.1:8000")
                self.assertEqual(config.executor_id, "eddz-mac-local")
                self.assertEqual(config.allowed_root, Path(temp_dir).resolve())
                self.assertEqual(config.interval, 7.0)
            finally:
                stop_server(server)

    def test_app_poll_once_runs_through_backend_contract(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backend, backend_state = start_backend_server(
                {"id": "task_1", "type": "detect_environment", "project_path": temp_dir}
            )
            config_path = Path(temp_dir) / "executor.json"
            app = start_app_server(config_path)
            try:
                post_json(
                    app,
                    "/api/config",
                    {
                        "server_url": f"http://127.0.0.1:{backend.server_port}",
                        "token": "secret-token",
                        "executor_id": "eddz-mac-local",
                        "allowed_root": temp_dir,
                        "interval": 5,
                    },
                )

                result = post_json(app, "/api/poll-once", {})

                self.assertTrue(result["last_result"]["submitted"])
                self.assertEqual(backend_state["poll_payloads"][0]["executor_id"], "eddz-mac-local")
                self.assertEqual(backend_state["result_payloads"][0]["task_id"], "task_1")
                self.assertTrue(backend_state["result_payloads"][0]["result"]["success"])
            finally:
                stop_server(app)
                stop_server(backend)


def start_app_server(config_path: Path) -> ThreadingHTTPServer:
    server = create_executor_app_server(host="127.0.0.1", port=0, config_path=config_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def start_backend_server(task: dict[str, Any]) -> tuple[ThreadingHTTPServer, dict[str, Any]]:
    state: dict[str, Any] = {
        "poll_payloads": [],
        "result_payloads": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            payload = read_json_body(self)
            if self.path == "/executor/poll":
                state["poll_payloads"].append(payload)
                write_json(self, {"task": task})
                return
            if self.path == f"/executor/tasks/{task['id']}/result":
                state["result_payloads"].append(payload)
                write_json(self, {"success": True})
                return
            self.send_error(404)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, state


def get_text(server: ThreadingHTTPServer, path: str) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}{path}") as response:
        return response.read().decode("utf-8")


def post_json(server: ThreadingHTTPServer, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def write_json(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def stop_server(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    unittest.main()
