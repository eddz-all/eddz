from services.detector_service import classify_command_risk, run_remote_command


def _execution_message(connection_mode: str, status: str):
    if connection_mode == "ssh":
        if status == "completed":
            return "已通过 SSH 远程执行完成。"
        if status == "blocked":
            return "命令被安全策略拦截，未执行。"
        return "后端已尝试通过 SSH 真实执行，但远程连接或命令执行失败，请查看每一步 stderr。"
    if connection_mode == "executor":
        return "Executor 模式仍是预留能力，命令未执行。"
    return "local 模式为避免误操作本机，只做安全模拟，不会真的执行命令。"


def _format_safety(command: str | None):
    if not command:
        return {
            "level": "low",
            "allowed": True,
            "requires_confirmation": False,
            "reason": "No shell command in this step.",
        }

    safety = classify_command_risk(command)
    return {
        "level": safety["risk_level"],
        "allowed": safety["allowed"],
        "requires_confirmation": safety["requires_confirmation"],
        "reason": safety["reason"],
    }


def simulate_config_plan_execution(
    steps,
    connection_mode: str = "local",
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    cwd: str | None = None,
):
    safety_report = []
    results = []

    for step in steps:
        safety = _format_safety(step.command)
        safety_report.append(
            {
                "order": step.order,
                "title": step.title,
                "command": step.command,
                "declared_risk_level": step.risk_level,
                "safety": safety,
            }
        )

        if not step.command:
            status = "skipped"
            exit_code = None
            stdout = "No command to execute."
            stderr = ""
        elif not safety["allowed"]:
            status = "blocked"
            exit_code = None
            stdout = ""
            stderr = safety["reason"]
        elif connection_mode == "executor":
            status = "not_executed"
            exit_code = None
            stdout = ""
            stderr = "Executor mode is reserved."
        elif connection_mode == "ssh":
            if not host or not port:
                remote_result = {
                    "success": False,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "Missing SSH host or port.",
                }
            else:
                remote_result = run_remote_command(
                    host=host,
                    port=port,
                    username=username or "",
                    command=step.command,
                    cwd=cwd,
                    timeout=60,
                )
            status = "success" if remote_result.get("success") else "failed"
            exit_code = remote_result.get("exit_code")
            stdout = remote_result.get("stdout") or ""
            stderr = remote_result.get("stderr") or remote_result.get("message") or ""
        else:
            status = "simulated"
            exit_code = 0
            stdout = "Simulated command execution."
            stderr = ""

        results.append(
            {
                "order": step.order,
                "title": step.title,
                "command": step.command,
                "risk_level": step.risk_level,
                "safety": safety,
                "status": status,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    if any(result["status"] == "blocked" for result in results):
        status = "blocked"
    elif any(result["status"] == "failed" for result in results):
        status = "failed"
    elif any(result["status"] == "not_executed" for result in results):
        status = "partial"
    elif connection_mode == "ssh":
        status = "completed"
    else:
        status = "completed"

    return {
        "status": status,
        "message": _execution_message(connection_mode, status),
        "safety_report": safety_report,
        "results": results,
    }
