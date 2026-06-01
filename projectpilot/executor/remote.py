from __future__ import annotations

import shlex
import shutil
import subprocess
import time
import hashlib
from pathlib import Path
from typing import Any

from projectpilot.git.parser import parse_branch_status, parse_remotes, parse_status_entries


def check_connection(host: str, timeout: int = 15, auth_mode: str = "key") -> dict[str, Any]:
    host = normalize_host(host)
    started = time.perf_counter()
    result = run_ssh_command(host, "echo projectpilot-ok", timeout=timeout, auth_mode=auth_mode)
    latency_ms = int((time.perf_counter() - started) * 1000)
    success = result["exit_code"] == 0 and result["stdout"].strip() == "projectpilot-ok"
    return {
        "success": success,
        "connected": success,
        "ssh_host": host,
        "host": host,
        "ssh_auth_mode": normalize_ssh_auth_mode(auth_mode),
        "latency_ms": latency_ms,
        "message": "Connection successful" if success else result["stderr"].strip() or result["stdout"].strip(),
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "error_type": None if success else "ssh_connection_failed",
    }


def detect_remote_git_status(host: str, project_path: str, timeout: int = 20, auth_mode: str = "key") -> dict[str, Any]:
    host = normalize_host(host)
    project_path = normalize_remote_path(project_path)
    command = " && ".join(
        [
            f"cd {shlex.quote(project_path)}",
            "printf 'status_begin\\n'",
            "git status --porcelain=v2 --branch --untracked-files=all",
            "printf 'status_end\\n'",
            "printf 'remotes_begin\\n'",
            "git remote -v",
            "printf 'remotes_end\\n'",
            "printf 'last_commit='",
            f"git log -1 --pretty={shlex.quote('%h %s')}",
        ]
    )
    result = run_ssh_command(host, command, timeout=timeout, auth_mode=auth_mode)
    if result["exit_code"] != 0:
        return remote_failure("remote_git_failed", host, project_path, result)

    parsed = parse_remote_git_output(result["stdout"])
    return {
        "success": True,
        "ssh_host": host,
        "host": host,
        "ssh_auth_mode": normalize_ssh_auth_mode(auth_mode),
        "project_path": project_path,
        "branch": parsed["branch"],
        "upstream": parsed["upstream"],
        "remote_url": parsed["remote_url"],
        "ahead": parsed["ahead"],
        "behind": parsed["behind"],
        "commit": parsed["commit"],
        "is_clean": parsed["is_clean"],
        "has_uncommitted_changes": parsed["has_uncommitted_changes"],
        "state": parsed["state"],
        "staged_count": parsed["staged_count"],
        "unstaged_count": parsed["unstaged_count"],
        "untracked_count": parsed["untracked_count"],
        "conflicted_count": parsed["conflicted_count"],
        "last_commit": parsed["last_commit"],
        "status_lines": parsed["status_lines"],
        "remotes": parsed["remotes"],
        "remote_lines": parsed["remote_lines"],
        "raw_data": parsed["raw_data"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
    }


def detect_remote_environment(
    host: str,
    project_path: str | None = None,
    timeout: int = 20,
    auth_mode: str = "key",
) -> dict[str, Any]:
    host = normalize_host(host)
    normalized_path = None
    path_check = "printf 'project_path_exists=unknown\\n'"
    disk_target = "/"
    if project_path:
        normalized_path = normalize_remote_path(project_path)
        quoted_path = shlex.quote(normalized_path)
        path_check = (
            f"if test -d {quoted_path}; "
            "then printf 'project_path_exists=true\\n'; "
            "else printf 'project_path_exists=false\\n'; fi"
        )
        disk_target = normalized_path

    command = r"""
printf 'os='; uname -s 2>/dev/null || true
printf 'architecture='; uname -m 2>/dev/null || true
printf 'git_version='; git --version 2>/dev/null | sed 's/^git version //' || true
printf 'python3_version='; python3 --version 2>/dev/null | sed 's/^Python //' || true
printf 'node_version='; node --version 2>/dev/null | sed 's/^v//' || true
printf 'npm_version='; npm --version 2>/dev/null || true
if command -v docker >/dev/null 2>&1; then printf 'docker_installed=true\n'; else printf 'docker_installed=false\n'; fi
printf 'docker_version='; docker --version 2>/dev/null | sed 's/^Docker version //' || true
if docker info >/dev/null 2>&1; then printf 'docker_running=true\n'; else printf 'docker_running=false\n'; fi
printf 'docker_compose_version='; docker compose version --short 2>/dev/null || true
printf 'cuda_version='; nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1 || true
""".strip()
    command = " && ".join(
        [
            command,
            path_check,
            f"printf 'disk_usage='; df -P {shlex.quote(disk_target)} 2>/dev/null | awk 'NR==2 {{print $5}}' || true",
        ]
    )
    result = run_ssh_command(host, command, timeout=timeout, auth_mode=auth_mode)
    if result["exit_code"] != 0:
        return remote_failure("remote_environment_failed", host, normalized_path, result)

    values = parse_key_value_lines(result["stdout"])
    return {
        "success": True,
        "ssh_host": host,
        "host": host,
        "ssh_auth_mode": normalize_ssh_auth_mode(auth_mode),
        "project_path": normalized_path,
        "os": values.get("os"),
        "architecture": values.get("architecture"),
        "git_version": values.get("git_version"),
        "python3_version": values.get("python3_version"),
        "python_version": values.get("python3_version"),
        "node_version": values.get("node_version"),
        "npm_version": values.get("npm_version"),
        "docker_installed": values.get("docker_installed") == "true",
        "docker_running": values.get("docker_running") == "true",
        "docker_version": values.get("docker_version"),
        "docker_compose_version": values.get("docker_compose_version"),
        "cuda_version": values.get("cuda_version") or None,
        "disk_usage": values.get("disk_usage"),
        "project_path_exists": parse_bool(values.get("project_path_exists")),
        "raw_data": values,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
    }


def apply_remote_git_operation(
    host: str,
    project_path: str,
    operation: str,
    params: dict[str, Any] | None = None,
    expected_command: list[str] | None = None,
    timeout: int = 30,
    auth_mode: str = "key",
) -> dict[str, Any]:
    host = normalize_host(host)
    project_path = normalize_remote_path(project_path)
    params = params or {}
    if not isinstance(params, dict):
        return {
            "success": False,
            "error_type": "invalid_git_operation",
            "host": host,
            "project_path": project_path,
            "message": "Git operation params must be an object.",
        }
    try:
        command_args = build_remote_git_command(operation, params)
    except ValueError as exc:
        return {
            "success": False,
            "error_type": "invalid_git_operation",
            "host": host,
            "project_path": project_path,
            "message": str(exc),
        }

    if expected_command is not None and expected_command != command_args:
        return {
            "success": False,
            "error_type": "command_mismatch",
            "host": host,
            "project_path": project_path,
            "message": "Approved command does not match the command generated by the executor.",
            "expected_command": expected_command,
            "generated_command": command_args,
        }

    before = detect_remote_git_status(host, project_path, timeout=timeout, auth_mode=auth_mode)
    if not before.get("success"):
        return {
            "success": False,
            "error_type": "remote_preflight_failed",
            "host": host,
            "project_path": project_path,
            "message": "Could not inspect remote repository before execution.",
            "before": before,
        }

    blockers = remote_git_operation_blockers(normalize_git_operation(operation), before)
    if blockers:
        return {
            "success": False,
            "error_type": "remote_git_operation_blocked",
            "host": host,
            "project_path": project_path,
            "operation": normalize_git_operation(operation),
            "command": command_args,
            "message": "; ".join(blockers),
            "blockers": blockers,
            "before": before,
        }

    remote_command = f"cd {shlex.quote(project_path)} && {shlex.join(command_args)}"
    result = run_ssh_command(host, remote_command, timeout=timeout, auth_mode=auth_mode)
    after = detect_remote_git_status(host, project_path, timeout=timeout, auth_mode=auth_mode)
    success = result["exit_code"] == 0 and bool(after.get("success"))
    return {
        "success": success,
        "error_type": None if success else remote_git_operation_error_type(result, after),
        "host": host,
        "ssh_auth_mode": normalize_ssh_auth_mode(auth_mode),
        "project_path": project_path,
        "operation": normalize_git_operation(operation),
        "command": command_args,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "before": before,
        "after": after,
    }


def run_remote_script(
    host: str,
    script: str,
    *,
    project_path: str | None = None,
    interpreter: str = "bash",
    args: list[str] | None = None,
    env: dict[str, Any] | None = None,
    expected_sha256: str | None = None,
    auth_mode: str = "key",
    timeout: int = 60,
) -> dict[str, Any]:
    host = normalize_host(host)
    normalized_path = normalize_remote_path(project_path) if project_path else None
    normalized_script = normalize_script(script)
    script_sha256 = sha256_text(normalized_script)
    if expected_sha256 and expected_sha256 != script_sha256:
        return {
            "success": False,
            "error_type": "script_hash_mismatch",
            "ssh_host": host,
            "host": host,
            "project_path": normalized_path,
            "message": "Approved script hash does not match the script payload.",
            "expected_sha256": expected_sha256,
            "script_sha256": script_sha256,
        }

    command = build_remote_script_command(
        interpreter=interpreter,
        project_path=normalized_path,
        args=args or [],
        env=env or {},
    )
    result = run_ssh_command(host, command, timeout=timeout, stdin_data=normalized_script, auth_mode=auth_mode)
    success = result["exit_code"] == 0
    return {
        "success": success,
        "error_type": None if success else "remote_script_failed",
        "ssh_host": host,
        "host": host,
        "ssh_auth_mode": normalize_ssh_auth_mode(auth_mode),
        "project_path": normalized_path,
        "interpreter": normalize_interpreter(interpreter),
        "command": command,
        "script_sha256": script_sha256,
        "script_size": len(normalized_script.encode("utf-8")),
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "message": "Script executed successfully" if success else result["stderr"].strip() or "Remote script failed.",
    }


def remote_git_operation_error_type(result: dict[str, Any], after: dict[str, Any]) -> str:
    if result["exit_code"] != 0:
        return "remote_git_operation_failed"
    if not after.get("success"):
        return "remote_postflight_failed"
    return "remote_git_operation_failed"


def remote_git_operation_blockers(operation: str, before: dict[str, Any]) -> list[str]:
    state = str(before.get("state") or "")
    is_clean = bool(before.get("is_clean", False))
    ahead = int(before.get("ahead") or 0)
    behind = int(before.get("behind") or 0)
    upstream = before.get("upstream")

    if operation == "fetch":
        return []

    if operation == "pull":
        blockers: list[str] = []
        if not upstream:
            blockers.append("pull requires an upstream branch")
        if not is_clean:
            blockers.append("pull requires a clean working tree")
        if state in {"conflict", "diverged", "no_upstream"}:
            blockers.append(f"pull is blocked while repository state is {state}")
        if ahead != 0:
            blockers.append("pull is blocked because the branch is ahead of upstream")
        if behind <= 0:
            blockers.append("pull requires the branch to be behind upstream")
        return blockers

    if operation == "push":
        blockers = []
        if not upstream:
            blockers.append("push requires an upstream branch")
        if not is_clean:
            blockers.append("push requires a clean working tree")
        if state in {"conflict", "diverged", "no_upstream"}:
            blockers.append(f"push is blocked while repository state is {state}")
        if ahead <= 0:
            blockers.append("push requires the branch to be ahead of upstream")
        if behind != 0:
            blockers.append("push is blocked because the branch is behind upstream")
        return blockers

    return []


def build_remote_git_command(operation: str, params: dict[str, Any]) -> list[str]:
    normalized = normalize_git_operation(operation)
    if normalized == "fetch":
        command = ["git", "fetch"]
        if bool(params.get("prune", False)):
            command.append("--prune")
        remote = optional_git_value(params.get("remote"))
        if remote:
            command.append(remote)
        return command
    if normalized == "add":
        paths = remote_string_list(params.get("paths") or params.get("include_paths") or params.get("include"))
        if not paths:
            raise ValueError("add requires paths.")
        return ["git", "add", "--", *paths]
    if normalized == "commit":
        return ["git", "commit", "-m", required_message(params, "message")]
    if normalized == "pull":
        return ["git", "pull", "--ff-only"]
    if normalized == "push":
        return ["git", "push"]
    if normalized == "switch":
        target = required_git_value(params, "target")
        command = ["git", "switch"]
        if bool(params.get("create", False)):
            command.extend(["-c", target])
            start_point = optional_git_value(params.get("start_point"))
            if start_point:
                command.append(start_point)
        else:
            command.append(target)
        return command
    if normalized == "merge":
        return ["git", "merge", "--ff-only", required_git_value(params, "source")]
    if normalized == "stash":
        command = ["git", "stash", "push"]
        if bool(params.get("include_untracked", False)):
            command.append("--include-untracked")
        message = optional_message(params.get("message")) or "ProjectPilot stash"
        command.extend(["-m", message])
        return command
    if normalized == "tag":
        name = required_git_value(params, "name")
        message = optional_message(params.get("message"))
        if message:
            return ["git", "tag", "-a", name, "-m", message]
        return ["git", "tag", name]
    if normalized == "revert":
        command = ["git", "revert"]
        command.append("--no-edit" if bool(params.get("commit", False)) else "--no-commit")
        command.append(required_git_value(params, "revision"))
        return command
    if normalized == "cherry-pick":
        command = ["git", "cherry-pick"]
        if not bool(params.get("commit", False)):
            command.append("--no-commit")
        command.append(required_git_value(params, "revision"))
        return command
    raise ValueError(f"Unsupported remote Git operation: {normalized}")


def run_ssh_command(
    host: str,
    remote_command: str,
    timeout: int = 20,
    stdin_data: str | None = None,
    auth_mode: str = "key",
) -> dict[str, Any]:
    if shutil.which("ssh") is None:
        return {"stdout": "", "stderr": "ssh command was not found.", "exit_code": 127}

    normalized_auth_mode = normalize_ssh_auth_mode(auth_mode)
    args = [
        "ssh",
        "-o",
        "ConnectTimeout=8",
        "-o",
        f"BatchMode={'no' if normalized_auth_mode == 'password' else 'yes'}",
    ]
    if normalized_auth_mode == "password":
        args.extend(["-o", "NumberOfPasswordPrompts=3"])
    args.extend([host, remote_command])
    try:
        process = subprocess.run(
            args,
            input=stdin_data,
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
        "ssh_auth_mode": normalized_auth_mode,
    }


def normalize_ssh_auth_mode(auth_mode: str | None) -> str:
    value = str(auth_mode or "key").strip().lower()
    if value in {"key", "agent", "key-only", "key_only", "publickey"}:
        return "key"
    if value in {"password", "interactive", "keyboard-interactive", "keyboard_interactive"}:
        return "password"
    raise ValueError(f"Unsupported ssh_auth_mode: {auth_mode}")


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


def normalize_git_operation(operation: str) -> str:
    value = str(operation or "").strip().replace("_", "-")
    if not value:
        raise ValueError("operation is required.")
    return value


def required_git_value(params: dict[str, Any], key: str) -> str:
    value = optional_git_value(params.get(key))
    if not value:
        raise ValueError(f"{key} is required.")
    return value


def optional_git_value(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if cleaned.startswith("-") or "\x00" in cleaned or "\n" in cleaned or "\r" in cleaned:
        raise ValueError(f"Invalid Git argument: {cleaned}")
    return cleaned


def required_message(params: dict[str, Any], key: str) -> str:
    value = optional_message(params.get(key))
    if not value:
        raise ValueError(f"{key} is required.")
    return value


def optional_message(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if "\x00" in cleaned or "\n" in cleaned or "\r" in cleaned:
        raise ValueError("Git message contains invalid characters.")
    return cleaned


def remote_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        raise ValueError("Expected a string array.")
    cleaned: list[str] = []
    for item in items:
        path = str(item).strip()
        if not path or "\x00" in path or "\n" in path or "\r" in path:
            raise ValueError("Invalid path argument.")
        cleaned.append(path)
    return cleaned


def normalize_script(script: str) -> str:
    value = str(script or "")
    if not value.strip():
        raise ValueError("script is required.")
    if "\x00" in value:
        raise ValueError("script contains invalid characters.")
    if not value.endswith("\n"):
        value += "\n"
    return value


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_interpreter(interpreter: str) -> str:
    value = str(interpreter or "bash").strip()
    allowed = {"bash", "sh"}
    if value not in allowed:
        raise ValueError(f"Unsupported script interpreter: {value}")
    return value


def normalize_script_args(args: Any) -> list[str]:
    if args is None:
        return []
    if not isinstance(args, list):
        raise ValueError("script args must be a string array.")
    cleaned: list[str] = []
    for item in args:
        value = str(item)
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError("script args contain invalid characters.")
        cleaned.append(value)
    return cleaned


def normalize_script_env(env: Any) -> dict[str, str]:
    if env is None:
        return {}
    if not isinstance(env, dict):
        raise ValueError("script env must be an object.")
    cleaned: dict[str, str] = {}
    for key, value in env.items():
        env_key = str(key)
        if not env_key.replace("_", "A").isalnum() or not env_key or env_key[0].isdigit():
            raise ValueError(f"Invalid environment variable name: {env_key}")
        env_value = str(value)
        if "\x00" in env_value:
            raise ValueError(f"Invalid environment variable value for {env_key}.")
        cleaned[env_key] = env_value
    return cleaned


def build_remote_script_command(
    *,
    interpreter: str,
    project_path: str | None,
    args: list[str],
    env: dict[str, Any],
) -> str:
    shell = normalize_interpreter(interpreter)
    script_args = normalize_script_args(args)
    script_env = normalize_script_env(env)
    env_prefix = ""
    if script_env:
        env_prefix = "env " + " ".join(f"{key}={shlex.quote(value)}" for key, value in script_env.items()) + " "
    command = f"{env_prefix}{shlex.quote(shell)} -s --"
    if script_args:
        command += " " + " ".join(shlex.quote(item) for item in script_args)
    if project_path:
        command = f"cd {shlex.quote(project_path)} && {command}"
    return command


def parse_remote_git_output(output: str) -> dict[str, Any]:
    lines = output.splitlines()
    fallback_branch = None
    fallback_commit = None
    last_commit = None
    status_lines: list[str] = []
    remote_lines: list[str] = []
    section = None

    for line in lines:
        if line.startswith("branch="):
            fallback_branch = line.removeprefix("branch=").strip() or None
            continue
        if line.startswith("commit="):
            fallback_commit = line.removeprefix("commit=").strip() or None
            continue
        if line.startswith("last_commit="):
            last_commit = line.removeprefix("last_commit=").strip() or None
            continue
        if line == "status_begin":
            section = "status"
            continue
        if line == "status_end":
            section = None
            continue
        if line == "remotes_begin":
            section = "remotes"
            continue
        if line == "remotes_end":
            section = None
            continue
        if section == "status" and line:
            status_lines.append(line)
        elif section == "remotes" and line:
            remote_lines.append(line)

    status_text = "\n".join(status_lines)
    branch_data = parse_branch_status(status_text)
    changed_files, untracked_files, conflicted_files = parse_status_entries(status_text)
    staged_files = [item.path for item in changed_files if item.is_staged]
    unstaged_files = [item.path for item in changed_files if item.is_unstaged]
    remotes = parse_remotes("\n".join(remote_lines))
    branch = branch_data["head"] if isinstance(branch_data["head"], str) else fallback_branch
    upstream = branch_data["upstream"] if isinstance(branch_data["upstream"], str) else None
    ahead = int(branch_data["ahead"] or 0)
    behind = int(branch_data["behind"] or 0)
    is_clean = not staged_files and not unstaged_files and not untracked_files and not conflicted_files
    state = classify_git_state(
        is_clean=is_clean,
        ahead=ahead,
        behind=behind,
        upstream=upstream,
        conflicted_count=len(conflicted_files),
    )
    return {
        "branch": branch,
        "upstream": upstream,
        "remote_url": select_remote_url(upstream, remotes),
        "ahead": ahead,
        "behind": behind,
        "commit": branch_data["commit"] if isinstance(branch_data["commit"], str) else fallback_commit,
        "is_clean": is_clean,
        "state": state,
        "staged_count": len(staged_files),
        "unstaged_count": len(unstaged_files),
        "untracked_count": len(untracked_files),
        "conflicted_count": len(conflicted_files),
        "last_commit": last_commit,
        "status_lines": status_lines,
        "remotes": remotes,
        "remote_lines": remote_lines,
        "has_uncommitted_changes": not is_clean,
        "raw_data": {
            "status": status_lines,
            "remotes": remote_lines,
        },
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


def parse_bool(value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def classify_git_state(
    *,
    is_clean: bool,
    ahead: int,
    behind: int,
    upstream: str | None,
    conflicted_count: int,
) -> str:
    if conflicted_count > 0:
        return "conflict"
    if not upstream:
        return "no_upstream"
    if ahead > 0 and behind > 0:
        return "diverged"
    if not is_clean:
        return "dirty"
    if behind > 0:
        return "behind"
    if ahead > 0:
        return "ahead"
    return "clean"


def select_remote_url(upstream: str | None, remotes: dict[str, list[str]]) -> str | None:
    candidates: list[str] = []
    if upstream and "/" in upstream:
        candidates.append(upstream.split("/", 1)[0])
    candidates.append("origin")
    candidates.extend(remote for remote in remotes if remote not in candidates)

    for remote in candidates:
        urls = remotes.get(remote, [])
        if urls:
            return urls[0]
    return None


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
