from fastapi import FastAPI

from database import Base, engine, ensure_schema_updates
from routers import ai, bindings, detection, environment_snapshots, execution, executor, git_status, operation_logs, projects, reports, servers, status


Base.metadata.create_all(bind=engine)
ensure_schema_updates()

app = FastAPI(
    title="ProjectPilot Backend",
    description="Backend service for the ProjectPilot project.",
    version="0.1.0",
)

app.include_router(projects.router)
app.include_router(servers.router)
app.include_router(bindings.router)
app.include_router(detection.router)
app.include_router(git_status.router)
app.include_router(environment_snapshots.router)
app.include_router(status.router)
app.include_router(ai.router)
app.include_router(reports.router)
app.include_router(execution.router)
app.include_router(executor.router)
app.include_router(operation_logs.router)


@app.get("/")
def read_root():
    return {"message": "ProjectPilot backend is running"}


@app.get("/health")
def read_status():
    return {"status": "ok"}
