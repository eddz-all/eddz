from database import Base, SessionLocal, engine, migrate_existing_schema
from models import EnvironmentSnapshot, GitStatus, Project, ProjectServerMapping, Server


def seed_data():
    Base.metadata.create_all(bind=engine)
    migrate_existing_schema()

    db = SessionLocal()
    try:
        project_pilot = db.query(Project).filter(Project.path == "/demo/projectpilot").first()
        if project_pilot is None:
            project_pilot = Project(
                name="ProjectPilot",
                path="/demo/projectpilot",
                description="AI project environment management platform",
            )
            db.add(project_pilot)

        demo_app = db.query(Project).filter(Project.path == "/demo/demo-app").first()
        if demo_app is None:
            demo_app = Project(
                name="DemoApp",
                path="/demo/demo-app",
                description="Demo project for backend testing",
            )
            db.add(demo_app)

        server_a = (
            db.query(Server)
            .filter(Server.host == "192.168.1.100", Server.port == 22)
            .first()
        )
        if server_a is None:
            server_a = Server(
                name="server-a",
                host="192.168.1.100",
                port=22,
                username="ubuntu",
                connection_mode="ssh",
                description="Primary test server",
            )
            db.add(server_a)

        server_b = (
            db.query(Server)
            .filter(Server.host == "192.168.1.101", Server.port == 22)
            .first()
        )
        if server_b is None:
            server_b = Server(
                name="server-b",
                host="192.168.1.101",
                port=22,
                username="root",
                connection_mode="ssh",
                description="Secondary test server",
            )
            db.add(server_b)

        db.commit()
        db.refresh(project_pilot)
        db.refresh(demo_app)
        db.refresh(server_a)
        db.refresh(server_b)

        bindings = [
            (project_pilot, server_a, "/opt/projectpilot"),
            (project_pilot, server_b, "/srv/projectpilot"),
            (demo_app, server_a, "/opt/demo-app"),
        ]
        for project, server, project_path in bindings:
            existing_binding = (
                db.query(ProjectServerMapping)
                .filter(
                    ProjectServerMapping.project_id == project.id,
                    ProjectServerMapping.server_id == server.id,
                )
                .first()
            )
            if existing_binding is None:
                db.add(
                    ProjectServerMapping(
                        project_id=project.id,
                        server_id=server.id,
                        project_path=project_path,
                    )
                )

        git_statuses = [
            (project_pilot, server_a, "main", 0, 1, False, "a1b2c3d update api"),
            (project_pilot, server_a, "main", 1, 0, True, "d4e5f6g add git status"),
            (project_pilot, server_b, "dev", 2, 0, False, "h7i8j9k test deploy"),
            (demo_app, server_a, "main", 0, 0, False, "l1m2n3o initial demo"),
        ]
        for project, server, branch, ahead, behind, has_changes, last_commit in git_statuses:
            db.add(
                GitStatus(
                    project_id=project.id,
                    server_id=server.id,
                    branch=branch,
                    remote_url=f"git@example.com:team/{project.name.lower()}.git",
                    ahead=ahead,
                    behind=behind,
                    has_uncommitted_changes=has_changes,
                    last_commit=last_commit,
                )
            )

        environment_snapshots = [
            (
                project_pilot,
                server_a,
                "Linux",
                "x86_64",
                "3.11.8",
                "20.11.0",
                True,
                True,
                "12.1",
                "68%",
                {
                    "python_packages": {
                        "fastapi": "0.136.1",
                        "numpy": "1.26.4",
                        "sqlalchemy": "2.0.0",
                    },
                    "commands": {
                        "git": "2.43.0",
                        "docker": "26.1.0",
                    },
                },
            ),
            (
                project_pilot,
                server_b,
                "Linux",
                "x86_64",
                "3.9.18",
                "18.19.0",
                True,
                False,
                None,
                "82%",
                {
                    "python_packages": {
                        "fastapi": "0.110.0",
                        "numpy": "1.24.0",
                    },
                    "commands": {
                        "git": "2.39.0",
                        "docker": "24.0.0",
                    },
                },
            ),
            (
                demo_app,
                server_a,
                "Linux",
                "x86_64",
                "3.10.12",
                "20.11.0",
                True,
                True,
                None,
                "55%",
                {
                    "node_packages": {
                        "vite": "5.0.0",
                        "typescript": "5.4.0",
                    },
                    "commands": {
                        "git": "2.43.0",
                        "node": "20.11.0",
                    },
                },
            ),
        ]
        for (
            project,
            server,
            os_name,
            architecture,
            python_version,
            node_version,
            docker_installed,
            docker_running,
            cuda_version,
            disk_usage,
            raw_data,
        ) in environment_snapshots:
            db.add(
                EnvironmentSnapshot(
                    project_id=project.id,
                    server_id=server.id,
                    os=os_name,
                    architecture=architecture,
                    python_version=python_version,
                    node_version=node_version,
                    docker_installed=docker_installed,
                    docker_running=docker_running,
                    cuda_version=cuda_version,
                    disk_usage=disk_usage,
                    raw_data=raw_data,
                )
            )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
    print("Seed data inserted successfully.")
