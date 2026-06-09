from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, migrate_existing_schema
from routers import (
    ai,
    bindings,
    detection,
    debug,
    environment_snapshots,
    execution,
    git_status,
    operation_logs,
    projects,
    reports,
    servers,
    status,
)


Base.metadata.create_all(bind=engine)
migrate_existing_schema()

app = FastAPI(
    title="ProjectPilot Backend",
    description="Backend service for the ProjectPilot project.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "tauri://localhost",
    ],
    allow_origin_regex=r"https?://127\.0\.0\.1:\d+|https?://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(servers.router)
app.include_router(bindings.router)
app.include_router(git_status.router)
app.include_router(environment_snapshots.router)
app.include_router(status.router)
app.include_router(ai.router)
app.include_router(reports.router)
app.include_router(execution.router)
app.include_router(detection.router)
app.include_router(operation_logs.router)
app.include_router(debug.router)


@app.get("/")
def read_root():
    return {"message": "ProjectPilot backend is running"}


@app.get("/health")
def read_status():
    return {"status": "ok"}
