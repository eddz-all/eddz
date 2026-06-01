from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, GitStatus, Project, ProjectServerMapping, Server
from services.formatters import format_environment_snapshot, format_git_status


router = APIRouter(tags=["status"])


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

        server_statuses.append(
            {
                "binding_id": binding.id,
                "server_id": server.id,
                "server_name": server.name,
                "host": server.host,
                "port": server.port,
                "username": server.username,
                "project_path": binding.project_path,
                "latest_git_status": format_git_status(latest_git_status),
                "latest_environment_snapshot": format_environment_snapshot(
                    latest_environment_snapshot
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

        project_statuses.append(
            {
                "binding_id": binding.id,
                "project_id": project.id,
                "project_name": project.name,
                "project_path": binding.project_path,
                "latest_git_status": format_git_status(latest_git_status),
                "latest_environment_snapshot": format_environment_snapshot(
                    latest_environment_snapshot
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
            "description": server.description,
            "created_at": server.created_at,
        },
        "projects": project_statuses,
    }
