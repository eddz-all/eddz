from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, GitStatus, Project, ProjectServerMapping, Server
from schemas import DetectRequest
from services.detector_service import (
    check_server_connection,
    detect_remote_environment,
    detect_remote_git_status,
)
from services.log_service import create_operation_log


router = APIRouter(tags=["detection"])


def _format_git_status(git_status: GitStatus | None):
    if git_status is None:
        return None
    return {
        "id": git_status.id,
        "branch": git_status.branch,
        "remote_url": git_status.remote_url,
        "ahead": git_status.ahead,
        "behind": git_status.behind,
        "has_uncommitted_changes": git_status.has_uncommitted_changes,
        "last_commit": git_status.last_commit,
        "created_at": git_status.created_at,
    }


def _format_environment_snapshot(snapshot: EnvironmentSnapshot | None):
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "os": snapshot.os,
        "architecture": snapshot.architecture,
        "python_version": snapshot.python_version,
        "node_version": snapshot.node_version,
        "docker_installed": snapshot.docker_installed,
        "docker_running": snapshot.docker_running,
        "cuda_version": snapshot.cuda_version,
        "disk_usage": snapshot.disk_usage,
        "raw_data": snapshot.raw_data,
        "created_at": snapshot.created_at,
    }


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
        operation_type="check_connection",
        risk_level="low",
        status="completed" if result.get("connected") else "failed",
        summary=f"Checked connection for {server.name}",
        detail=result.get("message"),
    )

    return {
        "server_id": server.id,
        "server_name": server.name,
        "connection_mode": server.connection_mode,
        "connected": result.get("connected", False),
        "message": result.get("message"),
        "latency_ms": result.get("latency_ms"),
    }


@router.post("/projects/{project_id}/servers/{server_id}/detect")
def detect_project_server(
    project_id: int,
    server_id: int,
    request: DetectRequest | None = None,
    db: Session = Depends(get_db),
):
    request = request or DetectRequest()
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

    git_status = None
    environment_snapshot = None
    errors = []

    if request.detect_git:
        git_result = detect_remote_git_status(
            host=server.host,
            port=server.port,
            username=server.username,
            project_path=binding.project_path,
            connection_mode=server.connection_mode,
        )
        if git_result.get("success"):
            git_status = GitStatus(
                project_id=project.id,
                server_id=server.id,
                branch=git_result.get("branch") or "unknown",
                remote_url=git_result.get("remote_url"),
                ahead=git_result.get("ahead", 0),
                behind=git_result.get("behind", 0),
                has_uncommitted_changes=git_result.get("has_uncommitted_changes", False),
                last_commit=git_result.get("last_commit"),
            )
            db.add(git_status)
        else:
            errors.append(git_result.get("message", "Git detection failed"))

    if request.detect_environment:
        env_result = detect_remote_environment(
            host=server.host,
            port=server.port,
            username=server.username,
            project_path=binding.project_path,
            connection_mode=server.connection_mode,
        )
        if env_result.get("success"):
            environment_snapshot = EnvironmentSnapshot(
                project_id=project.id,
                server_id=server.id,
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
        else:
            errors.append(env_result.get("message", "Environment detection failed"))

    db.commit()
    if git_status is not None:
        db.refresh(git_status)
    if environment_snapshot is not None:
        db.refresh(environment_snapshot)

    status = "completed" if not errors else "failed"
    create_operation_log(
        db=db,
        project_id=project.id,
        server_id=server.id,
        operation_type="detect_project_server",
        risk_level="low" if not errors else "medium",
        status=status,
        summary=f"Detected {project.name} on {server.name}",
        detail="; ".join(errors) if errors else None,
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "server_id": server.id,
        "server_name": server.name,
        "project_path": binding.project_path,
        "connection_mode": server.connection_mode,
        "status": status,
        "error_message": "; ".join(errors) if errors else None,
        "git_status": _format_git_status(git_status),
        "environment_snapshot": _format_environment_snapshot(environment_snapshot),
    }


@router.post("/projects/{project_id}/detect")
def detect_project(
    project_id: int,
    request: DetectRequest | None = None,
    db: Session = Depends(get_db),
):
    request = request or DetectRequest()
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    bindings = (
        db.query(ProjectServerMapping, Server)
        .join(Server, ProjectServerMapping.server_id == Server.id)
        .filter(ProjectServerMapping.project_id == project_id)
        .all()
    )

    results = []
    for binding, server in bindings:
        result = detect_project_server(
            project_id=project_id,
            server_id=server.id,
            request=request,
            db=db,
        )
        results.append(
            {
                "server_id": server.id,
                "server_name": server.name,
                "status": result["status"],
                "error_message": result.get("error_message"),
            }
        )

    status = "completed" if all(item["status"] == "completed" for item in results) else "partial"
    create_operation_log(
        db=db,
        project_id=project.id,
        operation_type="detect_project",
        risk_level="low" if status == "completed" else "medium",
        status=status,
        summary=f"Detected all bound servers for {project.name}",
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "status": status,
        "results": results,
    }
