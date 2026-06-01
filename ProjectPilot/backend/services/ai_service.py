import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import get_ai_settings


def extract_json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise ValueError("AI response does not contain a JSON object")

    return json.loads(text[start : end + 1])


def call_openai_compatible_json(system_prompt, user_payload, timeout=30):
    settings = get_ai_settings()
    base_url = settings.base_url.rstrip("/")
    url = f"{base_url}/chat/completions"

    body = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
    }

    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI API returned {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"AI API request failed: {error.reason}") from error

    data = json.loads(response_body)
    content = data["choices"][0]["message"]["content"]
    return extract_json_object(content)


def can_use_real_ai(settings):
    supported_providers = {"deepseek", "qwen", "openai_compatible"}
    return settings.provider.lower() in supported_providers and bool(settings.api_key)


def normalize_environment_analysis(analysis):
    return {
        "summary": str(analysis.get("summary", "AI analysis completed.")),
        "issues": analysis.get("issues", []),
        "suggestions": analysis.get("suggestions", []),
        "risk_level": analysis.get("risk_level", "medium"),
    }


def normalize_config_plan(plan, goal):
    return {
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status", "preview"),
        "summary": str(plan.get("summary", "AI config plan generated.")),
        "goal": plan.get("goal", goal),
        "risk_level": plan.get("risk_level", "medium"),
        "steps": plan.get("steps", []),
    }


def snapshot_to_payload(item):
    snapshot = item["snapshot"]
    if snapshot is None:
        snapshot_payload = None
    else:
        snapshot_payload = {
            "id": snapshot.id,
            "os": snapshot.os,
            "architecture": snapshot.architecture,
            "python_version": snapshot.python_version,
            "node_version": snapshot.node_version,
            "docker_installed": snapshot.docker_installed,
            "docker_running": snapshot.docker_running,
            "cuda_version": snapshot.cuda_version,
            "disk_usage": snapshot.disk_usage,
            "raw_data": snapshot.raw_data,
            "created_at": snapshot.created_at.isoformat()
            if snapshot.created_at is not None
            else None,
        }

    return {
        "binding_id": item["binding_id"],
        "server_id": item["server"].id,
        "server_name": item["server"].name,
        "host": item["server"].host,
        "project_path": item["project_path"],
        "latest_environment_snapshot": snapshot_payload,
    }


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


def analyze_environment(project, question, focus, server_snapshots):
    settings = get_ai_settings()
    if can_use_real_ai(settings):
        system_prompt = (
            "你是一个工程环境分析助手。"
            "请只返回 JSON，不要返回 Markdown。"
            "JSON 字段必须包含 summary 字符串、issues 字符串数组、"
            "suggestions 字符串数组、risk_level 字符串。"
            "risk_level 只能是 low、medium、high。"
        )
        payload = {
            "project": {
                "id": project.id,
                "name": project.name,
                "path": project.path,
                "description": project.description,
            },
            "question": question,
            "focus": focus,
            "server_snapshots": [
                snapshot_to_payload(item) for item in server_snapshots
            ],
        }
        try:
            return normalize_environment_analysis(
                call_openai_compatible_json(system_prompt, payload)
            )
        except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as error:
            fallback = build_mock_environment_analysis(server_snapshots)
            fallback["suggestions"].append(
                f"AI 调用失败，当前返回 mock 分析结果：{error}"
            )
            return fallback

    return build_mock_environment_analysis(server_snapshots)


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


def generate_config_plan(
    project,
    target_server,
    target_snapshot,
    source_server=None,
    source_snapshot=None,
    goal="让目标服务器可以运行该项目",
    allow_command_generation=True,
):
    settings = get_ai_settings()
    if can_use_real_ai(settings):
        system_prompt = (
            "你是一个谨慎的项目环境配置方案生成助手。"
            "请只返回 JSON，不要返回 Markdown。"
            "JSON 字段必须包含 plan_id、status、summary、goal、risk_level、steps。"
            "status 固定为 preview。risk_level 只能是 low、medium、high。"
            "steps 是数组，每项包含 order、title、description、command、risk_level、"
            "requires_confirmation。"
            "不要生成 rm -rf、格式化磁盘、删除数据库等高危破坏命令。"
        )
        payload = {
            "project": {
                "id": project.id,
                "name": project.name,
                "path": project.path,
                "description": project.description,
            },
            "source_server": {
                "id": source_server.id,
                "name": source_server.name,
                "host": source_server.host,
            }
            if source_server is not None
            else None,
            "target_server": {
                "id": target_server.id,
                "name": target_server.name,
                "host": target_server.host,
            },
            "source_snapshot": {
                "os": source_snapshot.os,
                "architecture": source_snapshot.architecture,
                "python_version": source_snapshot.python_version,
                "node_version": source_snapshot.node_version,
                "docker_installed": source_snapshot.docker_installed,
                "docker_running": source_snapshot.docker_running,
                "cuda_version": source_snapshot.cuda_version,
                "disk_usage": source_snapshot.disk_usage,
                "raw_data": source_snapshot.raw_data,
            }
            if source_snapshot is not None
            else None,
            "target_snapshot": {
                "os": target_snapshot.os,
                "architecture": target_snapshot.architecture,
                "python_version": target_snapshot.python_version,
                "node_version": target_snapshot.node_version,
                "docker_installed": target_snapshot.docker_installed,
                "docker_running": target_snapshot.docker_running,
                "cuda_version": target_snapshot.cuda_version,
                "disk_usage": target_snapshot.disk_usage,
                "raw_data": target_snapshot.raw_data,
            }
            if target_snapshot is not None
            else None,
            "goal": goal,
            "allow_command_generation": allow_command_generation,
        }
        try:
            return normalize_config_plan(
                call_openai_compatible_json(system_prompt, payload), goal
            )
        except (RuntimeError, ValueError, KeyError, json.JSONDecodeError):
            pass

    return build_mock_config_plan(
        project=project,
        source_server=source_server,
        target_server=target_server,
        source_snapshot=source_snapshot,
        target_snapshot=target_snapshot,
        goal=goal,
        allow_command_generation=allow_command_generation,
    )
