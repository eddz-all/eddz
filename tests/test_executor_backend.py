from __future__ import annotations

import io
import json
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

from projectpilot.cli import main as cli_main
from projectpilot.executor.backend import ExecutorBackendStore, create_executor_backend_server
from projectpilot.executor.client import poll_and_run_once
from projectpilot.executor.config import ExecutorConfig


class ExecutorBackendTests(unittest.TestCase):
    def test_backend_store_creates_queued_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"

            task = ExecutorBackendStore(storage).create_task(
                {
                    "type": "detect_environment",
                    "project_path": temp_dir,
                }
            )

            data = json.loads(storage.read_text(encoding="utf-8"))
            self.assertEqual(task["status"], "queued")
            self.assertEqual(data["tasks"][0]["id"], task["id"])

    def test_backend_server_runs_executor_poll_result_and_persists_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"
            store = ExecutorBackendStore(storage)
            task = store.create_task(
                {
                    "id": "task_1",
                    "type": "detect_environment",
                    "project_path": temp_dir,
                }
            )
            server = start_backend(storage, token="secret")
            try:
                config = ExecutorConfig(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                    executor_id="eddz-mac-local",
                    allowed_root=Path(temp_dir),
                )

                result = poll_and_run_once(config)

                data = json.loads(storage.read_text(encoding="utf-8"))
                self.assertTrue(result["submitted"])
                self.assertEqual(data["tasks"][0]["id"], task["id"])
                self.assertEqual(data["tasks"][0]["status"], "succeeded")
                self.assertEqual(data["tasks"][0]["executor_id"], "eddz-mac-local")
                self.assertEqual(len(data["environment_snapshots"]), 1)
                self.assertTrue(data["environment_snapshots"][0]["result"]["success"])
                self.assertIn("eddz-mac-local", data["executors"])
            finally:
                stop_server(server)

    def test_backend_server_rejects_invalid_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"
            server = start_backend(storage, token="secret")
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/executor/poll",
                    data=json.dumps({"executor_id": "bad"}).encode("utf-8"),
                    method="POST",
                    headers={
                        "Authorization": "Bearer wrong",
                        "Content-Type": "application/json",
                    },
                )

                with self.assertRaises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(request)

                self.assertEqual(exc.exception.code, 401)
                exc.exception.close()
            finally:
                stop_server(server)

    def test_backend_store_records_operation_log_from_nested_local_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"
            store = ExecutorBackendStore(storage)
            store.create_task(
                {
                    "id": "task_1",
                    "type": "apply_git_operation",
                    "project_path": temp_dir,
                    "operation": "pull",
                    "approved": True,
                }
            )
            store.record_executor_poll(
                {
                    "executor_id": "eddz-mac-local",
                    "capabilities": ["apply_git_operation"],
                    "status": "online",
                }
            )
            claimed = store.claim_next_task("eddz-mac-local", ["apply_git_operation"])
            self.assertIsNotNone(claimed)

            store.complete_task(
                "task_1",
                {
                    "executor_id": "eddz-mac-local",
                    "success": True,
                    "result": {
                        "success": True,
                        "operation": "pull",
                        "plan": {"command": ["git", "pull", "--ff-only"]},
                        "result": {"stdout": "updated\n", "stderr": ""},
                    },
                },
            )

            data = json.loads(storage.read_text(encoding="utf-8"))
            self.assertEqual(len(data["operation_logs"]), 1)
            self.assertEqual(data["operation_logs"][0]["command"], ["git", "pull", "--ff-only"])
            self.assertEqual(data["operation_logs"][0]["stdout_summary"], "updated\n")

    def test_backend_store_records_remote_script_operation_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"
            store = ExecutorBackendStore(storage)
            store.create_task(
                {
                    "id": "task_1",
                    "type": "run_remote_script",
                    "ssh_host": "prod-server",
                    "project_path": "/srv/app",
                    "approved": True,
                }
            )
            store.record_executor_poll(
                {
                    "executor_id": "eddz-mac-local",
                    "capabilities": ["run_remote_script"],
                    "status": "online",
                }
            )
            store.claim_next_task("eddz-mac-local", ["run_remote_script"])

            store.complete_task(
                "task_1",
                {
                    "executor_id": "eddz-mac-local",
                    "success": True,
                    "result": {
                        "success": True,
                        "command": "cd /srv/app && bash -s --",
                        "stdout": "ok\n",
                        "stderr": "",
                        "exit_code": 0,
                        "script_sha256": "abc123",
                        "script_size": 12,
                    },
                },
            )

            data = json.loads(storage.read_text(encoding="utf-8"))
            self.assertEqual(len(data["operation_logs"]), 1)
            self.assertEqual(data["operation_logs"][0]["operation"], "run_remote_script")
            self.assertEqual(data["operation_logs"][0]["script_sha256"], "abc123")
            self.assertEqual(data["operation_logs"][0]["stdout_summary"], "ok\n")

    def test_backend_store_records_local_script_operation_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"
            store = ExecutorBackendStore(storage)
            store.create_task(
                {
                    "id": "task_1",
                    "type": "run_local_script",
                    "project_path": "/home/hzy/project/web",
                    "approved": True,
                }
            )
            store.claim_next_task("server-b", ["run_local_script"])

            store.complete_task(
                "task_1",
                {
                    "executor_id": "server-b",
                    "success": True,
                    "result": {
                        "success": True,
                        "operation": "run_local_script",
                        "command": "cd /home/hzy/project/web && bash -s --",
                        "stdout": "ok\n",
                        "stderr": "",
                        "exit_code": 0,
                        "script_sha256": "abc123",
                        "script_size": 12,
                    },
                },
            )

            data = json.loads(storage.read_text(encoding="utf-8"))
            self.assertEqual(len(data["operation_logs"]), 1)
            self.assertEqual(data["operation_logs"][0]["operation"], "run_local_script")
            self.assertEqual(data["operation_logs"][0]["project_path"], "/home/hzy/project/web")
            self.assertEqual(data["operation_logs"][0]["stdout_summary"], "ok\n")

    def test_enqueue_cli_writes_backend_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "executor",
                        "enqueue",
                        "--storage",
                        str(storage),
                        "--type",
                        "detect_environment",
                        "--project-path",
                        temp_dir,
                        "--json",
                    ]
                )

            data = json.loads(output.getvalue())
            stored = json.loads(storage.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertTrue(data["success"])
            self.assertEqual(stored["tasks"][0]["type"], "detect_environment")

    def test_run_local_cli_processes_default_smart_git_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            repo.mkdir()
            init_repo(repo)
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "executor",
                        "run-local",
                        "--allowed-root",
                        str(root),
                        "--project-path",
                        str(repo),
                        "--once",
                        "--json",
                    ]
                )

            data = json.loads(output.getvalue())
            state = data["state"]
            self.assertEqual(exit_code, 0)
            self.assertTrue(data["success"])
            self.assertTrue(data["executor_result"]["submitted"])
            self.assertEqual(state["tasks"][0]["status"], "succeeded")
            self.assertEqual(len(state["smart_git_analyses"]), 1)
            self.assertIn("map", state["smart_git_analyses"][0]["result"]["reports"])

    def test_publish_cli_queues_smart_git_task_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Path(temp_dir) / "backend.json"
            server = start_backend(storage, token="secret")
            output = io.StringIO()
            try:
                with redirect_stdout(output):
                    exit_code = cli_main(
                        [
                            "executor",
                            "publish",
                            "--server-url",
                            f"http://127.0.0.1:{server.server_port}",
                            "--token",
                            "secret",
                            "--executor-id",
                            "server-b",
                            "--project-path",
                            "/home/hzy/project/web",
                            "--type",
                            "smart_git_analyze",
                            "--analyses",
                            "map",
                            "sync-plan",
                            "--json",
                        ]
                    )
            finally:
                stop_server(server)

            data = json.loads(output.getvalue())
            stored = json.loads(storage.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertTrue(data["success"])
            self.assertEqual(stored["tasks"][0]["type"], "smart_git_analyze")
            self.assertEqual(stored["tasks"][0]["executor_id"], "server-b")
            self.assertEqual(stored["tasks"][0]["project_path"], "/home/hzy/project/web")
            self.assertEqual(stored["tasks"][0]["analyses"], ["map", "sync-plan"])

    def test_publish_cli_prints_project_detect_request_without_posting(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = cli_main(
                [
                    "executor",
                    "publish",
                    "--mode",
                    "project-detect",
                    "--project-id",
                    "7",
                    "--server-id",
                    "9",
                    "--print-only",
                    "--json",
                ]
            )

        data = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(data["success"])
        self.assertEqual(data["path"], "/projects/7/servers/9/detect")
        self.assertEqual(data["payload"], {})


def start_backend(storage: Path, token: str):
    server = create_executor_backend_server(host="127.0.0.1", port=0, token=token, storage_path=storage)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def stop_server(server) -> None:
    server.shutdown()
    server.server_close()


def init_repo(repo: Path) -> None:
    run(["git", "init", "-b", "main"], repo)
    run(["git", "config", "user.name", "ProjectPilot Test"], repo)
    run(["git", "config", "user.email", "projectpilot@example.test"], repo)
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    run(["git", "add", "tracked.txt"], repo)
    run(["git", "commit", "-m", "initial"], repo)


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
