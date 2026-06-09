from sqlalchemy import create_engine, inspect, text
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


def migrate_existing_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "servers" not in table_names:
        return

    server_columns = {column["name"] for column in inspector.get_columns("servers")}

    with engine.begin() as connection:
        if "connection_mode" not in server_columns:
            connection.execute(
                text("ALTER TABLE servers ADD COLUMN connection_mode VARCHAR DEFAULT 'ssh' NOT NULL")
            )
            connection.execute(
                text(
                    "UPDATE servers "
                    "SET connection_mode = 'local' "
                    "WHERE host IN ('127.0.0.1', 'localhost', '::1')"
                )
            )

        required_tables = {
            "projects",
            "servers",
            "project_server_mappings",
            "git_statuses",
            "environment_snapshots",
            "operation_logs",
        }
        if not required_tables.issubset(table_names):
            return

        connection.execute(
            text(
                "DELETE FROM project_server_mappings "
                "WHERE project_id NOT IN (SELECT id FROM projects) "
                "OR server_id NOT IN (SELECT id FROM servers)"
            )
        )
        connection.execute(
            text(
                "DELETE FROM git_statuses "
                "WHERE project_id NOT IN (SELECT id FROM projects) "
                "OR server_id NOT IN (SELECT id FROM servers)"
            )
        )
        connection.execute(
            text(
                "DELETE FROM environment_snapshots "
                "WHERE project_id NOT IN (SELECT id FROM projects) "
                "OR server_id NOT IN (SELECT id FROM servers)"
            )
        )
        connection.execute(
            text(
                "DELETE FROM operation_logs "
                "WHERE (project_id IS NOT NULL AND project_id NOT IN (SELECT id FROM projects)) "
                "OR (server_id IS NOT NULL AND server_id NOT IN (SELECT id FROM servers))"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
