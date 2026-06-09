from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, ExecutorTask, GitStatus, Project, ProjectServerMapping, Server
from services.formatters import format_environment_snapshot, format_git_status


router = APIRouter(tags=["status"])


def task_event_time(task: ExecutorTask | None):
    if task is None:
        return None
    return task.completed_at or task.claimed_at or task.created_at


def record_event_time(record):
    if record is None:
        return None
    return getattr(record, "created_at", None)


def format_executor_task_summary(task: ExecutorTask | None):
    if task is None:
        return None
    result = task.result if isinstance(task.result, dict) else None
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "executor_id": task.executor_id,
        "error_type": task.error_type,
        "message": task.message or (result or {}).get("message"),
        "created_at": task.created_at,
        "claimed_at": task.claimed_at,
        "completed_at": task.completed_at,
        "result": result,
    }


def latest_task_for(db: Session, project_id: int, server_id: int, task_type: str):
    return (
        db.query(ExecutorTask)
        .filter(
            ExecutorTask.project_id == project_id,
            ExecutorTask.server_id == server_id,
            ExecutorTask.task_type == task_type,
        )
        .order_by(ExecutorTask.created_at.desc())
        .first()
    )


def resolve_git_view(latest_git_status, latest_git_task: ExecutorTask | None):
    if latest_git_task is None:
        return format_git_status(latest_git_status)

    task_time = task_event_time(latest_git_task)
    status_time = record_event_time(latest_git_status)
    if task_time is None or (status_time is not None and task_time <= status_time):
        return format_git_status(latest_git_status)

    if latest_git_task.status == "completed":
        return format_git_status(latest_git_status)

    return None


def resolve_environment_view(latest_snapshot, latest_env_task: ExecutorTask | None):
    if latest_env_task is None:
        return format_environment_snapshot(latest_snapshot)

    task_time = task_event_time(latest_env_task)
    snapshot_time = record_event_time(latest_snapshot)
    if task_time is None or (snapshot_time is not None and task_time <= snapshot_time):
        return format_environment_snapshot(latest_snapshot)

    if latest_env_task.status == "completed":
        return format_environment_snapshot(latest_snapshot)

    return None


@router.get("/projects/{project_id}/status")
def get_project_status(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    bindings = (
        db.query(ProjectServerMapping, Server)
        .join(Server, ProjectServerMapping.server_id == Server.id)
        .filter(ProjectServerMapping.project_id == project_id)
        .all()
    )

    server_statuses = []
    for binding, server in bindings:
        latest_git_status = (
            db.query(GitStatus)
            .filter(GitStatus.project_id == project_id, GitStatus.server_id == server.id)
            .order_by(GitStatus.id.desc())
            .first()
        )
        latest_environment_snapshot = (
            db.query(EnvironmentSnapshot)
            .filter(
                EnvironmentSnapshot.project_id == project_id,
                EnvironmentSnapshot.server_id == server.id,
            )
            .order_by(EnvironmentSnapshot.id.desc())
            .first()
        )
        latest_git_task = latest_task_for(db, project_id, server.id, "detect_git")
        latest_env_task = latest_task_for(db, project_id, server.id, "detect_environment")

        server_statuses.append(
            {
                "binding_id": binding.id,
                "server_id": server.id,
                "server_name": server.name,
                "host": server.host,
                "port": server.port,
                "username": server.username,
                "connection_mode": server.connection_mode,
                "project_path": binding.project_path,
                "latest_git_status": resolve_git_view(latest_git_status, latest_git_task),
                "latest_environment_snapshot": resolve_environment_view(
                    latest_environment_snapshot, latest_env_task
                ),
                "latest_git_detection": format_executor_task_summary(latest_git_task),
                "latest_environment_detection": format_executor_task_summary(
                    latest_env_task
                ),
            }
        )

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "path": project.path,
            "description": project.description,
            "created_at": project.created_at,
        },
        "servers": server_statuses,
    }


@router.get("/servers/{server_id}/status")
def get_server_status(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    bindings = (
        db.query(ProjectServerMapping, Project)
        .join(Project, ProjectServerMapping.project_id == Project.id)
        .filter(ProjectServerMapping.server_id == server_id)
        .all()
    )

    project_statuses = []
    for binding, project in bindings:
        latest_git_status = (
            db.query(GitStatus)
            .filter(GitStatus.project_id == project.id, GitStatus.server_id == server_id)
            .order_by(GitStatus.id.desc())
            .first()
        )
        latest_environment_snapshot = (
            db.query(EnvironmentSnapshot)
            .filter(
                EnvironmentSnapshot.project_id == project.id,
                EnvironmentSnapshot.server_id == server_id,
            )
            .order_by(EnvironmentSnapshot.id.desc())
            .first()
        )
        latest_git_task = latest_task_for(db, project.id, server_id, "detect_git")
        latest_env_task = latest_task_for(db, project.id, server_id, "detect_environment")

        project_statuses.append(
            {
                "binding_id": binding.id,
                "project_id": project.id,
                "project_name": project.name,
                "project_path": binding.project_path,
                "latest_git_status": resolve_git_view(latest_git_status, latest_git_task),
                "latest_environment_snapshot": resolve_environment_view(
                    latest_environment_snapshot, latest_env_task
                ),
                "latest_git_detection": format_executor_task_summary(latest_git_task),
                "latest_environment_detection": format_executor_task_summary(
                    latest_env_task
                ),
            }
        )

    return {
        "server": {
            "id": server.id,
            "name": server.name,
            "host": server.host,
            "port": server.port,
            "username": server.username,
            "connection_mode": server.connection_mode,
            "description": server.description,
            "created_at": server.created_at,
        },
        "projects": project_statuses,
    }
