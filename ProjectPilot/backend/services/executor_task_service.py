import uuid
from datetime import datetime, timezone

from models import EnvironmentSnapshot, ExecutorTask, GitStatus
from services.log_service import create_operation_log


TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"


def utc_now():
    return datetime.now(timezone.utc)


def make_task_id():
    return f"task_{uuid.uuid4().hex}"


def format_executor_task(task: ExecutorTask):
    return {
        "id": task.id,
        "project_id": task.project_id,
        "server_id": task.server_id,
        "task_type": task.task_type,
        "status": task.status,
        "payload": task.payload,
        "result": task.result,
        "executor_id": task.executor_id,
        "error_type": task.error_type,
        "message": task.message,
        "created_at": task.created_at,
        "claimed_at": task.claimed_at,
        "completed_at": task.completed_at,
    }


def create_executor_task(
    db,
    *,
    project_id: int | None,
    server_id: int | None,
    task_type: str,
    payload: dict,
    executor_id: str,
    summary: str,
    risk_level: str = "low",
    confirmed: bool = False,
):
    task = ExecutorTask(
        id=make_task_id(),
        project_id=project_id,
        server_id=server_id,
        task_type=task_type,
        status=TASK_STATUS_QUEUED,
        payload=payload,
        executor_id=executor_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    create_operation_log(
        db=db,
        project_id=project_id,
        server_id=server_id,
        operation_type=f"executor_task:{task_type}",
        risk_level=risk_level,
        status=TASK_STATUS_QUEUED,
        summary=summary,
        confirmed=confirmed,
        details={
            "task_id": task.id,
            "executor_id": executor_id,
            "payload": payload,
        },
    )
    return task


def claim_next_executor_task(db, executor_id: str, capabilities: list[str]):
    tasks = (
        db.query(ExecutorTask)
        .filter(
            ExecutorTask.status == TASK_STATUS_QUEUED,
            ExecutorTask.executor_id == executor_id,
        )
        .order_by(ExecutorTask.created_at.asc())
        .all()
    )
    capability_set = set(capabilities)
    for task in tasks:
        if task.task_type not in capability_set:
            continue
        task.status = TASK_STATUS_RUNNING
        task.claimed_at = utc_now()
        db.commit()
        db.refresh(task)
        create_operation_log(
            db=db,
            project_id=task.project_id,
            server_id=task.server_id,
            operation_type=f"executor_task:{task.task_type}",
            risk_level=str((task.payload or {}).get("risk_level") or "low"),
            status=TASK_STATUS_RUNNING,
            summary="Executor claimed task",
            confirmed=bool((task.payload or {}).get("approved", False)),
            details={
                "task_id": task.id,
                "executor_id": executor_id,
                "capabilities": capabilities,
            },
        )
        return task
    return None


def executor_task_to_agent_payload(task: ExecutorTask):
    payload = dict(task.payload or {})
    payload.setdefault("id", task.id)
    payload.setdefault("type", task.task_type)
    if task.project_id is not None:
        payload.setdefault("project_id", task.project_id)
    if task.server_id is not None:
        payload.setdefault("server_id", task.server_id)
    return payload


def complete_executor_task(db, task: ExecutorTask, payload: dict):
    result = payload.get("result")
    if not isinstance(result, dict):
        result = {}

    success = bool(payload.get("success", False))
    task.status = TASK_STATUS_COMPLETED if success else TASK_STATUS_FAILED
    task.result = result
    task.error_type = payload.get("error_type") or result.get("error_type")
    task.message = payload.get("message") or result.get("message")
    task.completed_at = utc_now()
    db.commit()
    db.refresh(task)

    project_id = task.project_id
    server_id = task.server_id

    persist_task_artifact(db, task, result)
    create_operation_log(
        db=db,
        project_id=project_id,
        server_id=server_id,
        operation_type=f"executor_task:{task.task_type}",
        risk_level=str((task.payload or {}).get("risk_level") or "low"),
        status=task.status,
        summary="Executor task finished",
        confirmed=bool((task.payload or {}).get("approved", False)),
        details={
            "task_id": task.id,
            "executor_id": payload.get("executor_id"),
            "result": result,
        },
        output=result.get("stdout"),
        error_message=task.message if not success else None,
    )
    return task


def persist_task_artifact(db, task: ExecutorTask, result: dict):
    project_id = task.project_id
    server_id = task.server_id
    if not result.get("success") or project_id is None:
        return

    if task.task_type == "detect_git":
        git_status = GitStatus(
            project_id=project_id,
            server_id=server_id,
            branch=str(result.get("branch") or "(unknown)"),
            remote_url=result.get("remote_url"),
            ahead=int(result.get("ahead") or 0),
            behind=int(result.get("behind") or 0),
            has_uncommitted_changes=bool(result.get("has_uncommitted_changes", False)),
            last_commit=result.get("last_commit"),
        )
        db.add(git_status)
        db.commit()
        return

    if task.task_type == "detect_environment":
        snapshot = EnvironmentSnapshot(
            project_id=project_id,
            server_id=server_id,
            os=result.get("os"),
            architecture=result.get("architecture"),
            python_version=result.get("python_version"),
            node_version=result.get("node_version"),
            docker_installed=bool(result.get("docker_installed", False)),
            docker_running=bool(result.get("docker_running", False)),
            cuda_version=result.get("cuda_version"),
            disk_usage=result.get("disk_usage"),
            raw_data=result.get("raw_data"),
        )
        db.add(snapshot)
        db.commit()
