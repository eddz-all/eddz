from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Project, ProjectServerMapping, Server
from services.git_worktree_service import inspect_git_worktree, unavailable_git_worktree


router = APIRouter(tags=["git-worktree"])


def should_inspect_on_host(server: Server) -> bool:
    return (server.connection_mode or "").lower() == "local"


@router.get("/projects/{project_id}/git-worktree")
def get_project_git_worktree(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    bindings = (
        db.query(ProjectServerMapping, Server)
        .join(Server, ProjectServerMapping.server_id == Server.id)
        .filter(ProjectServerMapping.project_id == project_id)
        .all()
    )

    repositories = []
    for binding, server in bindings:
        if should_inspect_on_host(server):
            worktree = inspect_git_worktree(binding.project_path)
        else:
            worktree = unavailable_git_worktree(
                binding.project_path,
                reason="remote_path",
                message=(
                    f"{binding.project_path} belongs to {server.name} ({server.connection_mode}); "
                    "the desktop app cannot inspect that remote filesystem directly. "
                    "Run Git detection through the executor or bind a local workspace path."
                ),
            )
        repositories.append(
            {
                **worktree,
                "binding_id": binding.id,
                "project_id": project.id,
                "server_id": server.id,
                "server_name": server.name,
                "connection_mode": server.connection_mode,
            }
        )

    return {
        "schema_version": "git-worktree.v1",
        "project_id": project.id,
        "project_name": project.name,
        "repositories": repositories,
    }
