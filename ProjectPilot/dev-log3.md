# Dev Log 3：成员 B 检测能力接入记录

## 当前进度

本阶段完成了成员 B 的 `engine` 文件夹接入验证，并将其中的本地检测能力初步接入到 ProjectPilot 后端。

本次重点不是新增前端接口，而是在保持原有接口不变的前提下，把后端内部的 mock 检测能力替换为“优先调用成员 B 的真实检测函数，失败后回退 mock”的模式。

## 成员 B 提供的内容

成员 B 提供了 `engine` 文件夹，其中包含完整的 Python 包：

```text
engine/engine/projectpilot/
```

其中与当前后端最相关的是：

```python
from projectpilot.integration.member_b import (
    detect_local_environment,
    detect_local_git_status,
)
```

这两个函数分别用于：

```text
detect_local_git_status(project_path)
检测本机指定项目目录的 Git 状态。

detect_local_environment(project_path)
检测本机指定项目目录对应的运行环境。
```

它们返回结构化 `dict`，不直接操作数据库，也不直接调用我们的 FastAPI 接口。数据库保存仍由成员 A 的后端负责。

## 当前接入方式

当前改动集中在：

```text
backend/services/detection_service.py
```

现在后端检测逻辑变成：

```text
1. 优先调用成员 B 的本地检测函数
2. 如果 B 的检测函数成功，返回 source = member_b_local
3. 如果 B 的检测函数失败，回退到原有 mock 数据
4. 接口、数据库表、前端调用方式保持不变
```

这样做的好处是：

```text
前端接口不用改
数据库结构不用改
AI 分析接口不用改
B 的能力可以逐步替换 mock
即使 B 检测失败，系统仍可继续演示
```

## Git 仓库初始化

为了让 B 的 Git 检测函数能够检测当前项目，已将：

```text
/home/huancheng/AutoEnv/ProjectPilot
```

初始化为 Git 仓库，并完成首次提交：

```text
Initial ProjectPilot backend
```

同时新增 `.gitignore`，避免提交敏感或本地生成文件：

```text
.env
backend/.env
backend/projectpilot.db
__pycache__/
*.pyc
```

## seed.py 更新

已更新：

```text
backend/seed.py
```

将 `ProjectPilot + server-a` 的绑定路径从原来的模拟路径：

```text
/opt/projectpilot
```

改为当前本机真实路径：

```text
/home/huancheng/AutoEnv/ProjectPilot
```

运行 `seed.py` 后，当前绑定关系为：

```text
ProjectPilot + server-a -> /home/huancheng/AutoEnv/ProjectPilot
ProjectPilot + server-b -> /srv/projectpilot
DemoApp + server-a -> /opt/demo-app
```

其中 `server-a` 当前用于本地真实检测测试，`server-b` 暂时仍保留为模拟目标服务器。

## 已验证接口

已测试：

```text
POST /projects/1/servers/1/detect
```

结果显示：

```text
git_result.source = member_b_local
environment_result.source = member_b_local
```

说明：

```text
成员 B 的本地 Git 检测函数已被调用
成员 B 的本地环境检测函数已被调用
检测结果已写入 GitStatus 表
检测结果已写入 EnvironmentSnapshot 表
操作过程已写入 OperationLog 表
```

Git 检测结果示例：

```text
branch = main
ahead = 0
behind = 0
has_uncommitted_changes = false
last_commit = Initial ProjectPilot backend
```

环境检测结果示例：

```text
os = Linux
python_version = 3.11.6
node_version = 24.15.0
docker_installed = true
docker_running = false
disk_usage = 3%
```

## AI 分析验证

已测试：

```text
POST /projects/1/ai/analyze-env
```

该接口不是重新检测环境，而是：

```text
读取数据库中最新的 EnvironmentSnapshot
将项目、服务器、环境快照和用户问题发送给 Qwen
返回 AI 环境分析结果
```

测试结果表明，AI 已经能够基于成员 B 检测出的真实本机快照进行分析。

当前链路为：

```text
成员 B 本地检测
↓
成员 A 后端保存 GitStatus / EnvironmentSnapshot
↓
AI analyze-env 读取最新快照
↓
Qwen 生成环境分析
↓
返回给前端
```

## mock 的当前作用

当前 mock 仍然保留。

mock 的作用是：

```text
当 B 的检测函数不可用时兜底
当检测路径不存在时兜底
当某些服务器还没有真实接入时兜底
保证前端和 AI 流程仍能演示
```

例如：

```text
server-b -> /srv/projectpilot
```

当前在本机不存在，因此仍会回退到 mock 或 seed 数据。

这符合当前阶段预期。

## 尚未接入的 B 能力

当前只接入了 B 的本地检测函数。

尚未接入：

```text
projectpilot.executor.remote.check_connection
projectpilot.executor.remote.detect_remote_git_status
projectpilot.executor.remote.detect_remote_environment
projectpilot.executor.remote.run_remote_script
projectpilot.executor.remote.apply_remote_git_operation
```

这些属于远程服务器检测、远程脚本执行、远程 Git 操作能力。

后续如果需要真实远程服务器能力，可以继续在：

```text
backend/services/detection_service.py
backend/services/execution_service.py
```

中逐步替换当前 mock 或模拟执行逻辑。

## 当前阶段结论

成员 A 与成员 B 的第一阶段对接已经完成。

当前已经实现：

```text
B 提供真实检测能力
A 调用 B 的检测函数
A 保存检测结果
A 提供稳定后端接口
A 调用 AI 分析检测结果
前端接口保持不变
```

下一阶段建议：

```text
1. 前端联调 detect 和 analyze-env 接口
2. 根据演示需要接入远程检测能力
3. 优化 AI config-plan 的安全提示词
4. 为执行接口增加命令风险检查
5. 整理最终答辩演示流程
```
