from __future__ import annotations

import io
import json
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from projectpilot.cli import main as cli_main


class BackendConsoleTests(unittest.TestCase):
    def test_default_projectpilot_opens_backend_console_not_executor(self) -> None:
        output = io.StringIO()

        with patch("sys.stdin.isatty", return_value=False), redirect_stdout(output):
            exit_code = cli_main([])

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        self.assertIn("ProjectPilot Backend Console", text)
        self.assertNotIn("ProjectPilot Executor connected", text)

    def test_backend_health_cli_reads_backend(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "backend",
                        "--server-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--token",
                        "secret",
                        "--json",
                        "health",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue()), {"status": "ok"})
            self.assertEqual(state["auth"], ["Bearer secret"])
        finally:
            server.shutdown()
            server.server_close()

    def test_backend_detect_cli_posts_project_server_detect(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "backend",
                        "--server-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--token",
                        "secret",
                        "--json",
                        "detect",
                        "--project-id",
                        "1",
                        "--server-id",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["queued"], True)
            self.assertEqual(state["posts"], ["/projects/1/servers/2/detect"])
        finally:
            server.shutdown()
            server.server_close()


def start_backend_test_server() -> tuple[ThreadingHTTPServer, dict[str, Any]]:
    state: dict[str, Any] = {
        "auth": [],
        "posts": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            state["auth"].append(self.headers.get("Authorization"))
            if self.path == "/health":
                self.write_json({"status": "ok"})
                return
            if self.path == "/projects":
                self.write_json([{"id": 1, "name": "ProjectPilot", "path": "/demo/projectpilot"}])
                return
            if self.path == "/servers":
                self.write_json([{"id": 2, "name": "server-b", "connection_mode": "executor"}])
                return
            if self.path == "/executor/tasks":
                self.write_json([])
                return
            self.send_error(404)

        def do_POST(self) -> None:
            state["auth"].append(self.headers.get("Authorization"))
            state["posts"].append(self.path)
            if self.path == "/projects/1/servers/2/detect":
                read_json_body(self)
                self.write_json({"queued": True})
                return
            self.send_error(404)

        def write_json(self, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, state


def read_json_body(handler: BaseHTTPRequestHandler) -> Any:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
