from __future__ import annotations

import io
import json
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

from projectpilot.executor.client import execute_task, poll_and_run_once
from projectpilot.executor.config import ExecutorConfig, load_config, save_config
from projectpilot.cli import main as cli_main


class ExecutorTests(unittest.TestCase):
    def test_setup_cli_writes_reusable_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "executor.json"
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "executor",
                        "setup",
                        "--config",
                        str(config_path),
                        "--server-url",
                        "http://127.0.0.1:8000",
                        "--token",
                        "secret-token",
                        "--executor-id",
                        "eddz-mac-local",
                        "--allowed-root",
                        temp_dir,
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(config_path.exists())
            config = load_config(config_path)
            self.assertEqual(config.server_url, "http://127.0.0.1:8000")
            self.assertEqual(config.executor_id, "eddz-mac-local")
            self.assertEqual(config.mode, "local")
            self.assertEqual(config.allowed_root, Path(temp_dir).resolve())
            self.assertIn("secr...oken", output.getvalue())

    def test_status_cli_masks_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "executor.json"
            save_config(
                ExecutorConfig(
                    server_url="http://127.0.0.1:8000",
                    token="secret-token",
                    executor_id="eddz-mac-local",
                    allowed_root=Path(temp_dir),
                ),
                config_path,
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(["executor", "status", "--config", str(config_path), "--json"])

            data = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(data["config"]["token"], "secr...oken")
            self.assertTrue(data["allowed_root_exists"])

    def test_execute_task_rejects_paths_outside_allowed_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            result = execute_task(
                {"id": "task_1", "type": "detect_environment", "project_path": "/tmp"},
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "path_not_allowed")

    def test_execute_task_runs_local_git_detection(self) -> None:
        with git_repo() as repo:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=repo.parent,
            )

            result = execute_task(
                {"id": "task_1", "type": "detect_git", "project_path": str(repo)},
                config,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["branch"], "main")
            self.assertFalse(result["has_uncommitted_changes"])

    def test_execute_task_rejects_unknown_task_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            result = execute_task(
                {"id": "task_1", "type": "run_command", "project_path": temp_dir},
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "unsupported_task")

    def test_execute_task_runs_remote_connection_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            with patch("projectpilot.executor.client.check_connection") as check_connection:
                check_connection.return_value = {
                    "success": True,
                    "host": "dev-server",
                    "stdout": "projectpilot-ok",
                    "stderr": "",
                    "exit_code": 0,
                }
                result = execute_task({"id": "task_1", "type": "check_connection", "ssh_host": "dev-server"}, config)

            self.assertTrue(result["success"])
            check_connection.assert_called_once_with("dev-server", timeout=20)

    def test_execute_task_runs_remote_git_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            with patch("projectpilot.executor.client.detect_remote_git_status") as detect_remote_git_status:
                detect_remote_git_status.return_value = {
                    "success": True,
                    "host": "prod-server",
                    "project_path": "/srv/app",
                    "branch": "main",
                }
                result = execute_task(
                    {
                        "id": "task_1",
                        "type": "detect_remote_git_status",
                        "ssh_host": "prod-server",
                        "project_path": "/srv/app",
                    },
                    config,
                )

            self.assertTrue(result["success"])
            detect_remote_git_status.assert_called_once_with("prod-server", "/srv/app", timeout=20)

    def test_poll_and_run_once_uploads_detection_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = {
                "id": "task_1",
                "type": "detect_environment",
                "project_path": temp_dir,
            }
            server, state = start_executor_test_server(task)
            try:
                config = ExecutorConfig(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                    executor_id="eddz-mac-local",
                    allowed_root=Path(temp_dir),
                )

                result = poll_and_run_once(config)

                self.assertTrue(result["success"])
                self.assertTrue(result["submitted"])
                self.assertEqual(state["auth"], ["Bearer secret", "Bearer secret"])
                self.assertEqual(state["poll_payloads"][0]["executor_id"], "eddz-mac-local")
                self.assertEqual(state["poll_payloads"][0]["mode"], "local")
                self.assertIn("detect_remote_git_status", state["poll_payloads"][0]["capabilities"])
                self.assertEqual(state["result_payloads"][0]["task_id"], "task_1")
                self.assertTrue(state["result_payloads"][0]["success"])
                self.assertTrue(state["result_payloads"][0]["result"]["success"])
                self.assertIn("os", state["result_payloads"][0]["result"])
            finally:
                server.shutdown()
                server.server_close()

    def test_ssh_hosts_cli_lists_config_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ssh_config = Path(temp_dir) / "config"
            ssh_config.write_text("Host dev-server\n  HostName 127.0.0.1\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(["executor", "ssh-hosts", "--ssh-config", str(ssh_config), "--json"])

            data = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(data["hosts"], ["dev-server"])


class git_repo:
    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        run(["git", "init", "-b", "main"], self.repo)
        run(["git", "config", "user.name", "ProjectPilot Test"], self.repo)
        run(["git", "config", "user.email", "projectpilot@example.test"], self.repo)
        (self.repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
        run(["git", "add", "tracked.txt"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)
        return self.repo

    def __exit__(self, exc_type, exc, tb) -> None:
        self.temp_dir.cleanup()


def start_executor_test_server(task: dict[str, Any]) -> tuple[ThreadingHTTPServer, dict[str, Any]]:
    state: dict[str, Any] = {
        "auth": [],
        "poll_payloads": [],
        "result_payloads": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            payload = read_json_body(self)
            state["auth"].append(self.headers.get("Authorization"))

            if self.path == "/executor/poll":
                state["poll_payloads"].append(payload)
                self.write_json({"task": task})
                return
            if self.path == f"/executor/tasks/{task['id']}/result":
                state["result_payloads"].append(payload)
                self.write_json({"success": True})
                return
            self.send_error(404)

        def write_json(self, payload: dict[str, Any]) -> None:
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


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


if __name__ == "__main__":
    unittest.main()
