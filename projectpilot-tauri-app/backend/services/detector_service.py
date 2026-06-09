import importlib
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from shlex import quote


MEMBER_B_MODULES = (
    "services.member_b_runner",
    "member_b_runner",
    "member_b",
    "member_b_integration",
)


def _member_b_function(*function_names):
    for module_name in MEMBER_B_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for function_name in function_names:
            function = getattr(module, function_name, None)
            if callable(function):
                return function
    return None


def _run(command, cwd=None, timeout=8):
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
        )
        return {
            "success": completed.returncode == 0,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "exit_code": completed.returncode,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {command[0]}",
            "exit_code": 127,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "exit_code": 124,
        }


def _ssh_target(username: str, host: str):
    return f"{username}@{host}" if username else host


def _remote_command(command: str, cwd: str | None = None):
    if cwd:
        return f"cd {quote(cwd)} && {command}"
    return command


def _find_ssh_executable():
    executable = shutil.which("ssh")
    if executable:
        return executable

    windows_candidates = (
        Path("C:/Windows/System32/OpenSSH/ssh.exe"),
        Path("C:/Windows/Sysnative/OpenSSH/ssh.exe"),
    )
    for candidate in windows_candidates:
        if candidate.exists():
            return str(candidate)

    return None


def run_remote_command(
    host: str,
    port: int,
    username: str,
    command: str,
    cwd: str | None = None,
    timeout: int = 30,
):
    member_b_runner = _member_b_function("run_remote_command", "run_remote_script")
    if member_b_runner is not None:
        try:
            return member_b_runner(
                host=host,
                port=port,
                username=username,
                command=command,
                cwd=cwd,
                timeout=timeout,
            )
        except TypeError:
            return member_b_runner(
                host=host,
                port=port,
                username=username,
                script=command,
                cwd=cwd,
                timeout=timeout,
            )

    ssh_executable = _find_ssh_executable()
    if ssh_executable is None:
        return {
            "success": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": "OpenSSH client was not found on this computer.",
            "error_type": "ssh_client_not_found",
            "message": "OpenSSH client is required for SSH mode.",
        }

    ssh_command = [
        ssh_executable,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-p",
        str(port),
        _ssh_target(username=username, host=host),
        _remote_command(command, cwd=cwd),
    ]

    try:
        completed = subprocess.run(
            ssh_command,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": 124,
            "stdout": "",
            "stderr": "SSH command timed out",
            "error_type": "timeout",
            "message": "SSH command timed out.",
        }

    success = completed.returncode == 0
    return {
        "success": success,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "error_type": None if success else "remote_command_failed",
        "message": "Command executed successfully." if success else "Remote command failed.",
    }


def _version(command):
    result = _run(command)
    if result["success"]:
        return result["stdout"] or result["stderr"]
    return None


def _disk_usage(path):
    try:
        usage = shutil.disk_usage(path)
        percent = round((usage.used / usage.total) * 100)
        return f"{percent}%"
    except OSError:
        return None


def detect_local_git_status(project_path: str):
    path = Path(project_path)
    if not path.exists():
        return {
            "success": False,
            "error_type": "path_not_found",
            "message": "Project path does not exist.",
        }

    inside = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
    if not inside["success"] or inside["stdout"] != "true":
        return {
            "success": True,
            "error_type": "not_git_repository",
            "warning": "not_git_repository",
            "message": "The target path is not a Git repository.",
            "branch": "not-git",
            "remote_url": None,
            "ahead": 0,
            "behind": 0,
            "has_uncommitted_changes": False,
            "last_commit": "not a git repository",
        }

    branch = _run(["git", "branch", "--show-current"], cwd=path)
    remote = _run(["git", "config", "--get", "remote.origin.url"], cwd=path)
    status = _run(["git", "status", "--porcelain"], cwd=path)
    commit = _run(["git", "log", "-1", "--oneline"], cwd=path)
    ahead = 0
    behind = 0
    counts = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=path)
    if counts["success"] and counts["stdout"]:
        parts = counts["stdout"].split()
        if len(parts) >= 2:
            ahead = int(parts[0])
            behind = int(parts[1])

    return {
        "success": True,
        "branch": branch["stdout"] or "unknown",
        "remote_url": remote["stdout"] or None,
        "ahead": ahead,
        "behind": behind,
        "has_uncommitted_changes": bool(status["stdout"]),
        "last_commit": commit["stdout"] or None,
    }


