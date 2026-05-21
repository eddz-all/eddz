from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


def check_connection(host: str, timeout: int = 15) -> dict[str, Any]:
    host = normalize_host(host)
    result = run_ssh_command(host, "printf projectpilot-ok", timeout=timeout)
    success = result["exit_code"] == 0 and result["stdout"].strip() == "projectpilot-ok"
    return {
        "success": success,
        "host": host,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "error_type": None if success else "connection_failed",
    }


def detect_remote_git_status(host: str, project_path: str, timeout: int = 20) -> dict[str, Any]:
    host = normalize_host(host)
    project_path = normalize_remote_path(project_path)
    command = " && ".join(
        [
            f"cd {shlex.quote(project_path)}",
            "printf 'branch='",
            "git branch --show-current",
            "printf 'commit='",
            "git rev-parse HEAD",
            "printf 'status_begin\\n'",
            "git status --porcelain=v1 -b",
            "printf 'remotes_begin\\n'",
            "git remote -v",
        ]
    )
    result = run_ssh_command(host, command, timeout=timeout)
    if result["exit_code"] != 0:
        return remote_failure("remote_git_failed", host, project_path, result)

    parsed = parse_remote_git_output(result["stdout"])
    return {
        "success": True,
        "host": host,
        "project_path": project_path,
        "branch": parsed["branch"],
        "commit": parsed["commit"],
        "has_uncommitted_changes": parsed["has_uncommitted_changes"],
        "status_lines": parsed["status_lines"],
        "remotes": parsed["remotes"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
    }


def detect_remote_environment(host: str, project_path: str | None = None, timeout: int = 20) -> dict[str, Any]:
    host = normalize_host(host)
    prefix = ""
    normalized_path = None
    if project_path:
        normalized_path = normalize_remote_path(project_path)
        prefix = f"cd {shlex.quote(normalized_path)} && "

    command = prefix + r"""
printf 'os='; uname -s 2>/dev/null || true
printf 'architecture='; uname -m 2>/dev/null || true
printf 'git_version='; git --version 2>/dev/null | sed 's/^git version //' || true
printf 'python3_version='; python3 --version 2>/dev/null | sed 's/^Python //' || true
printf 'node_version='; node --version 2>/dev/null | sed 's/^v//' || true
if command -v docker >/dev/null 2>&1; then printf 'docker_installed=true\n'; else printf 'docker_installed=false\n'; fi
if docker info >/dev/null 2>&1; then printf 'docker_running=true\n'; else printf 'docker_running=false\n'; fi
""".strip()
    result = run_ssh_command(host, command, timeout=timeout)
    if result["exit_code"] != 0:
        return remote_failure("remote_environment_failed", host, normalized_path, result)

    values = parse_key_value_lines(result["stdout"])
    return {
        "success": True,
        "host": host,
        "project_path": normalized_path,
        "os": values.get("os"),
        "architecture": values.get("architecture"),
        "git_version": values.get("git_version"),
        "python3_version": values.get("python3_version"),
        "node_version": values.get("node_version"),
        "docker_installed": values.get("docker_installed") == "true",
        "docker_running": values.get("docker_running") == "true",
        "raw_data": values,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
    }


def run_ssh_command(host: str, remote_command: str, timeout: int = 20) -> dict[str, Any]:
    if shutil.which("ssh") is None:
        return {"stdout": "", "stderr": "ssh command was not found.", "exit_code": 127}

    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        host,
        remote_command,
    ]
    try:
        process = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + f"\nSSH command timed out after {timeout}s.",
            "exit_code": 124,
        }

    return {
        "stdout": process.stdout,
        "stderr": process.stderr,
        "exit_code": process.returncode,
    }


def list_ssh_hosts(config_path: Path | None = None) -> list[str]:
    path = (config_path or Path.home() / ".ssh" / "config").expanduser()
    if not path.exists():
        return []

    hosts: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or parts[0].lower() != "host":
            continue
        for host in parts[1:]:
            if any(char in host for char in "*?!"):
                continue
            if host.startswith("-"):
                continue
            hosts.add(host)
    return sorted(hosts)


def resolve_ssh_host(host: str, timeout: int = 8) -> dict[str, Any]:
    host = normalize_host(host)
    if shutil.which("ssh") is None:
        return {
            "success": False,
            "host": host,
            "error_type": "command_not_found",
            "message": "ssh command was not found.",
        }

    try:
        process = subprocess.run(
            ["ssh", "-G", host],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "host": host,
            "error_type": "ssh_config_timeout",
            "message": f"ssh -G timed out after {timeout}s.",
        }

    if process.returncode != 0:
        return {
            "success": False,
            "host": host,
            "error_type": "ssh_config_failed",
            "message": process.stderr.strip() or process.stdout.strip(),
            "stderr": process.stderr,
            "stdout": process.stdout,
        }

    data = parse_ssh_g_output(process.stdout)
    return {
        "success": True,
        "host": host,
        "hostname": data.get("hostname"),
        "user": data.get("user"),
        "port": data.get("port"),
        "identityfile": data.get("identityfile", []),
        "proxyjump": data.get("proxyjump"),
        "raw_data": data,
    }


def normalize_host(host: str) -> str:
    value = str(host or "").strip()
    if not value:
        raise ValueError("SSH host is required.")
    if value.startswith("-") or any(char.isspace() for char in value):
        raise ValueError(f"Invalid SSH host: {value}")
    return value


def normalize_remote_path(project_path: str) -> str:
    value = str(project_path or "").strip()
    if not value:
        raise ValueError("project_path is required.")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("project_path contains invalid characters.")
    if not value.startswith("/"):
        raise ValueError("project_path must be an absolute remote path.")
    return value


def parse_remote_git_output(output: str) -> dict[str, Any]:
    lines = output.splitlines()
    branch = None
    commit = None
    status_lines: list[str] = []
    remotes: list[str] = []
    section = None

    for line in lines:
        if line.startswith("branch="):
            branch = line.removeprefix("branch=").strip() or None
            continue
        if line.startswith("commit="):
            commit = line.removeprefix("commit=").strip() or None
            continue
        if line == "status_begin":
            section = "status"
            continue
        if line == "remotes_begin":
            section = "remotes"
            continue
        if section == "status" and line:
            status_lines.append(line)
        elif section == "remotes" and line:
            remotes.append(line)

    return {
        "branch": branch,
        "commit": commit,
        "status_lines": status_lines,
        "remotes": remotes,
        "has_uncommitted_changes": any(not line.startswith("##") for line in status_lines),
    }


def parse_key_value_lines(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_ssh_g_output(output: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line in output.splitlines():
        if not line.strip() or " " not in line:
            continue
        key, value = line.split(None, 1)
        key = key.lower()
        value = value.strip()
        if key == "identityfile":
            data.setdefault(key, []).append(value)
        else:
            data[key] = value
    return data


def remote_failure(
    error_type: str,
    host: str,
    project_path: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": error_type,
        "host": host,
        "project_path": project_path,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "message": result["stderr"].strip() or result["stdout"].strip() or error_type,
    }
