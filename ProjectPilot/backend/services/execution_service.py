import re

from services.eddz_bridge import bridge_run_remote_script, integration_runtime


BLOCKED_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bsudo\s+apt\s+remove\b",
    r"\bsudo\s+apt\s+purge\b",
    r"\bcurl\b.*\|\s*(bash|sh)\b",
    r"\bwget\b.*\|\s*(bash|sh)\b",
    r">\s*/etc/",
]

MEDIUM_RISK_PATTERNS = [
    r"\bsudo\b",
    r"\bapt\s+install\b",
    r"\bpip\s+install\b",
    r"\bnpm\s+install\b",
    r"\bsystemctl\s+(start|stop|restart|enable|disable)\b",
    r"\bchmod\b",
    r"\bchown\b",
]

SAFE_READONLY_PREFIXES = (
    "echo ",
    "pwd",
    "whoami",
    "date",
    "uname ",
    "python --version",
    "python3 --version",
    "node --version",
    "npm --version",
    "git status",
    "git branch",
    "git log",
    "git remote",
    "docker --version",
    "docker compose version",
)


def classify_command_safety(command: str | None):
    if command is None or not command.strip():
        return {
            "level": "none",
            "allowed": False,
            "reason": "No command to execute.",
        }

    normalized = " ".join(command.strip().split())
    lowered = normalized.lower()

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            return {
                "level": "blocked",
                "allowed": False,
                "reason": f"Blocked by dangerous pattern: {pattern}",
            }

    if lowered.startswith(SAFE_READONLY_PREFIXES):
        return {
            "level": "low",
            "allowed": True,
            "reason": "Read-only command.",
        }

    for pattern in MEDIUM_RISK_PATTERNS:
        if re.search(pattern, lowered):
            return {
                "level": "medium",
                "allowed": True,
                "reason": f"Requires confirmation because it matches: {pattern}",
            }

    return {
        "level": "medium",
        "allowed": True,
        "reason": "Unknown command type, treat as medium risk.",
    }


def inspect_config_plan_steps(steps):
    return [
        {
            "order": step.order,
            "title": step.title,
            "command": step.command,
            "declared_risk_level": step.risk_level,
            "safety": classify_command_safety(step.command),
        }
        for step in steps
    ]


def simulate_config_plan_execution(steps):
    results = []

    for step in steps:
        safety = classify_command_safety(step.command)
        if safety["level"] == "blocked":
            results.append(
                {
                    "order": step.order,
                    "title": step.title,
                    "command": step.command,
                    "risk_level": step.risk_level,
                    "safety": safety,
                    "status": "blocked",
                    "exit_code": None,
                    "stdout": "",
                    "stderr": safety["reason"],
                }
            )
            continue

        results.append(
            {
                "order": step.order,
                "title": step.title,
                "command": step.command,
                "risk_level": step.risk_level,
                "safety": safety,
                "status": "success",
                "exit_code": 0,
                "stdout": "Simulated command execution.",
                "stderr": "",
            }
        )

    return results


def execute_config_plan_steps(server, project_path: str, steps):
    connection_mode = getattr(server, "connection_mode", "ssh")

    if connection_mode == "local":
        return simulate_config_plan_execution(steps)

    if connection_mode == "executor":
        return [
            build_not_executed_result(
                step,
                "executor_not_implemented",
                "Executor mode is reserved but not implemented in this backend yet.",
            )
            for step in steps
        ]

    if connection_mode != "ssh":
        return [
            build_not_executed_result(
                step,
                "unsupported_connection_mode",
                f"Unsupported connection_mode: {connection_mode}",
            )
            for step in steps
        ]

    if bridge_run_remote_script is None:
        return [
            build_not_executed_result(
                step,
                "eddz_runner_unavailable",
                "eddz run_remote_script is not available.",
            )
            for step in steps
        ]

    return execute_steps_over_ssh(server, project_path, steps)


def execute_steps_over_ssh(server, project_path: str, steps):
    results = []

    for step in steps:
        safety = classify_command_safety(step.command)
        if safety["level"] == "blocked":
            results.append(
                {
                    "order": step.order,
                    "title": step.title,
                    "command": step.command,
                    "risk_level": step.risk_level,
                    "safety": safety,
                    "status": "blocked",
                    "exit_code": None,
                    "stdout": "",
                    "stderr": safety["reason"],
                    "execution_mode": "ssh",
                }
            )
            continue

        if not safety["allowed"]:
            results.append(
                build_not_executed_result(
                    step,
                    "command_not_allowed",
                    safety["reason"],
                    safety=safety,
                    execution_mode="ssh",
                )
            )
            continue

        result = bridge_run_remote_script(
            server.host,
            step.command,
            project_path=project_path,
            interpreter="bash",
            auth_mode="key",
            timeout=60,
        )
        results.append(
            {
                "order": step.order,
                "title": step.title,
                "command": step.command,
                "risk_level": step.risk_level,
                "safety": safety,
                "status": "success" if result.get("success") else "failed",
                "exit_code": result.get("exit_code"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "execution_mode": "ssh",
                "runner_result": result,
                "integration_runtime": integration_runtime(),
            }
        )

    return results


def build_not_executed_result(
    step,
    error_type: str,
    message: str,
    safety: dict | None = None,
    execution_mode: str | None = None,
):
    return {
        "order": step.order,
        "title": step.title,
        "command": step.command,
        "risk_level": step.risk_level,
        "safety": safety or classify_command_safety(step.command),
        "status": "not_executed",
        "exit_code": None,
        "stdout": "",
        "stderr": message,
        "error_type": error_type,
        "execution_mode": execution_mode,
    }