def detect_local_environment(project_path: str | None = None):
    path = project_path or "."
    docker_version = _version(["docker", "--version"])
    docker_ps = _run(["docker", "ps"], timeout=5) if docker_version else None
    cuda_result = _run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], timeout=5)

    raw_data = {
        "commands": {
            "git": _version(["git", "--version"]),
            "python": _version(["python", "--version"]),
            "node": _version(["node", "--version"]),
            "docker": docker_version,
        }
    }

    return {
        "success": True,
        "os": platform.system(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "node_version": _version(["node", "--version"]),
        "docker_installed": docker_version is not None,
        "docker_running": bool(docker_ps and docker_ps["success"]),
        "cuda_version": cuda_result["stdout"].splitlines()[0] if cuda_result["success"] and cuda_result["stdout"] else None,
        "disk_usage": _disk_usage(path),
        "raw_data": raw_data,
    }


def check_server_connection(host: str, port: int, username: str, connection_mode: str = "ssh"):
    if connection_mode == "local":
        return {
            "success": True,
            "connected": True,
            "message": "Local debug target is available without SSH.",
            "latency_ms": 0,
        }
    if connection_mode == "executor":
        return {
            "success": False,
            "connected": False,
            "error_type": "executor_not_ready",
            "message": "Executor mode is reserved and not connected yet.",
        }

    member_b_checker = _member_b_function("check_server_connection")
    if member_b_checker is not None:
        return member_b_checker(host=host, port=port, username=username)

    start = time.perf_counter()
    ssh_check = run_remote_command(
        host=host,
        port=port,
        username=username,
        command="true",
        timeout=12,
    )
    latency_ms = round((time.perf_counter() - start) * 1000)
    if ssh_check.get("success"):
        return {
            "success": True,
            "connected": True,
            "message": "SSH connection successful",
            "latency_ms": latency_ms,
        }

    return {
        "success": False,
        "connected": False,
        "error_type": ssh_check.get("error_type") or "ssh_connection_failed",
        "message": ssh_check.get("stderr") or ssh_check.get("message") or "SSH connection failed",
        "latency_ms": latency_ms,
    }


def detect_remote_git_status(
    host: str,
    port: int,
    username: str,
    project_path: str,
    connection_mode: str = "ssh",
):
    if connection_mode == "local":
        return detect_local_git_status(project_path)
    if connection_mode == "executor":
        return {
            "success": False,
            "error_type": "executor_not_ready",
            "message": "Executor mode is reserved and cannot detect Git yet.",
        }

    member_b_detector = _member_b_function("detect_remote_git_status")
    if member_b_detector is not None:
        return member_b_detector(
            host=host,
            port=port,
            username=username,
            project_path=project_path,
        )

    inside = run_remote_command(
        host=host,
        port=port,
        username=username,
        command="git rev-parse --is-inside-work-tree",
        cwd=project_path,
        timeout=20,
    )
    if not inside.get("success"):
        return {
            "success": False,
            "error_type": inside.get("error_type") or "remote_git_detection_failed",
            "message": inside.get("stderr") or inside.get("message") or "Remote Git detection failed.",
        }
    if inside.get("stdout") != "true":
        return {
            "success": True,
            "error_type": "not_git_repository",
            "warning": "not_git_repository",
            "message": "The target path is not a Git repository.",
            "branch": "not-git",
            "remote_url": None,
            "ahead": 0,
            "behind": 0,
            "has_uncommitted_changes": False,
            "last_commit": "not a git repository",
        }

    branch = run_remote_command(host, port, username, "git branch --show-current", cwd=project_path, timeout=20)
    remote = run_remote_command(host, port, username, "git config --get remote.origin.url", cwd=project_path, timeout=20)
    status = run_remote_command(host, port, username, "git status --porcelain", cwd=project_path, timeout=20)
    commit = run_remote_command(host, port, username, "git log -1 --oneline", cwd=project_path, timeout=20)
    counts = run_remote_command(host, port, username, "git rev-list --left-right --count HEAD...@{u}", cwd=project_path, timeout=20)

    ahead = 0
    behind = 0
    if counts.get("success") and counts.get("stdout"):
        parts = counts["stdout"].split()
        if len(parts) >= 2:
            ahead = int(parts[0])
            behind = int(parts[1])

    return {
        "success": True,
        "branch": branch.get("stdout") or "unknown",
        "remote_url": remote.get("stdout") or None,
        "ahead": ahead,
        "behind": behind,
        "has_uncommitted_changes": bool(status.get("stdout")),
        "last_commit": commit.get("stdout") or None,
        "raw_data": {
            "target": {
                "host": host,
                "port": port,
                "username": username,
                "project_path": project_path,
                "connection_mode": connection_mode,
            },
        },
    }


def detect_remote_environment(
    host: str,
    port: int,
    username: str,
    project_path: str | None = None,
    connection_mode: str = "ssh",
):
    if connection_mode == "local":
        return detect_local_environment(project_path)
    if connection_mode == "executor":
        return {
            "success": False,
            "error_type": "executor_not_ready",
            "message": "Executor mode is reserved and cannot detect environment yet.",
        }

    member_b_detector = _member_b_function("detect_remote_environment")
    if member_b_detector is not None:
        return member_b_detector(
            host=host,
            port=port,
            username=username,
            project_path=project_path,
        )

    def remote_value(command: str, timeout: int = 20):
        result = run_remote_command(
            host=host,
            port=port,
            username=username,
            command=command,
            cwd=project_path,
            timeout=timeout,
        )
        return result.get("stdout") if result.get("success") else None

    os_name = remote_value("uname -s")
    architecture = remote_value("uname -m")
    python_version = remote_value("python3 --version || python --version")
    node_version = remote_value("node --version")
    docker_version = remote_value("docker --version")
    docker_ps = run_remote_command(host, port, username, "docker ps", cwd=project_path, timeout=20) if docker_version else None
    cuda_version = remote_value("nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1")
    disk_usage = remote_value("df -P . | awk 'NR==2 {print $5}'")

    return {
        "success": True,
        "os": os_name,
        "architecture": architecture,
        "python_version": (python_version or "").replace("Python ", "") or None,
        "node_version": node_version,
        "docker_installed": docker_version is not None,
        "docker_running": bool(docker_ps and docker_ps.get("success")),
        "cuda_version": cuda_version,
        "disk_usage": disk_usage,
        "raw_data": {
            "commands": {
                "python": python_version,
                "node": node_version,
                "docker": docker_version,
            },
            "target": {
                "host": host,
                "port": port,
                "username": username,
                "project_path": project_path,
                "connection_mode": connection_mode,
            },
        },
    }


def classify_command_risk(command: str):
    member_b_classifier = _member_b_function("classify_command_risk")
    if member_b_classifier is not None:
        return member_b_classifier(command)

    high = ["rm -rf", "reset --hard", "clean -fd", "push --force", " rebase", "mkfs", "shutdown", "reboot"]
    medium = ["pip install", "npm install", "systemctl", "git pull", "sudo"]
    normalized = command.lower()
    if any(token in normalized for token in high):
        return {
            "risk_level": "high",
            "requires_confirmation": True,
            "allowed": False,
            "reason": "Command may cause destructive or history-changing changes.",
        }
    if any(token in normalized for token in medium):
        return {
            "risk_level": "medium",
            "requires_confirmation": True,
            "allowed": True,
            "reason": "Command changes project or service state.",
        }
    return {
        "risk_level": "low",
        "requires_confirmation": False,
        "allowed": True,
        "reason": "Read-only or low-impact command.",
    }
