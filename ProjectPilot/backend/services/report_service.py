from models import EnvironmentSnapshot, GitStatus, Project, ProjectServerMapping, Server
from services.ai_service import build_mock_environment_analysis


def generate_project_report(project: Project, db, include_ai_analysis: bool = True):
    bindings = (
        db.query(ProjectServerMapping, Server)
        .join(Server, ProjectServerMapping.server_id == Server.id)
        .filter(ProjectServerMapping.project_id == project.id)
        .all()
    )

    server_rows = []
    server_snapshots = []
    for binding, server in bindings:
        latest_git_status = (
            db.query(GitStatus)
            .filter(GitStatus.project_id == project.id, GitStatus.server_id == server.id)
            .order_by(GitStatus.id.desc())
            .first()
        )
        latest_environment_snapshot = (
            db.query(EnvironmentSnapshot)
            .filter(
                EnvironmentSnapshot.project_id == project.id,
                EnvironmentSnapshot.server_id == server.id,
            )
            .order_by(EnvironmentSnapshot.id.desc())
            .first()
        )

        server_rows.append(
            {
                "binding": binding,
                "server": server,
                "git_status": latest_git_status,
                "environment_snapshot": latest_environment_snapshot,
            }
        )
        server_snapshots.append(
            {
                "binding_id": binding.id,
                "server": server,
                "server_name": server.name,
                "project_path": binding.project_path,
                "snapshot": latest_environment_snapshot,
            }
        )

    lines = [
        f"# {project.name} 项目状态报告",
        "",
        "## 项目基本信息",
        "",
        f"- 项目 ID：{project.id}",
        f"- 项目名称：{project.name}",
        f"- 项目路径：{project.path}",
        f"- 项目说明：{project.description or '无'}",
        f"- 创建时间：{project.created_at}",
        "",
        "## 绑定服务器",
        "",
    ]

    if not server_rows:
        lines.append("当前项目还没有绑定服务器。")
    else:
        lines.extend(
            [
                "| 服务器 | 地址 | 端口 | 用户名 | 项目路径 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in server_rows:
            server = row["server"]
            binding = row["binding"]
            lines.append(
                f"| {server.name} | {server.host} | {server.port} | "
                f"{server.username} | {binding.project_path} |"
            )

    lines.extend(["", "## 最新 Git 状态", ""])
    if not server_rows:
        lines.append("暂无 Git 状态数据。")
    else:
        lines.extend(
            [
                "| 服务器 | 分支 | ahead | behind | 未提交修改 | 最近提交 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in server_rows:
            server = row["server"]
            git_status = row["git_status"]
            if git_status is None:
                lines.append(f"| {server.name} | 未检测 | - | - | - | - |")
            else:
                lines.append(
                    f"| {server.name} | {git_status.branch} | {git_status.ahead} | "
                    f"{git_status.behind} | {git_status.has_uncommitted_changes} | "
                    f"{git_status.last_commit or '无'} |"
                )

    lines.extend(["", "## 最新环境状态", ""])
    if not server_rows:
        lines.append("暂无环境状态数据。")
    else:
        lines.extend(
            [
                "| 服务器 | OS | 架构 | Python | Node | Docker安装 | Docker运行 | CUDA | 磁盘占用 |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in server_rows:
            server = row["server"]
            snapshot = row["environment_snapshot"]
            if snapshot is None:
                lines.append(f"| {server.name} | 未检测 | - | - | - | - | - | - | - |")
            else:
                lines.append(
                    f"| {server.name} | {snapshot.os or '-'} | "
                    f"{snapshot.architecture or '-'} | {snapshot.python_version or '-'} | "
                    f"{snapshot.node_version or '-'} | {snapshot.docker_installed} | "
                    f"{snapshot.docker_running} | {snapshot.cuda_version or '-'} | "
                    f"{snapshot.disk_usage or '-'} |"
                )

    if include_ai_analysis:
        analysis = build_mock_environment_analysis(server_snapshots)
        lines.extend(["", "## AI 环境分析", ""])
        lines.extend(
            [
                f"- 总结：{analysis['summary']}",
                f"- 风险等级：{analysis['risk_level']}",
                "",
                "### 发现的问题",
                "",
            ]
        )
        lines.extend([f"- {issue}" for issue in analysis["issues"]])
        lines.extend(["", "### 建议操作", ""])
        lines.extend([f"- {suggestion}" for suggestion in analysis["suggestions"]])

    return "\n".join(lines)
