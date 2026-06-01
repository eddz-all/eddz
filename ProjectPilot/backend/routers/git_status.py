from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import GitStatus, Project, Server
from schemas import GitStatusCreate


router = APIRouter(tags=["git-status"])


@router.post("/projects/{project_id}/git-status")
def create_git_status(
    project_id: int,
    git_status: GitStatusCreate,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if git_status.server_id is not None:
        server = db.query(Server).filter(Server.id == git_status.server_id).first()
        if server is None:
            raise HTTPException(status_code=404, detail="Server not found")

    new_git_status = GitStatus(
        project_id=project_id,
        server_id=git_status.server_id,
        branch=git_status.branch,
        remote_url=git_status.remote_url,
        ahead=git_status.ahead,
        behind=git_status.behind,
        has_uncommitted_changes=git_status.has_uncommitted_changes,
        last_commit=git_status.last_commit,
    )
    db.add(new_git_status)
    db.commit()
    db.refresh(new_git_status)

    return {
        "id": new_git_status.id,
        "project_id": new_git_status.project_id,
        "server_id": new_git_status.server_id,
        "branch": new_git_status.branch,
        "remote_url": new_git_status.remote_url,
        "ahead": new_git_status.ahead,
        "behind": new_git_status.behind,
        "has_uncommitted_changes": new_git_status.has_uncommitted_changes,
        "last_commit": new_git_status.last_commit,
        "created_at": new_git_status.created_at,
    }


@router.get("/projects/{project_id}/git-status")
def get_project_git_statuses(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    git_statuses = (
        db.query(GitStatus)
        .filter(GitStatus.project_id == project_id)
        .order_by(GitStatus.id.desc())
        .all()
    )

    return [
        {
            "id": git_status.id,
            "project_id": git_status.project_id,
            "server_id": git_status.server_id,
            "branch": git_status.branch,
            "remote_url": git_status.remote_url,
            "ahead": git_status.ahead,
            "behind": git_status.behind,
            "has_uncommitted_changes": git_status.has_uncommitted_changes,
            "last_commit": git_status.last_commit,
            "created_at": git_status.created_at,
        }
        for git_status in git_statuses
    ]


@router.get("/servers/{server_id}/git-status")
def get_server_git_statuses(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    git_statuses = (
        db.query(GitStatus, Project)
        .join(Project, GitStatus.project_id == Project.id)
        .filter(GitStatus.server_id == server_id)
        .order_by(GitStatus.id.desc())
        .all()
    )

    return [
        {
            "id": git_status.id,
            "project_id": project.id,
            "project_name": project.name,
            "server_id": git_status.server_id,
            "branch": git_status.branch,
            "remote_url": git_status.remote_url,
            "ahead": git_status.ahead,
            "behind": git_status.behind,
            "has_uncommitted_changes": git_status.has_uncommitted_changes,
            "last_commit": git_status.last_commit,
            "created_at": git_status.created_at,
        }
        for git_status, project in git_statuses
    ]


@router.get("/projects/{project_id}/servers/{server_id}/git-status/latest")
def get_latest_project_server_git_status(
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

    git_status = (
        db.query(GitStatus)
        .filter(GitStatus.project_id == project_id, GitStatus.server_id == server_id)
        .order_by(GitStatus.id.desc())
        .first()
    )

    if git_status is None:
        raise HTTPException(status_code=404, detail="Git status not found")

    return {
        "id": git_status.id,
        "project_id": git_status.project_id,
        "project_name": project.name,
        "server_id": git_status.server_id,
        "server_name": server.name,
        "branch": git_status.branch,
        "remote_url": git_status.remote_url,
        "ahead": git_status.ahead,
        "behind": git_status.behind,
        "has_uncommitted_changes": git_status.has_uncommitted_changes,
        "last_commit": git_status.last_commit,
        "created_at": git_status.created_at,
    }
