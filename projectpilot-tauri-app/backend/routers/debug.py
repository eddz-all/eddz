from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Project, ProjectServerMapping, Server
from services.log_service import create_operation_log


router = APIRouter(tags=["debug"])


@router.post("/debug/local-fixture")
def create_local_debug_fixture(db: Session = Depends(get_db)):
    app_root = Path(__file__).resolve().parents[2]
    project_path = str(app_root)

    project = db.query(Project).filter(Project.path == project_path).first()
    if project is None:
        project = Project(
            name="Local Debug Project",
            path=project_path,
            description="Uses this computer as a fake server for no-server debugging.",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

    server = db.query(Server).filter(Server.host == "127.0.0.1", Server.port == 22).first()
    if server is None:
        server = Server(
            name="local-computer",
            host="127.0.0.1",
            port=22,
            username="local",
            connection_mode="local",
            description="This machine, used as a debug server.",
        )
        db.add(server)
        db.commit()
        db.refresh(server)

    binding = (
        db.query(ProjectServerMapping)
        .filter(
            ProjectServerMapping.project_id == project.id,
            ProjectServerMapping.server_id == server.id,
        )
        .first()
    )
    if binding is None:
        binding = ProjectServerMapping(
            project_id=project.id,
            server_id=server.id,
            project_path=project_path,
        )
        db.add(binding)
        db.commit()
        db.refresh(binding)

    create_operation_log(
        db=db,
        project_id=project.id,
        server_id=server.id,
        operation_type="create_local_debug_fixture",
        risk_level="low",
        status="completed",
        summary="Created local debug project and server fixture",
        detail=project_path,
    )

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "path": project.path,
            "description": project.description,
            "created_at": project.created_at,
        },
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
        "binding": {
            "id": binding.id,
            "project_id": binding.project_id,
            "server_id": binding.server_id,
            "project_path": binding.project_path,
            "created_at": binding.created_at,
        },
    }
