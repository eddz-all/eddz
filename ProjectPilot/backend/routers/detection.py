from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, GitStatus, Project, ProjectServerMapping, Server
from services.detection_service import (
    check_server_connection,
    detect_remote_environment,
    detect_remote_git_status,
)
from services.executor_task_service import create_executor_task, format_executor_task
from services.formatters import format_environment_snapshot, format_git_status
from services.log_service import create_operation_log, format_operation_log


router = APIRouter(tags=["detection"])


@router.post("/servers/{server_id}/check-connection")
def check_connection(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    result = check_server_connection(
        host=server.host,
        port=server.port,
        username=server.username,
        connection_mode=server.connection_mode,
    )

    create_operation_log(
        db=db,
        server_id=server.id,
        operation_type="check_server_connection",
        risk_level="low",
        status="completed" if result.get("connected") else "failed",
        summary="检测服务器连接状态",
        confirmed=False,
        details=result,
        error_message=None if result.get("connected") else result.get("message"),
    )

    return {
        "server_id": server.id,
        "server_name": server.name,
        "host": server.host,
        "port": server.port,
        "connection_mode": server.connection_mode,
        "connected": result.get("connected", False),
        "message": result.get("message"),
        "latency_ms": result.get("latency_ms"),
    }


@router.post("/projects/{project_id}/servers/{server_id}/detect")
def detect_project_on_server(
    project_id: int,
    server_id: int,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    binding = (
        db.query(ProjectServerMapping)
        .filter(
            ProjectServerMapping.project_id == project_id,
            ProjectServerMapping.server_id == server_id,
        )
        .first()
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Project-server binding not found")

    if server.connection_mode == "executor":
        executor_id = server.name
        git_task = create_executor_task(
            db=db,
            project_id=project.id,
            server_id=server.id,
            task_type="detect_git",
            payload={
                "project_path": binding.project_path,
                "connection_mode": server.connection_mode,
                "risk_level": "low",
            },
            executor_id=executor_id,
            summary="等待 Executor 检测 Git 状态",
        )
        env_task = create_executor_task(
            db=db,
            project_id=project.id,
            server_id=server.id,
            task_type="detect_environment",
            payload={
                "project_path": binding.project_path,
                "connection_mode": server.connection_mode,
                "risk_level": "low",
            },
            executor_id=executor_id,
            summary="等待 Executor 检测环境状态",
        )
        log = create_operation_log(
            db=db,
            project_id=project.id,
            server_id=server.id,
            operation_type="detect_project_on_server",
            risk_level="low",
            status="queued",
            summary="已创建 Executor 检测任务",
            confirmed=False,
            details={
                "project_path": binding.project_path,
                "connection_mode": server.connection_mode,
                "executor_id": executor_id,
                "task_ids": [git_task.id, env_task.id],
            },
        )
        return {
            "project_id": project.id,
            "project_name": project.name,
            "server_id": server.id,
            "server_name": server.name,
            "project_path": binding.project_path,
            "connection_mode": server.connection_mode,
            "status": "queued",
            "message": "Executor tasks created and waiting for agent polling.",
            "tasks": [format_executor_task(git_task), format_executor_task(env_task)],
            "operation_log": format_operation_log(log),
        }

    git_result = detect_remote_git_status(
        host=server.host,
        port=server.port,
        username=server.username,
        project_path=binding.project_path,
        connection_mode=server.connection_mode,
    )
    if not git_result["success"]:
        raise HTTPException(status_code=500, detail=git_result["message"])

    env_result = detect_remote_environment(
        host=server.host,
        port=server.port,
        username=server.username,
        project_path=binding.project_path,
        connection_mode=server.connection_mode,
    )
    if not env_result["success"]:
        raise HTTPException(status_code=500, detail=env_result["message"])

    git_status = GitStatus(
        project_id=project_id,
        server_id=server_id,
        branch=git_result["branch"],
        remote_url=git_result.get("remote_url"),
        ahead=git_result.get("ahead", 0),
        behind=git_result.get("behind", 0),
        has_uncommitted_changes=git_result.get("has_uncommitted_changes", False),
        last_commit=git_result.get("last_commit"),
    )
    db.add(git_status)

    environment_snapshot = EnvironmentSnapshot(
        project_id=project_id,
        server_id=server_id,
        os=env_result.get("os"),
        architecture=env_result.get("architecture"),
        python_version=env_result.get("python_version"),
        node_version=env_result.get("node_version"),
        docker_installed=env_result.get("docker_installed", False),
        docker_running=env_result.get("docker_running", False),
        cuda_version=env_result.get("cuda_version"),
        disk_usage=env_result.get("disk_usage"),
        raw_data=env_result.get("raw_data"),
    )
    db.add(environment_snapshot)
    db.commit()
    db.refresh(git_status)
    db.refresh(environment_snapshot)

    log = create_operation_log(
        db=db,
        project_id=project.id,
        server_id=server.id,
        operation_type="detect_project_on_server",
        risk_level="low",
        status="completed",
        summary="检测项目在服务器上的 Git 状态和环境状态",
        confirmed=False,
        details={
            "project_path": binding.project_path,
            "connection_mode": server.connection_mode,
            "git_result": git_result,
            "environment_result": env_result,
        },
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "server_id": server.id,
        "server_name": server.name,
        "project_path": binding.project_path,
        "connection_mode": server.connection_mode,
        "status": "completed",
        "git_status": format_git_status(git_status),
        "environment_snapshot": format_environment_snapshot(environment_snapshot),
        "operation_log": format_operation_log(log),
    }
