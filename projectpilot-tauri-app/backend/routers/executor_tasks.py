from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models import ExecutorTask
from services.executor_task_service import format_executor_task


router = APIRouter(prefix="/executor/tasks", tags=["executor-tasks"])


@router.get("")
def list_executor_tasks(
    project_id: int | None = None,
    server_id: int | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(ExecutorTask)
    if project_id is not None:
        query = query.filter(ExecutorTask.project_id == project_id)
    if server_id is not None:
        query = query.filter(ExecutorTask.server_id == server_id)
    if status:
        query = query.filter(ExecutorTask.status == status)

    tasks = query.order_by(ExecutorTask.created_at.desc(), ExecutorTask.id.desc()).limit(limit).all()
    return [format_executor_task(task) for task in tasks]


@router.get("/{task_id}")
def get_executor_task(task_id: str, db: Session = Depends(get_db)):
    filters = [ExecutorTask.public_id == task_id]
    if task_id.isdigit():
        filters.append(ExecutorTask.id == int(task_id))

    task = db.query(ExecutorTask).filter(or_(*filters)).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Executor task not found")
    return format_executor_task(task)
