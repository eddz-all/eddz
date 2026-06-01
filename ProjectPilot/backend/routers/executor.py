from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from config import get_executor_settings
from database import get_db
from models import ExecutorTask
from services.executor_task_service import (
    claim_next_executor_task,
    complete_executor_task,
    executor_task_to_agent_payload,
    format_executor_task,
)


router = APIRouter(tags=["executor"])


def require_executor_auth(authorization: str | None):
    settings = get_executor_settings()
    expected = f"Bearer {settings.shared_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid executor token")


@router.post("/executor/poll")
def poll_executor(
    payload: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_executor_auth(authorization)
    executor_id = str(payload.get("executor_id") or "").strip()
    if not executor_id:
        raise HTTPException(status_code=400, detail="executor_id is required")

    raw_capabilities = payload.get("capabilities") or []
    if not isinstance(raw_capabilities, list):
        raise HTTPException(status_code=400, detail="capabilities must be an array")
    capabilities = [str(item) for item in raw_capabilities]
    task = claim_next_executor_task(db, executor_id, capabilities)
    return {"success": True, "task": None if task is None else executor_task_to_agent_payload(task)}


@router.post("/executor/tasks/{task_id}/result")
def submit_executor_result(
    task_id: str,
    payload: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_executor_auth(authorization)
    task = db.query(ExecutorTask).filter(ExecutorTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Executor task not found")

    executor_id = str(payload.get("executor_id") or "").strip()
    if executor_id and task.executor_id and executor_id != task.executor_id:
        raise HTTPException(status_code=403, detail="executor_id does not match the assigned task")

    task = complete_executor_task(db, task, payload)
    return {"success": True, "task": format_executor_task(task)}


@router.get("/executor/tasks")
def get_executor_tasks(
    project_id: int | None = Query(default=None),
    server_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(ExecutorTask).order_by(ExecutorTask.created_at.desc())
    if project_id is not None:
        query = query.filter(ExecutorTask.project_id == project_id)
    if server_id is not None:
        query = query.filter(ExecutorTask.server_id == server_id)
    if status is not None:
        query = query.filter(ExecutorTask.status == status)
    return [format_executor_task(task) for task in query.all()]


@router.get("/executor/tasks/{task_id}")
def get_executor_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(ExecutorTask).filter(ExecutorTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Executor task not found")
    return format_executor_task(task)
