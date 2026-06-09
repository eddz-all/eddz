def build_mock_environment_analysis(server_snapshots):
    issues = []
    suggestions = []

    python_versions = {
        item["server_name"]: item["snapshot"].python_version
        for item in server_snapshots
        if item["snapshot"] is not None and item["snapshot"].python_version is not None
    }
    if len(set(python_versions.values())) > 1:
        issues.append(f"Python versions are inconsistent: {python_versions}")
        suggestions.append("Confirm the recommended Python version and align server runtimes.")

    node_versions = {
        item["server_name"]: item["snapshot"].node_version
        for item in server_snapshots
        if item["snapshot"] is not None and item["snapshot"].node_version is not None
    }
    if len(set(node_versions.values())) > 1:
        issues.append(f"Node.js versions are inconsistent: {node_versions}")
        suggestions.append("Use the same Node.js major version across deployment servers.")

    stopped_docker_servers = [
        item["server_name"]
        for item in server_snapshots
        if item["snapshot"] is not None and not item["snapshot"].docker_running
    ]
    if stopped_docker_servers:
        issues.append(f"Docker is not running on: {stopped_docker_servers}")
        suggestions.append("Start Docker on servers that need container-based deployment.")

    missing_snapshot_servers = [
        item["server_name"] for item in server_snapshots if item["snapshot"] is None
    ]
    if missing_snapshot_servers:
        issues.append(f"No environment snapshot found for: {missing_snapshot_servers}")
        suggestions.append("Run environment detection on servers without snapshot data.")

    if not issues:
        issues.append("No obvious environment differences were found in summary fields.")
        suggestions.append("Review raw_data for project-specific dependency differences.")

    risk_level = "low"
    if stopped_docker_servers or missing_snapshot_servers:
        risk_level = "medium"
    if len(issues) >= 3:
        risk_level = "high"

    return {
        "summary": "Environment analysis completed based on latest snapshots.",
        "issues": issues,
        "suggestions": suggestions,
        "risk_level": risk_level,
    }


def build_mock_config_plan(
    project,
    target_server,
    target_snapshot,
    source_server=None,
    source_snapshot=None,
    goal="让目标服务器可以运行该项目",
    allow_command_generation=True,
):
    steps = []

    if source_server is not None:
        summary = (
            f"根据 {source_server.name} 的环境状态，为 {target_server.name} "
            f"生成项目 {project.name} 的配置方案。"
        )
    else:
        summary = f"根据目标服务器当前环境，为项目 {project.name} 生成配置方案。"

    if target_snapshot is None:
        steps.append(
            {
                "order": len(steps) + 1,
                "title": "先执行环境检测",
                "description": "目标服务器还没有环境快照，建议先运行环境检测再生成精确配置方案。",
                "command": None,
                "risk_level": "low",
                "requires_confirmation": False,
            }
        )
    else:
        if source_snapshot is not None:
            if source_snapshot.python_version != target_snapshot.python_version:
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "title": "对齐 Python 版本",
                        "description": (
                            f"源服务器 Python 为 {source_snapshot.python_version}，"
                            f"目标服务器 Python 为 {target_snapshot.python_version}。"
                        ),
                        "command": (
                            "sudo apt install python3 python3-venv"
                            if allow_command_generation
                            else None
                        ),
                        "risk_level": "medium",
                        "requires_confirmation": True,
                    }
                )

            if source_snapshot.node_version != target_snapshot.node_version:
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "title": "对齐 Node.js 版本",
                        "description": (
                            f"源服务器 Node.js 为 {source_snapshot.node_version}，"
                            f"目标服务器 Node.js 为 {target_snapshot.node_version}。"
                        ),
                        "command": (
                            "node --version"
                            if allow_command_generation
                            else None
                        ),
                        "risk_level": "low",
                        "requires_confirmation": True,
                    }
                )

        if target_snapshot.docker_installed and not target_snapshot.docker_running:
            steps.append(
                {
                    "order": len(steps) + 1,
                    "title": "启动 Docker 服务",
                    "description": "目标服务器已安装 Docker，但 Docker 当前未运行。",
                    "command": (
                        "sudo systemctl start docker"
                        if allow_command_generation
                        else None
                    ),
                    "risk_level": "low",
                    "requires_confirmation": True,
                }
            )

        if not target_snapshot.docker_installed:
            steps.append(
                {
                    "order": len(steps) + 1,
                    "title": "安装 Docker",
                    "description": "目标服务器未检测到 Docker，如项目依赖容器部署，需要先安装 Docker。",
                    "command": (
                        "sudo apt install docker.io"
                        if allow_command_generation
                        else None
                    ),
                    "risk_level": "medium",
                    "requires_confirmation": True,
                }
            )

    if not steps:
        steps.append(
            {
                "order": 1,
                "title": "检查项目依赖",
                "description": "摘要环境未发现明显差异，建议继续检查 raw_data 中的项目依赖版本。",
                "command": None,
                "risk_level": "low",
                "requires_confirmation": False,
            }
        )

    risk_order = {"low": 1, "medium": 2, "high": 3}
    risk_level = max(steps, key=lambda step: risk_order[step["risk_level"]])["risk_level"]

    return {
        "plan_id": None,
        "status": "preview",
        "summary": summary,
        "goal": goal,
        "risk_level": risk_level,
        "steps": steps,
    }
