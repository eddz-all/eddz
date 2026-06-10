from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from database import Base, SessionLocal, engine, migrate_existing_schema
from models import EnvironmentSnapshot, ExecutorTask, GitStatus, OperationLog, Project, ProjectServerMapping, Server
from services.detector_service import detect_local_environment, detect_local_git_status
from services.executor_task_service import create_executor_task
from services.log_service import create_operation_log


REPO_ROOT = Path(__file__).resolve().parents[2]
if (REPO_ROOT / "projectpilot").exists() and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from projectpilot.integration.smart_git import analyze_repository  # noqa: E402


DEMO_ROOT = Path(os.environ.get("PROJECTPILOT_DEMO_ROOT", Path.home() / "work" / "projectpilot-demo")).resolve()
PROJECT_PATH = str(DEMO_ROOT)
PROJECT_NAME = "ProjectPilot Git Workspace Demo"
SERVER_SPECS = [
    ("Demo Diverged Dirty", "diverged-dirty"),
    ("Demo Merge Conflict", "merge-conflict"),
    ("Demo Detached HEAD", "detached-head"),
    ("Demo Wrong Branch", "wrong-branch"),
]


def run(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def configure_repo(repo: Path) -> None:
    run(["git", "config", "user.name", "ProjectPilot Demo"], repo)
    run(["git", "config", "user.email", "demo@projectpilot.local"], repo)
    run(["git", "config", "advice.detachedHead", "false"], repo)


def create_base_repo(repo: Path, remote: Path | None = None) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-b", "main"], repo)
    configure_repo(repo)
    write(repo / "README.md", "# ProjectPilot Git Demo\n")
    write(repo / "app.py", "print('hello from demo')\n")
    write(repo / ".gitignore", ".env\n*.log\n.DS_Store\ndist/\nbuild/\n__pycache__/\n")
    write(repo / "dist" / "bundle.js", "console.log('tracked generated output v1')\n")
    run(["git", "add", "README.md", "app.py", ".gitignore"], repo)
    run(["git", "add", "-f", "dist/bundle.js"], repo)
    run(["git", "commit", "-m", "initial demo app"], repo)
    if remote is not None:
        remote.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "--bare", str(remote)], repo)
        run(["git", "remote", "add", "origin", str(remote)], repo)
        run(["git", "push", "-u", "origin", "main"], repo)
        run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], remote)


def create_remote_commit(remote: Path, relative_path: str, content: str, message: str, peer: Path) -> None:
    run(["git", "clone", str(remote), str(peer)], peer.parent)
    configure_repo(peer)
    write(peer / relative_path, content)
    run(["git", "add", relative_path], peer)
    run(["git", "commit", "-m", message], peer)
    run(["git", "push", "origin", "main"], peer)


def create_diverged_dirty_workspace(workspaces: Path, remotes: Path, peers: Path) -> Path:
    repo = workspaces / "diverged-dirty"
    remote = remotes / "diverged-dirty.git"
    create_base_repo(repo, remote)
    create_remote_commit(remote, "remote.txt", "remote side change\n", "remote side change", peers / "diverged-peer")
    run(["git", "fetch", "origin"], repo)
    write(repo / "local.txt", "local side change\n")
    run(["git", "add", "local.txt"], repo)
    run(["git", "commit", "-m", "local side change"], repo)
    write(repo / "app.py", "print('dirty local draft')\n")
    write(repo / ".env", "PROJECTPILOT_TOKEN=demo-secret\n")
    write(repo / "dist" / "bundle.js", "console.log('tracked generated output v2')\n")
    return repo


def create_conflict_workspace(workspaces: Path) -> Path:
    repo = workspaces / "merge-conflict"
    create_base_repo(repo)
    run(["git", "switch", "-c", "feature/conflict"], repo)
    write(repo / "app.py", "print('feature branch change')\n")
    run(["git", "commit", "-am", "feature branch change"], repo)
    run(["git", "switch", "main"], repo)
    write(repo / "app.py", "print('main branch change')\n")
    run(["git", "commit", "-am", "main branch change"], repo)
    run(["git", "merge", "feature/conflict"], repo, check=False)
    return repo


def create_detached_workspace(workspaces: Path) -> Path:
    repo = workspaces / "detached-head"
    create_base_repo(repo)
    run(["git", "checkout", "--detach", "HEAD"], repo)
    write(repo / "detached-note.md", "work created while detached\n")
    return repo


def create_wrong_branch_workspace(workspaces: Path) -> Path:
    repo = workspaces / "wrong-branch"
    create_base_repo(repo)
    run(["git", "switch", "-c", "feature/wrong-target"], repo)
    write(repo / "feature.py", "print('work on the wrong branch')\n")
    run(["git", "add", "feature.py"], repo)
    run(["git", "commit", "-m", "work on wrong branch"], repo)
    return repo


def recreate_demo_workspaces() -> dict[str, Path]:
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)
    workspaces = DEMO_ROOT / "workspaces"
    remotes = DEMO_ROOT / "remotes"
    peers = DEMO_ROOT / "peers"
    workspaces.mkdir(parents=True)
    remotes.mkdir(parents=True)
    peers.mkdir(parents=True)
    return {
        "diverged-dirty": create_diverged_dirty_workspace(workspaces, remotes, peers),
        "merge-conflict": create_conflict_workspace(workspaces),
        "detached-head": create_detached_workspace(workspaces),
        "wrong-branch": create_wrong_branch_workspace(workspaces),
    }


