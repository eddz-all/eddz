from models import EnvironmentSnapshot, GitStatus


def format_git_status(git_status: GitStatus | None):
    if git_status is None:
        return None

    return {
        "id": git_status.id,
        "project_id": git_status.project_id,
        "server_id": git_status.server_id,
        "branch": git_status.branch,
        "remote_url": git_status.remote_url,
        "ahead": git_status.ahead,
        "behind": git_status.behind,
        "has_uncommitted_changes": git_status.has_uncommitted_changes,
        "last_commit": git_status.last_commit,
        "created_at": git_status.created_at,
    }


def format_environment_snapshot(snapshot: EnvironmentSnapshot | None):
    if snapshot is None:
        return None

    return {
        "id": snapshot.id,
        "project_id": snapshot.project_id,
        "server_id": snapshot.server_id,
        "os": snapshot.os,
        "architecture": snapshot.architecture,
        "python_version": snapshot.python_version,
        "node_version": snapshot.node_version,
        "docker_installed": snapshot.docker_installed,
        "docker_running": snapshot.docker_running,
        "cuda_version": snapshot.cuda_version,
        "disk_usage": snapshot.disk_usage,
        "raw_data": snapshot.raw_data,
        "created_at": snapshot.created_at,
    }
