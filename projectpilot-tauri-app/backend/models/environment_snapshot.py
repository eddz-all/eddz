from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base


class EnvironmentSnapshot(Base):
    __tablename__ = "environment_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    os = Column(String, nullable=True)
    architecture = Column(String, nullable=True)
    python_version = Column(String, nullable=True)
    node_version = Column(String, nullable=True)
    docker_installed = Column(Boolean, nullable=False, default=False)
    docker_running = Column(Boolean, nullable=False, default=False)
    cuda_version = Column(String, nullable=True)
    disk_usage = Column(String, nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
