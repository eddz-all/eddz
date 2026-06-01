from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Server
from schemas import ServerCreate


router = APIRouter(tags=["servers"])
VALID_CONNECTION_MODES = {"local", "ssh", "executor"}


def format_server(server: Server):
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
    if server.connection_mode not in VALID_CONNECTION_MODES:
        raise HTTPException(
            status_code=400,
            detail="connection_mode must be local, ssh, or executor",
        )

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

    return format_server(new_server)


@router.get("/servers")
def get_servers(db: Session = Depends(get_db)):
    servers = db.query(Server).all()

    return [format_server(server) for server in servers]


@router.get("/servers/{server_id}")
def get_server_by_id(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()

    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    return format_server(server)


@router.delete("/servers/{server_id}")
def delete_server(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()

    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    db.delete(server)
    db.commit()

    return {"message": "Server deleted successfully"}
