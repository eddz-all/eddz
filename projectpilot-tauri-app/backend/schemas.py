from typing import Literal

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    path: str
    description: str | None = None


class ServerCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    connection_mode: Literal["local", "ssh", "executor"] = "ssh"
    description: str | None = None


class ProjectServerBind(BaseModel):
    server_id: int
    project_path: str


class GitStatusCreate(BaseModel):
    server_id: int | None = None
    branch: str
    remote_url: str | None = None
    ahead: int = 0
    behind: int = 0
    has_uncommitted_changes: bool = False
    last_commit: str | None = None


class EnvironmentSnapshotCreate(BaseModel):
    server_id: int | None = None
    os: str | None = None
    architecture: str | None = None
    python_version: str | None = None
    node_version: str | None = None
    docker_installed: bool = False
    docker_running: bool = False
    cuda_version: str | None = None
    disk_usage: str | None = None
    raw_data: dict | None = None


class DetectRequest(BaseModel):
    detect_git: bool = True
    detect_environment: bool = True


class AIAnalyzeRequest(BaseModel):
    question: str | None = None
    focus: str = "environment"


class GitAnalyzeRequest(BaseModel):
    analyses: list[str] | None = None


class ProjectReportRequest(BaseModel):
    project_id: int
    include_ai_analysis: bool = True


class ConfigPlanRequest(BaseModel):
    source_server_id: int | None = None
    target_server_id: int
    goal: str = "让目标服务器可以运行该项目"
    allow_command_generation: bool = True


class ConfigPlanStepExecute(BaseModel):
    order: int
    title: str | None = None
    command: str | None = None
    risk_level: str | None = None


class ExecuteConfigPlanRequest(BaseModel):
    confirmed: bool
    steps: list[ConfigPlanStepExecute]
