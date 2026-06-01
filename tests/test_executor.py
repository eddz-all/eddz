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

    def test_execute_task_rejects_unapproved_git_operation(self) -> None:
        with git_repo() as repo:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=repo.parent,
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "apply_git_operation",
                    "project_path": str(repo),
                    "operation": "pull",
                },
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "approval_required")

    def test_execute_task_applies_approved_local_git_add(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=repo.parent,
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "apply_git_operation",
                    "project_path": str(repo),
                    "approved": True,
                    "operation": "add",
                    "expected_command": ["git", "add", "--", "projectpilot/feature.py"],
                },
                config,
            )
            staged = run(["git", "diff", "--cached", "--name-only"], repo).stdout.splitlines()

            self.assertTrue(result["success"])
            self.assertEqual(result["operation"], "add")
            self.assertIn("projectpilot/feature.py", staged)

    def test_execute_task_rejects_local_git_command_mismatch(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=repo.parent,
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "apply_git_operation",
                    "project_path": str(repo),
                    "approved": True,
                    "operation": "add",
                    "expected_command": ["git", "add", "--", "other.py"],
                },
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "command_mismatch")

    def test_execute_task_rejects_invalid_local_git_params(self) -> None:
        with git_repo() as repo:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=repo.parent,
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "apply_git_operation",
                    "project_path": str(repo),
                    "approved": True,
                    "operation": "pull",
                    "params": ["not", "an", "object"],
                },
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "git_operation_failed")

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
            check_connection.assert_called_once_with("dev-server", timeout=20, auth_mode="key")

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
            detect_remote_git_status.assert_called_once_with("prod-server", "/srv/app", timeout=20, auth_mode="key")

    def test_execute_task_rejects_unapproved_remote_git_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "apply_remote_git_operation",
                    "ssh_host": "prod-server",
                    "project_path": "/srv/app",
                    "operation": "pull",
                },
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "approval_required")

    def test_execute_task_runs_approved_remote_git_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            with patch("projectpilot.executor.client.apply_remote_git_operation") as apply_remote_git_operation:
                apply_remote_git_operation.return_value = {
                    "success": True,
                    "operation": "pull",
                    "command": ["git", "pull", "--ff-only"],
                }
                result = execute_task(
                    {
                        "id": "task_1",
                        "type": "apply_remote_git_operation",
                        "ssh_host": "prod-server",
                        "project_path": "/srv/app",
                        "approved": True,
                        "operation": "pull",
                        "expected_command": ["git", "pull", "--ff-only"],
                    },
                    config,
                )

            self.assertTrue(result["success"])
            apply_remote_git_operation.assert_called_once_with(
                "prod-server",
                "/srv/app",
                operation="pull",
                params={},
                expected_command=["git", "pull", "--ff-only"],
                timeout=20,
                auth_mode="key",
            )

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
                self.assertIn("smart_git_analyze", state["poll_payloads"][0]["capabilities"])
                self.assertIn("detect_remote_git_status", state["poll_payloads"][0]["capabilities"])
                self.assertIn("apply_git_operation", state["poll_payloads"][0]["capabilities"])
                self.assertIn("apply_remote_git_operation", state["poll_payloads"][0]["capabilities"])
                self.assertIn("run_remote_script", state["poll_payloads"][0]["capabilities"])
                self.assertEqual(state["result_payloads"][0]["task_id"], "task_1")
                self.assertTrue(state["result_payloads"][0]["success"])
                self.assertIn("started_at", state["result_payloads"][0])
                self.assertIn("finished_at", state["result_payloads"][0])
                self.assertIn("duration_ms", state["result_payloads"][0])
                self.assertTrue(state["result_payloads"][0]["result"]["success"])
                self.assertEqual(state["result_payloads"][0]["result"]["task_id"], "task_1")
                self.assertIn("os", state["result_payloads"][0]["result"])
            finally:
                server.shutdown()
                server.server_close()

    def test_execute_task_runs_smart_git_analysis(self) -> None:
        with git_repo() as repo:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="dev-server-agent",
                allowed_root=repo.parent,
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "smart_git_analyze",
                    "project_path": str(repo),
                    "analyses": ["map", "sync-plan"],
                },
                config,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["schema_version"], "smart-git.v1")
            self.assertEqual(result["branch"], "main")
            self.assertIn("map", result["reports"])
            self.assertIn("sync_plan", result["reports"])

    def test_execute_task_rejects_invalid_smart_git_analyses(self) -> None:
        with git_repo() as repo:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="dev-server-agent",
                allowed_root=repo.parent,
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "smart_git_analyze",
                    "project_path": str(repo),
                    "analyses": "map",
                },
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "invalid_analyses")

    def test_execute_task_rejects_remote_path_outside_task_allowed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "detect_remote_git_status",
                    "ssh_host": "prod-server",
                    "project_path": "/srv/other",
                    "allowed_paths": ["/srv/app"],
                },
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "path_not_allowed")

    def test_execute_task_rejects_unapproved_remote_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            result = execute_task(
                {
                    "id": "task_1",
                    "type": "run_remote_script",
                    "ssh_host": "prod-server",
                    "project_path": "/srv/app",
                    "script": "echo hello\n",
                },
                config,
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error_type"], "approval_required")

    def test_execute_task_runs_approved_remote_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            with patch("projectpilot.executor.client.run_remote_script") as run_remote_script:
                run_remote_script.return_value = {
                    "success": True,
                    "operation": "run_remote_script",
                    "exit_code": 0,
                }
                result = execute_task(
                    {
                        "id": "task_1",
                        "type": "run_remote_script",
                        "ssh_host": "prod-server",
                        "project_path": "/srv/app",
                        "approved": True,
                        "script": "echo hello\n",
                        "script_sha256": "abc",
                        "params": {"env": {"APP_ENV": "test"}, "args": ["one"]},
                    },
                    config,
                )

            self.assertTrue(result["success"])
            run_remote_script.assert_called_once_with(
                "prod-server",
                "echo hello\n",
                project_path="/srv/app",
                interpreter="bash",
                args=["one"],
                env={"APP_ENV": "test"},
                expected_sha256="abc",
                auth_mode="key",
                timeout=20,
            )

    def test_execute_task_passes_password_auth_mode_to_remote_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ExecutorConfig(
                server_url="http://127.0.0.1:8000",
                token="secret",
                executor_id="eddz-mac-local",
                allowed_root=Path(temp_dir),
            )

            with patch("projectpilot.executor.client.run_remote_script") as run_remote_script:
                run_remote_script.return_value = {"success": True, "exit_code": 0}
                result = execute_task(
                    {
                        "id": "task_1",
                        "type": "run_remote_script",
                        "ssh_host": "ubuntu",
                        "project_path": "/home/hzy",
                        "approved": True,
                        "script": "whoami\n",
                        "ssh_auth_mode": "password",
                    },
                    config,
                )

            self.assertTrue(result["success"])
            self.assertEqual(run_remote_script.call_args.kwargs["auth_mode"], "password")

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
