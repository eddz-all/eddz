from __future__ import annotations

import base64
import json
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from projectpilot.executor.remote import normalize_script, sha256_text
from projectpilot.executor.security import (
    ApprovalError,
    EXECUTION_TASK_TYPES,
    SCRIPT_TASK_TYPES,
    validate_execution_approval,
)


DEFAULT_BACKEND_DATA = {
    "executors": {},
    "tasks": [],
    "git_statuses": [],
    "smart_git_analyses": [],
    "environment_snapshots": [],
    "operation_logs": [],
}


def default_backend_storage_path() -> Path:
    return Path(".projectpilot") / "executor-backend.json"


@dataclass(frozen=True)
class ExecutorBackendConfig:
    token: str
    storage_path: Path


class ExecutorBackendStore:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path.expanduser()
        self._lock = threading.Lock()

    def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(task, dict):
            raise ValueError("Task payload must be an object.")
        task_type = str(task.get("type") or "").strip()
        if not task_type:
            raise ValueError("Task is missing type.")
        self._validate_task_before_queue(task_type, task)

        now = utc_now()
        stored_task = dict(task)
        stored_task.setdefault("id", f"task_{uuid.uuid4().hex}")
        stored_task["id"] = str(stored_task["id"])
        stored_task["type"] = task_type
        stored_task.setdefault("status", "queued")
        stored_task.setdefault("created_at", now)
        stored_task["updated_at"] = now

        with self._lock:
            data = self._load_unlocked()
            if self._find_task(data, stored_task["id"]) is not None:
                raise ValueError(f"Task already exists: {stored_task['id']}")
            data["tasks"].append(stored_task)
            self._save_unlocked(data)
        return stored_task

    def _validate_task_before_queue(self, task_type: str, task: dict[str, Any]) -> None:
        if task_type not in EXECUTION_TASK_TYPES:
            return
        try:
            script_sha256 = None
            if task_type in SCRIPT_TASK_TYPES:
                script = normalize_script(script_from_task(task))
                script_sha256 = sha256_text(script)
            validate_execution_approval(task, task_type=task_type, script_sha256=script_sha256)
        except ApprovalError as exc:
            raise ValueError(str(exc)) from exc

    def record_executor_poll(self, payload: dict[str, Any]) -> dict[str, Any]:
        executor_id = str(payload.get("executor_id") or "").strip()
        if not executor_id:
            raise ValueError("executor_id is required.")

        record = {
            "executor_id": executor_id,
            "mode": str(payload.get("mode") or "local"),
            "capabilities": list(payload.get("capabilities") or []),
            "status": str(payload.get("status") or "online"),
            "last_seen_at": utc_now(),
        }

        with self._lock:
            data = self._load_unlocked()
            data["executors"][executor_id] = record
            self._save_unlocked(data)
        return record

    def claim_next_task(self, executor_id: str, capabilities: list[str]) -> dict[str, Any] | None:
        capability_set = set(capabilities)
        now = utc_now()
        with self._lock:
            data = self._load_unlocked()
            for task in data["tasks"]:
                if task.get("status") != "queued":
                    continue
                if task.get("type") not in capability_set:
                    continue
                assigned_executor = task.get("executor_id")
                if assigned_executor and assigned_executor != executor_id:
                    continue
                task["status"] = "running"
                task["executor_id"] = executor_id
                task["started_at"] = now
                task["updated_at"] = now
                self._save_unlocked(data)
                return dict(task)
        return None

    def complete_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        executor_id = str(payload.get("executor_id") or "").strip()
        success = bool(payload.get("success", False))
        result = payload.get("result")
        if not isinstance(result, dict):
            result = {}

        with self._lock:
            data = self._load_unlocked()
            task = self._find_task(data, task_id)
            if task is None:
                raise KeyError(task_id)
            if executor_id and task.get("executor_id") and task.get("executor_id") != executor_id:
                raise PermissionError("Result executor_id does not match the claimed task.")

            task["executor_id"] = executor_id or task.get("executor_id")
            task["status"] = "succeeded" if success else "failed"
            task["success"] = success
            task["result"] = result
            task["error_type"] = payload.get("error_type") or result.get("error_type")
            task["message"] = payload.get("message") or result.get("message")
            task["result_started_at"] = payload.get("started_at")
            task["result_finished_at"] = payload.get("finished_at")
            task["duration_ms"] = payload.get("duration_ms")
            task["finished_at"] = now
            task["updated_at"] = now

            self._append_result_artifact(data, task, result)
            self._save_unlocked(data)
            return dict(task)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(task) for task in self._load_unlocked()["tasks"]]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def _append_result_artifact(self, data: dict[str, Any], task: dict[str, Any], result: dict[str, Any]) -> None:
        task_type = str(task.get("type") or "")
        base = {
            "id": f"artifact_{uuid.uuid4().hex}",
            "task_id": task.get("id"),
            "task_type": task_type,
            "executor_id": task.get("executor_id"),
            "project_id": task.get("project_id"),
            "server_id": task.get("server_id"),
            "ssh_host": task.get("ssh_host"),
            "project_path": task.get("project_path"),
            "captured_at": utc_now(),
            "success": result.get("success"),
            "result": result,
        }
        if task_type in {"detect_git", "detect_remote_git_status"}:
            data["git_statuses"].append(base)
        elif task_type == "smart_git_analyze":
            data["smart_git_analyses"].append(base)
        elif task_type in {"detect_environment", "detect_remote_environment"}:
            data["environment_snapshots"].append(base)
        elif task_type in {
            "apply_git_operation",
            "apply_remote_git_operation",
            "run_remote_script",
            "apply_remote_script",
            "execute_remote_script",
            "run_local_script",
            "apply_local_script",
            "execute_local_script",
        }:
            stdout, stderr = operation_streams(result)
            operation = {
                **base,
                "operation": task.get("operation") or result.get("operation") or task_type,
                "command": result.get("command") or nested_value(result, "plan", "command"),
                "exit_code": result.get("exit_code"),
                "stdout_summary": summarize_text(stdout),
                "stderr_summary": summarize_text(stderr),
                "risk_level": task.get("risk_level"),
                "approved": task.get("approved"),
                "script_sha256": result.get("script_sha256"),
                "script_size": result.get("script_size"),
            }
            data["operation_logs"].append(operation)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return json.loads(json.dumps(DEFAULT_BACKEND_DATA))
        data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        for key, default_value in DEFAULT_BACKEND_DATA.items():
            data.setdefault(key, json.loads(json.dumps(default_value)))
        return data

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix(f"{self.storage_path.suffix}.tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(self.storage_path)

    @staticmethod
    def _find_task(data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
        for task in data["tasks"]:
            if task.get("id") == task_id:
                return task
        return None


class ExecutorBackendState:
    def __init__(self, config: ExecutorBackendConfig) -> None:
        self.config = config
        self.store = ExecutorBackendStore(config.storage_path)


def create_executor_backend_server(
    host: str = "127.0.0.1",
    port: int = 8780,
    *,
    token: str,
    storage_path: Path,
) -> ThreadingHTTPServer:
    state = ExecutorBackendState(ExecutorBackendConfig(token=token, storage_path=storage_path))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.write_json({"success": True, "status": "ok"})
                return
            if self.path == "/tasks":
                if not self.require_auth(state):
                    return
                self.write_json({"success": True, "tasks": state.store.list_tasks()})
                return
            if self.path == "/state":
                if not self.require_auth(state):
                    return
                self.write_json({"success": True, "state": state.store.snapshot()})
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if not self.require_auth(state):
                return
            payload = self.read_json()
            if self.path == "/executor/poll":
                self.handle_executor_poll(state, payload)
                return
            match = re.fullmatch(r"/executor/tasks/([^/]+)/result", self.path)
            if match:
                self.handle_task_result(state, match.group(1), payload)
                return
            if self.path == "/tasks":
                self.handle_create_task(state, payload)
                return
            self.send_error(404)

        def handle_executor_poll(self, app_state: ExecutorBackendState, payload: dict[str, Any]) -> None:
            try:
                executor = app_state.store.record_executor_poll(payload)
                task = app_state.store.claim_next_task(
                    executor["executor_id"],
                    [str(item) for item in payload.get("capabilities") or []],
                )
                self.write_json({"task": task})
            except ValueError as exc:
                self.write_json({"success": False, "error_type": "invalid_poll", "message": str(exc)}, status=400)

        def handle_task_result(
            self,
            app_state: ExecutorBackendState,
            task_id: str,
            payload: dict[str, Any],
        ) -> None:
            try:
                task = app_state.store.complete_task(task_id, payload)
                self.write_json({"success": True, "task": task})
            except KeyError:
                self.write_json({"success": False, "error_type": "task_not_found", "message": task_id}, status=404)
            except PermissionError as exc:
                self.write_json({"success": False, "error_type": "executor_mismatch", "message": str(exc)}, status=403)

        def handle_create_task(self, app_state: ExecutorBackendState, payload: dict[str, Any]) -> None:
            try:
                task = app_state.store.create_task(payload)
                self.write_json({"success": True, "task": task}, status=201)
            except ValueError as exc:
                self.write_json({"success": False, "error_type": "invalid_task", "message": str(exc)}, status=400)

        def require_auth(self, app_state: ExecutorBackendState) -> bool:
            expected = app_state.config.token
            auth = self.headers.get("Authorization", "")
            if expected and auth != f"Bearer {expected}":
                self.write_json(
                    {"success": False, "error_type": "unauthorized", "message": "Invalid executor token."},
                    status=401,
                )
                return False
            return True

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON payload must be an object.")
            return payload

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


def run_executor_backend(
    host: str = "127.0.0.1",
    port: int = 8780,
    *,
    token: str,
    storage_path: Path,
) -> None:
    server = create_executor_backend_server(host=host, port=port, token=token, storage_path=storage_path)
    actual_host, actual_port = server.server_address[:2]
    print(f"ProjectPilot Executor backend: http://{actual_host}:{actual_port}")
    print(f"Storage: {storage_path.expanduser()}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize_text(value: Any, limit: int = 1000) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def nested_value(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def operation_streams(result: dict[str, Any]) -> tuple[Any, Any]:
    stdout = result.get("stdout")
    stderr = result.get("stderr")
    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        stdout = stdout if stdout is not None else nested_result.get("stdout")
        stderr = stderr if stderr is not None else nested_result.get("stderr")
    return stdout, stderr


def script_from_task(task: dict[str, Any]) -> str:
    for key in ("script", "script_content", "script_body"):
        value = task.get(key)
        if value is not None:
            return str(value)
    encoded = task.get("script_base64")
    if encoded is not None:
        try:
            return base64.b64decode(str(encoded), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApprovalError("script_base64 must be valid UTF-8 base64.") from exc
    raise ApprovalError("Script execution approval requires a script payload.")
