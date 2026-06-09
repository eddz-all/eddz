from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, GitStatus, OperationLog, ProjectServerMapping, Server
from schemas import ServerCreate


router = APIRouter(tags=["servers"])


def _format_server(server: Server):
    return {
        "id": server.id,
        "name": server.name,
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "connection_mode": server.connection_mode,
        "description": server.description,
        "created_at": server.created_at,
    }


@router.post("/servers")
def create_server(server: ServerCreate, db: Session = Depends(get_db)):
    existing_server = (
        db.query(Server)
        .filter(Server.host == server.host, Server.port == server.port)
        .first()
    )

    if existing_server is not None:
        raise HTTPException(status_code=400, detail="Server host and port already exist")

    new_server = Server(
        name=server.name,
        host=server.host,
        port=server.port,
        username=server.username,
        connection_mode=server.connection_mode,
        description=server.description,
    )
    db.add(new_server)
    db.commit()
    db.refresh(new_server)

    return _format_server(new_server)


@router.get("/servers")
def get_servers(db: Session = Depends(get_db)):
    servers = db.query(Server).all()

    return [_format_server(server) for server in servers]


@router.get("/servers/{server_id}")
def get_server_by_id(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()

    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    return _format_server(server)


@router.delete("/servers/{server_id}")
def delete_server(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()

    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    db.query(OperationLog).filter(OperationLog.server_id == server_id).delete(
        synchronize_session=False
    )
    db.query(EnvironmentSnapshot).filter(
        EnvironmentSnapshot.server_id == server_id
    ).delete(synchronize_session=False)
    db.query(GitStatus).filter(GitStatus.server_id == server_id).delete(
        synchronize_session=False
    )
    db.query(ProjectServerMapping).filter(
        ProjectServerMapping.server_id == server_id
    ).delete(synchronize_session=False)
    db.delete(server)
    db.commit()

    return {"message": "Server deleted successfully"}
