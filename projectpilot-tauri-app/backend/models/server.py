from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from database import Base


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False, default=22)
    username = Column(String, nullable=False)
    connection_mode = Column(String, nullable=False, default="ssh")
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
