from datetime import datetime, timezone
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from models import ExecutorTask


TERMINAL_STATUSES = {"completed", "failed", "blocked", "error", "succeeded"}


def utc_now():
    return datetime.now(timezone.utc)


def create_executor_task(
    db,
    task_type: str,
    project_id: int | None = None,
    server_id: int | None = None,
    status: str = "queued",
    priority: int = 100,
    approval_status: str = "not_required",
    executor_id: str | None = None,
    payload: dict | None = None,
    result: dict | None = None,
    error_type: str | None = None,
    message: str | None = None,
):
    now = utc_now()
    task = ExecutorTask(
        public_id=f"task_{uuid4().hex[:12]}",
        project_id=project_id,
        server_id=server_id,
        task_type=task_type,
        status=status,
        priority=priority,
        approval_status=approval_status,
        executor_id=executor_id,
        payload=jsonable_encoder(payload) if payload is not None else None,
        result=jsonable_encoder(result) if result is not None else None,
        error_type=error_type,
        message=message,
        claimed_at=now if status in TERMINAL_STATUSES else None,
        completed_at=now if status in TERMINAL_STATUSES else None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def format_executor_task(task: ExecutorTask):
    return {
        "id": task.public_id,
        "numeric_id": task.id,
        "public_id": task.public_id,
        "project_id": task.project_id,
        "server_id": task.server_id,
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "approval_status": task.approval_status,
        "executor_id": task.executor_id,
        "payload": task.payload,
        "result": task.result,
        "error_type": task.error_type,
        "message": task.message,
        "created_at": task.created_at,
        "claimed_at": task.claimed_at,
        "completed_at": task.completed_at,
        "updated_at": task.updated_at,
    }
