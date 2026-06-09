from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, Project, Server
from schemas import EnvironmentSnapshotCreate


router = APIRouter(tags=["environment-snapshots"])


@router.post("/projects/{project_id}/env-snapshots")
def create_environment_snapshot(
    project_id: int,
    snapshot: EnvironmentSnapshotCreate,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if snapshot.server_id is not None:
        server = db.query(Server).filter(Server.id == snapshot.server_id).first()
        if server is None:
            raise HTTPException(status_code=404, detail="Server not found")

    new_snapshot = EnvironmentSnapshot(
        project_id=project_id,
        server_id=snapshot.server_id,
        os=snapshot.os,
        architecture=snapshot.architecture,
        python_version=snapshot.python_version,
        node_version=snapshot.node_version,
        docker_installed=snapshot.docker_installed,
        docker_running=snapshot.docker_running,
        cuda_version=snapshot.cuda_version,
        disk_usage=snapshot.disk_usage,
        raw_data=snapshot.raw_data,
    )
    db.add(new_snapshot)
    db.commit()
    db.refresh(new_snapshot)

    return {
        "id": new_snapshot.id,
        "project_id": new_snapshot.project_id,
        "server_id": new_snapshot.server_id,
        "os": new_snapshot.os,
        "architecture": new_snapshot.architecture,
        "python_version": new_snapshot.python_version,
        "node_version": new_snapshot.node_version,
        "docker_installed": new_snapshot.docker_installed,
        "docker_running": new_snapshot.docker_running,
        "cuda_version": new_snapshot.cuda_version,
        "disk_usage": new_snapshot.disk_usage,
        "raw_data": new_snapshot.raw_data,
        "created_at": new_snapshot.created_at,
    }


@router.get("/projects/{project_id}/env-snapshots")
def get_project_environment_snapshots(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    snapshots = (
        db.query(EnvironmentSnapshot)
        .filter(EnvironmentSnapshot.project_id == project_id)
        .order_by(EnvironmentSnapshot.id.desc())
        .all()
    )

    return [
        {
            "id": snapshot.id,
            "project_id": snapshot.project_id,
            "server_id": snapshot.server_id,
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
        for snapshot in snapshots
    ]


@router.get("/servers/{server_id}/env-snapshots")
def get_server_environment_snapshots(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    snapshots = (
        db.query(EnvironmentSnapshot, Project)
        .join(Project, EnvironmentSnapshot.project_id == Project.id)
        .filter(EnvironmentSnapshot.server_id == server_id)
        .order_by(EnvironmentSnapshot.id.desc())
        .all()
    )

    return [
        {
            "id": snapshot.id,
            "project_id": project.id,
            "project_name": project.name,
            "server_id": snapshot.server_id,
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
        for snapshot, project in snapshots
    ]


@router.get("/projects/{project_id}/servers/{server_id}/env-snapshots/latest")
def get_latest_project_server_environment_snapshot(
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

    snapshot = (
        db.query(EnvironmentSnapshot)
        .filter(
            EnvironmentSnapshot.project_id == project_id,
            EnvironmentSnapshot.server_id == server_id,
        )
        .order_by(EnvironmentSnapshot.id.desc())
        .first()
    )

    if snapshot is None:
        raise HTTPException(status_code=404, detail="Environment snapshot not found")

    return {
        "id": snapshot.id,
        "project_id": snapshot.project_id,
        "project_name": project.name,
        "server_id": snapshot.server_id,
        "server_name": server.name,
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
