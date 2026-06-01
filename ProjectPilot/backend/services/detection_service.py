from services.eddz_bridge import (
    bridge_check_connection,
    bridge_detect_local_environment,
    bridge_detect_local_git_status,
    bridge_detect_remote_environment,
    bridge_detect_remote_git_status,
    integration_runtime,
)


def detect_remote_git_status(
    host: str,
    port: int,
    username: str,
    project_path: str,
    connection_mode: str = "ssh",
):
    member_b_error = None
    if connection_mode == "local" and bridge_detect_local_git_status is not None:
        result = bridge_detect_local_git_status(project_path)
        if result.get("success"):
            result["source"] = "eddz_local"
            return result
        member_b_error = result

    if connection_mode == "ssh" and bridge_detect_remote_git_status is not None:
        result = bridge_detect_remote_git_status(host, project_path, timeout=20, auth_mode="key")
        if result.get("success"):
            result["source"] = "eddz_ssh"
            return result
        return result

    if connection_mode == "executor":
        return {
            "success": False,
            "error_type": "executor_not_implemented",
            "message": "Executor mode is reserved but not implemented in this backend yet.",
            "connection_mode": connection_mode,
        }

    return {
        "success": True,
        "source": "mock_detection",
        "connection_mode": connection_mode,
        "branch": "main",
        "remote_url": "git@example.com:team/projectpilot.git",
        "ahead": 1,
        "behind": 0,
        "has_uncommitted_changes": False,
        "last_commit": "mock123 simulated remote git status",
        "member_b_error": member_b_error,
        "integration_runtime": integration_runtime(),
    }


def check_server_connection(
    host: str,
    port: int,
    username: str,
    connection_mode: str = "ssh",
):
    if connection_mode == "local":
        return {
            "success": True,
            "connected": True,
            "connection_mode": connection_mode,
            "message": "Local connection is available",
            "latency_ms": 0,
        }

    if connection_mode == "ssh" and bridge_check_connection is not None:
        result = bridge_check_connection(host, timeout=15, auth_mode="key")
        result["source"] = "eddz_ssh"
        return result

    if connection_mode == "executor":
        return {
            "success": False,
            "connected": False,
            "connection_mode": connection_mode,
            "message": "Executor mode does not support direct connection checks from the backend.",
            "latency_ms": None,
        }

    return {
        "success": True,
        "connected": True,
        "connection_mode": connection_mode,
        "message": "Connection successful",
        "latency_ms": 35,
    }


def detect_remote_environment(
    host: str,
    port: int,
    username: str,
    project_path: str | None = None,
    connection_mode: str = "ssh",
):
    member_b_error = None
    if connection_mode == "local" and bridge_detect_local_environment is not None:
        result = bridge_detect_local_environment(project_path)
        if result.get("success"):
            result["source"] = "eddz_local"
            return result
        member_b_error = result

    if connection_mode == "ssh" and bridge_detect_remote_environment is not None:
        result = bridge_detect_remote_environment(host, project_path, timeout=20, auth_mode="key")
        if result.get("success"):
            result["source"] = "eddz_ssh"
            return result
        return result

    if connection_mode == "executor":
        return {
            "success": False,
            "error_type": "executor_not_implemented",
            "message": "Executor mode is reserved but not implemented in this backend yet.",
            "connection_mode": connection_mode,
        }

    return {
        "success": True,
        "os": "Linux",
        "architecture": "x86_64",
        "python_version": "3.11.8",
        "node_version": "20.11.0",
        "docker_installed": True,
        "docker_running": True,
        "cuda_version": None,
        "disk_usage": "64%",
        "raw_data": {
            "source": "mock_detection",
            "connection_mode": connection_mode,
            "project_path": project_path,
            "member_b_error": member_b_error,
            "integration_runtime": integration_runtime(),
            "commands": {
                "git": "2.43.0",
                "python": "3.11.8",
                "node": "20.11.0",
            },
        },
    }
