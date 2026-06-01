from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Project, ProjectServerMapping, Server
from schemas import ProjectServerBind


router = APIRouter(tags=["project-server-bindings"])


@router.post("/projects/{project_id}/bind-server")
def bind_server_to_project(
    project_id: int,
    binding: ProjectServerBind,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    server = db.query(Server).filter(Server.id == binding.server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    existing_binding = (
        db.query(ProjectServerMapping)
        .filter(
            ProjectServerMapping.project_id == project_id,
            ProjectServerMapping.server_id == binding.server_id,
        )
        .first()
    )
    if existing_binding is not None:
        raise HTTPException(status_code=400, detail="Project and server are already bound")

    new_binding = ProjectServerMapping(
        project_id=project_id,
        server_id=binding.server_id,
        project_path=binding.project_path,
    )
    db.add(new_binding)
    db.commit()
    db.refresh(new_binding)

    return {
        "id": new_binding.id,
        "project_id": new_binding.project_id,
        "server_id": new_binding.server_id,
        "project_path": new_binding.project_path,
        "created_at": new_binding.created_at,
    }


@router.get("/projects/{project_id}/servers")
def get_project_servers(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    bindings = (
        db.query(ProjectServerMapping, Server)
        .join(Server, ProjectServerMapping.server_id == Server.id)
        .filter(ProjectServerMapping.project_id == project_id)
        .all()
    )

    return [
        {
            "binding_id": binding.id,
            "project_id": binding.project_id,
            "server_id": server.id,
            "server_name": server.name,
            "host": server.host,
            "port": server.port,
            "username": server.username,
            "project_path": binding.project_path,
            "created_at": binding.created_at,
        }
        for binding, server in bindings
    ]


@router.delete("/projects/{project_id}/servers/{server_id}")
def unbind_server_from_project(
    project_id: int,
    server_id: int,
    db: Session = Depends(get_db),
):
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

    db.delete(binding)
    db.commit()

    return {"message": "Project-server binding deleted successfully"}


@router.get("/servers/{server_id}/projects")
def get_server_projects(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    bindings = (
        db.query(ProjectServerMapping, Project)
        .join(Project, ProjectServerMapping.project_id == Project.id)
        .filter(ProjectServerMapping.server_id == server_id)
        .all()
    )

    return [
        {
            "binding_id": binding.id,
            "server_id": binding.server_id,
            "project_id": project.id,
            "project_name": project.name,
            "project_path": binding.project_path,
            "created_at": binding.created_at,
        }
        for binding, project in bindings
    ]