def clear_existing_demo(db) -> None:
    project = db.query(Project).filter(Project.path == PROJECT_PATH).first()
    server_names = [name for name, _ in SERVER_SPECS]
    servers = db.query(Server).filter(Server.name.in_(server_names)).all()
    project_ids = [project.id] if project is not None else []
    server_ids = [server.id for server in servers]
    if project_ids:
        db.query(GitStatus).filter(GitStatus.project_id.in_(project_ids)).delete(synchronize_session=False)
        db.query(EnvironmentSnapshot).filter(EnvironmentSnapshot.project_id.in_(project_ids)).delete(synchronize_session=False)
        db.query(ExecutorTask).filter(ExecutorTask.project_id.in_(project_ids)).delete(synchronize_session=False)
        db.query(OperationLog).filter(OperationLog.project_id.in_(project_ids)).delete(synchronize_session=False)
        db.query(ProjectServerMapping).filter(ProjectServerMapping.project_id.in_(project_ids)).delete(synchronize_session=False)
        db.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
    if server_ids:
        db.query(ProjectServerMapping).filter(ProjectServerMapping.server_id.in_(server_ids)).delete(synchronize_session=False)
        db.query(GitStatus).filter(GitStatus.server_id.in_(server_ids)).delete(synchronize_session=False)
        db.query(EnvironmentSnapshot).filter(EnvironmentSnapshot.server_id.in_(server_ids)).delete(synchronize_session=False)
        db.query(ExecutorTask).filter(ExecutorTask.server_id.in_(server_ids)).delete(synchronize_session=False)
        db.query(OperationLog).filter(OperationLog.server_id.in_(server_ids)).delete(synchronize_session=False)
        db.query(Server).filter(Server.id.in_(server_ids)).delete(synchronize_session=False)
    db.commit()


def seed_backend(workspace_paths: dict[str, Path]) -> dict:
    Base.metadata.create_all(bind=engine)
    migrate_existing_schema()
    db = SessionLocal()
    try:
        clear_existing_demo(db)
        project = Project(
            name=PROJECT_NAME,
            path=PROJECT_PATH,
            description="Demo project with conflict, dirty, diverged, detached HEAD, wrong branch, and ignore-rule Git states.",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        created = []
        for index, (server_name, key) in enumerate(SERVER_SPECS, start=1):
            repo_path = workspace_paths[key]
            server = Server(
                name=server_name,
                host="127.0.0.1",
                port=2200 + index,
                username=os.environ.get("USER", "demo"),
                connection_mode="local",
                description=f"Local demo workspace: {key}",
            )
            db.add(server)
            db.commit()
            db.refresh(server)
            db.add(ProjectServerMapping(project_id=project.id, server_id=server.id, project_path=str(repo_path)))
            git_result = detect_local_git_status(str(repo_path))
            git_status = GitStatus(
                project_id=project.id,
                server_id=server.id,
                branch=git_result.get("branch") or "unknown",
                remote_url=git_result.get("remote_url"),
                ahead=git_result.get("ahead", 0),
                behind=git_result.get("behind", 0),
                has_uncommitted_changes=git_result.get("has_uncommitted_changes", False),
                last_commit=git_result.get("last_commit"),
            )
            db.add(git_status)
            env_result = detect_local_environment(str(repo_path))
            db.add(
                EnvironmentSnapshot(
                    project_id=project.id,
                    server_id=server.id,
                    os=platform.system(),
                    architecture=platform.machine(),
                    python_version=env_result.get("python_version"),
                    node_version=env_result.get("node_version"),
                    docker_installed=env_result.get("docker_installed", False),
                    docker_running=env_result.get("docker_running", False),
                    cuda_version=env_result.get("cuda_version"),
                    disk_usage=env_result.get("disk_usage"),
                    raw_data=env_result.get("raw_data"),
                )
            )
            db.commit()
            analysis = analyze_repository(repo_path)
            create_executor_task(
                db=db,
                project_id=project.id,
                server_id=server.id,
                task_type="smart_git_analyze",
                status="completed" if analysis.get("success") else "failed",
                executor_id="demo-seed",
                payload={"project_path": str(repo_path)},
                result=analysis,
                error_type=analysis.get("error_type"),
                message=analysis.get("message") or f"Seeded smart Git analysis for {server_name}",
            )
            created.append({"server_id": server.id, "server_name": server.name, "path": str(repo_path)})

        create_operation_log(
            db=db,
            project_id=project.id,
            operation_type="demo_seed",
            risk_level="low",
            status="completed",
            summary="Seeded ProjectPilot Git Workspace demo",
            detail=str(DEMO_ROOT),
        )
        return {"project_id": project.id, "project_name": project.name, "demo_root": str(DEMO_ROOT), "repositories": created}
    finally:
        db.close()


def main() -> int:
    workspace_paths = recreate_demo_workspaces()
    result = seed_backend(workspace_paths)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
