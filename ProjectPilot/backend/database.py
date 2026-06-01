from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = "sqlite:///./projectpilot.db"

# Engine is the core connection object used to talk to the database.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# SessionLocal is used later when we want to read or write data.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class that database models will inherit from.
Base = declarative_base()


def ensure_schema_updates():
    with engine.begin() as connection:
        server_columns = connection.execute(text("PRAGMA table_info(servers)")).fetchall()
        server_column_names = {column[1] for column in server_columns}
        if "connection_mode" not in server_column_names:
            connection.execute(
                text(
                    "ALTER TABLE servers "
                    "ADD COLUMN connection_mode VARCHAR NOT NULL DEFAULT 'ssh'"
                )
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
