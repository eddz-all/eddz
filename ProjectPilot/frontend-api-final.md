# ProjectPilot 前端接口设计文档（最终效果版）

本文档描述 ProjectPilot 最终希望提供给前端的主要接口形态。

说明：

- 当前文档以当前已实现接口为主，并保留少量后续扩展说明。
- 前端主要通过这些接口完成项目管理、服务器管理、检测、AI 分析、AI 配置计划、人工审核执行、报告展示和操作日志查看。
- 后端负责数据存储、状态聚合、AI 调用、报告生成和执行流程控制。
- 成员 B 的检测和执行能力最终会由后端在相关接口内部调用。

如果后端通过 Cloudflare Tunnel 暴露，例如：

```text
https://xxxx.trycloudflare.com
```

则前端 API Base URL 使用：

```text
https://xxxx.trycloudflare.com
```

直接访问根路径：

```http
GET /
```

会返回：

```json
{
  "message": "ProjectPilot backend is running"
}
```

接口文档页面访问：

```text
https://xxxx.trycloudflare.com/docs
```

## 一、基础接口

### 1. 健康检查

```http
GET /health
```

用途：

检查后端服务是否正常运行。

响应示例：

```json
{
  "status": "ok"
}
```

## 二、项目管理接口

### 1. 创建项目

```http
POST /projects
```

请求体：

```json
{
  "name": "ProjectPilot",
  "path": "/home/user/ProjectPilot",
  "description": "AI 项目环境管理平台"
}
```

响应示例：

```json
{
  "id": 1,
  "name": "ProjectPilot",
  "path": "/home/user/ProjectPilot",
  "description": "AI 项目环境管理平台",
  "created_at": "2026-05-18T10:00:00"
}
```

### 2. 获取项目列表

```http
GET /projects
```

响应示例：

```json
[
  {
    "id": 1,
    "name": "ProjectPilot",
    "path": "/home/user/ProjectPilot",
    "description": "AI 项目环境管理平台",
    "created_at": "2026-05-18T10:00:00"
  }
]
```

### 3. 获取项目详情

```http
GET /projects/{project_id}
```

响应示例：

```json
{
  "id": 1,
  "name": "ProjectPilot",
  "path": "/home/user/ProjectPilot",
  "description": "AI 项目环境管理平台",
  "created_at": "2026-05-18T10:00:00"
}
```

### 4. 删除项目

```http
DELETE /projects/{project_id}
```

响应示例：

```json
{
  "message": "Project deleted successfully"
}
```

## 三、服务器管理接口

### 1. 创建服务器

```http
POST /servers
```

请求体：

```json
{
  "name": "server-a",
  "host": "127.0.0.1",
  "port": 22,
  "username": "ubuntu",
  "connection_mode": "local",
  "description": "测试服务器 A"
}
```

响应示例：

```json
{
  "id": 1,
  "name": "server-a",
  "host": "192.168.1.100",
  "port": 22,
  "username": "ubuntu",
  "connection_mode": "local",
  "description": "测试服务器 A",
  "created_at": "2026-05-18T10:00:00"
}
```

connection_mode 当前支持：

```text
local
本机检测/模拟执行，用于开发测试。

executor
Agent / Executor 模式。后端会创建异步任务，由目标机器上的 executor 主动轮询并执行。
```

### 2. 获取服务器列表

```http
GET /servers
```

响应示例：

```json
[
  {
    "id": 1,
    "name": "server-a",
    "host": "192.168.1.100",
    "port": 22,
    "username": "ubuntu",
    "connection_mode": "local",
    "description": "测试服务器 A",
    "created_at": "2026-05-18T10:00:00"
  }
]
```

### 3. 获取服务器详情

```http
GET /servers/{server_id}
```

响应示例：

```json
{
  "id": 1,
  "name": "server-a",
  "host": "192.168.1.100",
  "port": 22,
  "username": "ubuntu",
  "connection_mode": "local",
  "description": "测试服务器 A",
  "created_at": "2026-05-18T10:00:00"
}
```

### 4. 删除服务器

```http
DELETE /servers/{server_id}
```

响应示例：

```json
{
  "message": "Server deleted successfully"
}
```

## 四、项目与服务器绑定接口

### 1. 绑定项目和服务器

```http
POST /projects/{project_id}/bind-server
```

请求体：

```json
{
  "server_id": 1,
  "project_path": "/opt/projectpilot"
}
```

响应示例：

```json
{
  "id": 1,
  "project_id": 1,
  "server_id": 1,
  "project_path": "/opt/projectpilot",
  "created_at": "2026-05-18T10:00:00"
}
```

### 2. 获取某个项目绑定的服务器

```http
GET /projects/{project_id}/servers
```

响应示例：

```json
[
  {
    "binding_id": 1,
    "project_id": 1,
    "server_id": 1,
    "server_name": "server-a",
    "host": "192.168.1.100",
    "port": 22,
    "username": "ubuntu",
    "project_path": "/opt/projectpilot",
    "created_at": "2026-05-18T10:00:00"
  }
]
```

### 3. 获取某台服务器绑定的项目

```http
GET /servers/{server_id}/projects
```

响应示例：

```json
[
  {
    "binding_id": 1,
    "server_id": 1,
    "project_id": 1,
    "project_name": "ProjectPilot",
    "project_path": "/opt/projectpilot",
    "created_at": "2026-05-18T10:00:00"
  }
]
```

### 4. 解除项目和服务器绑定

```http
DELETE /projects/{project_id}/servers/{server_id}
```

响应示例：

```json
{
  "message": "Project-server binding deleted successfully"
}
```

## 五、检测触发接口

检测触发接口是最终版本中前端最常用的操作接口之一。

前端点击“检测”后，不应该手动提交 GitStatus 或 EnvironmentSnapshot，而是调用检测接口。后端内部会调用成员 B 的检测函数。

### 1. 检测某项目在某服务器上的状态

```http
POST /projects/{project_id}/servers/{server_id}/detect
```

用途：

检测某个项目在某台服务器上的 Git 状态和环境状态。

请求体：无。

说明：

后端会根据服务器的 `connection_mode` 选择检测方式。

```text
local -> 调用成员 B 的本地检测函数
executor -> 创建 detect_git / detect_environment 异步任务，等待 executor 拉取
```

`local` 模式响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "server_id": 1,
  "server_name": "server-a",
  "project_path": "/home/huancheng/AutoEnv/ProjectPilot",
  "connection_mode": "local",
  "status": "completed",
  "git_status": {
    "id": 10,
    "branch": "main",
    "remote_url": "git@example.com:team/projectpilot.git",
    "ahead": 1,
    "behind": 0,
    "has_uncommitted_changes": true,
    "last_commit": "abc123 update backend",
    "created_at": "2026-05-18T10:10:00"
  },
  "environment_snapshot": {
    "id": 8,
    "os": "Linux",
    "architecture": "x86_64",
    "python_version": "3.11.8",
    "node_version": "20.11.0",
    "docker_installed": true,
    "docker_running": true,
    "cuda_version": "12.1",
    "disk_usage": "68%",
    "raw_data": {
      "python_packages": {
        "numpy": "1.26.4"
      }
    },
    "created_at": "2026-05-18T10:10:00"
  }
}
```

`executor` 模式响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "server_id": 1,
  "server_name": "server-a",
  "project_path": "/home/huancheng/AutoEnv/ProjectPilot",
  "connection_mode": "executor",
  "status": "queued",
  "message": "Executor tasks created and waiting for agent polling.",
  "tasks": [
    {
      "id": "task_xxx",
      "project_id": 1,
      "server_id": 1,
      "task_type": "detect_git",
      "status": "queued",
      "payload": {
        "project_path": "/home/huancheng/AutoEnv/ProjectPilot",
        "connection_mode": "executor",
        "risk_level": "low"
      },
      "result": null,
      "executor_id": "server-a"
    },
    {
      "id": "task_yyy",
      "project_id": 1,
      "server_id": 1,
      "task_type": "detect_environment",
      "status": "queued",
      "payload": {
        "project_path": "/home/huancheng/AutoEnv/ProjectPilot",
        "connection_mode": "executor",
        "risk_level": "low"
      },
      "result": null,
      "executor_id": "server-a"
    }
  ]
}
```

前端处理建议：

- `status = completed`：表示同步完成，可直接展示结果
- `status = queued`：表示已创建 executor 任务，需要轮询任务状态或刷新项目状态页

### 2. 批量检测某项目绑定的所有服务器

当前后端暂未实现该接口。

前端如果需要批量检测，可以先调用：

```http
GET /projects/{project_id}/servers
```

拿到绑定服务器列表后，对每台服务器分别调用：

```http
POST /projects/{project_id}/servers/{server_id}/detect
```

### 2. 检测服务器连接状态

```http
POST /servers/{server_id}/check-connection
```

响应示例：

```json
{
  "server_id": 1,
  "server_name": "server-a",
  "connection_mode": "local",
  "connected": true,
  "message": "Connection successful",
  "latency_ms": 35
}
```

## 六、Git 状态接口

GitStatus 是快照型数据。

一条 GitStatus 表示：

```text
某个时刻，某个项目在某台服务器上的 Git 状态。
```

### 1. 手动提交 Git 状态快照

```http
POST /projects/{project_id}/git-status
```

说明：

该接口主要用于开发调试，最终实际使用中更推荐通过检测触发接口自动生成。

请求体：

```json
{
  "server_id": 1,
  "branch": "main",
  "remote_url": "git@example.com:team/projectpilot.git",
  "ahead": 1,
  "behind": 0,
  "has_uncommitted_changes": true,
  "last_commit": "abc123 update backend"
}
```

### 2. 获取某项目的 Git 状态历史

```http
GET /projects/{project_id}/git-status
```

响应示例：

```json
[
  {
    "id": 1,
    "project_id": 1,
    "server_id": 1,
    "branch": "main",
    "remote_url": "git@example.com:team/projectpilot.git",
    "ahead": 1,
    "behind": 0,
    "has_uncommitted_changes": true,
    "last_commit": "abc123 update backend",
    "created_at": "2026-05-18T10:10:00"
  }
]
```

### 3. 获取某服务器的 Git 状态历史

```http
GET /servers/{server_id}/git-status
```

### 4. 获取某项目在某服务器上的最新 Git 状态

```http
GET /projects/{project_id}/servers/{server_id}/git-status/latest
```

响应示例：

```json
{
  "id": 1,
  "project_id": 1,
  "project_name": "ProjectPilot",
  "server_id": 1,
  "server_name": "server-a",
  "branch": "main",
  "remote_url": "git@example.com:team/projectpilot.git",
  "ahead": 1,
  "behind": 0,
  "has_uncommitted_changes": true,
  "last_commit": "abc123 update backend",
  "created_at": "2026-05-18T10:10:00"
}
```

## 七、环境快照接口

EnvironmentSnapshot 是快照型数据。

一条 EnvironmentSnapshot 表示：

```text
某个时刻，某个项目在某台服务器上的环境状态。
```

### 1. 手动提交环境快照

```http
POST /projects/{project_id}/env-snapshots
```

说明：

该接口主要用于开发调试，最终实际使用中更推荐通过检测触发接口自动生成。

请求体：

```json
{
  "server_id": 1,
  "os": "Linux",
  "architecture": "x86_64",
  "python_version": "3.11.8",
  "node_version": "20.11.0",
  "docker_installed": true,
  "docker_running": true,
  "cuda_version": "12.1",
  "disk_usage": "68%",
  "raw_data": {
    "python_packages": {
      "numpy": "1.26.4",
      "torch": "2.2.0"
    },
    "commands": {
      "git": "2.43.0",
      "docker": "26.1.0"
    }
  }
}
```

### 2. 获取某项目的环境快照历史

```http
GET /projects/{project_id}/env-snapshots
```

### 3. 获取某服务器的环境快照历史

```http
GET /servers/{server_id}/env-snapshots
```

### 4. 获取某项目在某服务器上的最新环境快照

```http
GET /projects/{project_id}/servers/{server_id}/env-snapshots/latest
```

## 八、综合状态接口

综合状态接口是前端详情页最推荐调用的接口。

### 1. 获取项目综合状态

```http
GET /projects/{project_id}/status
```

响应示例：

```json
{
  "project": {
    "id": 1,
    "name": "ProjectPilot",
    "path": "/home/user/ProjectPilot",
    "description": "AI 项目环境管理平台",
    "created_at": "2026-05-18T10:00:00"
  },
  "servers": [
    {
      "binding_id": 1,
      "server_id": 1,
      "server_name": "server-a",
      "host": "192.168.1.100",
      "port": 22,
      "username": "ubuntu",
      "connection_mode": "local",
      "project_path": "/opt/projectpilot",
      "latest_git_status": {
        "branch": "main",
        "ahead": 1,
        "behind": 0,
        "has_uncommitted_changes": true
      },
      "latest_git_detection": {
        "id": "task_detect_git_xxx",
        "task_type": "detect_git",
        "status": "completed",
        "executor_id": "server-a",
        "error_type": null,
        "message": null
      },
      "latest_environment_snapshot": {
        "os": "Linux",
        "python_version": "3.11.8",
        "docker_running": true
      },
      "latest_environment_detection": {
        "id": "task_detect_env_xxx",
        "task_type": "detect_environment",
        "status": "completed",
        "executor_id": "server-a",
        "error_type": null,
        "message": null
      }
    }
  ]
}
```

补充说明：

- `latest_git_status` / `latest_environment_snapshot` 表示当前可用的最新成功快照。
- `latest_git_detection` / `latest_environment_detection` 表示最近一次检测任务本身的状态。
- 如果最近一次 `detect_git` 任务失败，而且它比旧的 Git 快照更新，后端会返回：
  - `latest_git_status = null`
  - `latest_git_detection.status = failed`
  - `latest_git_detection.message = 失败原因`
- 前端此时应优先展示检测失败或“检测中”状态，不要再回退显示旧 Git 快照。

### 2. 获取服务器综合状态

```http
GET /servers/{server_id}/status
```

响应示例：

```json
{
  "server": {
    "id": 1,
    "name": "server-a",
    "host": "192.168.1.100",
    "port": 22,
    "username": "ubuntu",
    "connection_mode": "local"
  },
  "projects": [
    {
      "binding_id": 1,
      "project_id": 1,
      "project_name": "ProjectPilot",
      "project_path": "/opt/projectpilot",
      "latest_git_status": {},
      "latest_git_detection": {
        "id": "task_detect_git_xxx",
        "task_type": "detect_git",
        "status": "failed",
        "error_type": "not_git_repository",
        "message": "The target path is not a Git repository."
      },
      "latest_environment_snapshot": {},
      "latest_environment_detection": {
        "id": "task_detect_env_xxx",
        "task_type": "detect_environment",
        "status": "completed"
      }
    }
  ]
}
```

前端展示建议：

- 优先使用 `latest_git_status` 和 `latest_environment_snapshot` 展示成功快照。
- 当它们为 `null` 时，读取对应的 `latest_*_detection`。
- `latest_*_detection.status` 可能是：
  - `queued`
  - `running`
  - `completed`
  - `failed`
- 不要再用假兜底补成 `ssh`、`unknown`、`/demo/projectpilot`、模拟执行结果等演示数据。

## 九、AI 分析接口

### 1. AI 环境分析

```http
POST /projects/{project_id}/ai/analyze-env
```

请求体：

```json
{
  "question": "请分析这个项目在各服务器上的环境风险",
  "focus": "environment"
}
```

响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "focus": "environment",
  "question": "请分析这个项目在各服务器上的环境风险",
  "summary": "当前项目在多台服务器上的环境存在差异。",
  "issues": [
    "server-b 的 Python 版本低于 server-a",
    "server-b 的 Docker 未运行"
  ],
  "suggestions": [
    "确认项目推荐 Python 版本，并统一服务器环境",
    "在 server-b 上启动 Docker 服务"
  ],
  "risk_level": "medium",
  "context": []
}
```

### 2. AI 配置计划生成

```http
POST /projects/{project_id}/ai/config-plan
```

请求体：

```json
{
  "source_server_id": 1,
  "target_server_id": 2,
  "goal": "让目标服务器可以运行该项目",
  "allow_command_generation": true
}
```

说明：

- source_server_id 可选。
- 有 source_server_id 时，表示以源服务器作为参考环境。
- 没有 source_server_id 时，表示基于目标服务器当前状态和项目需求生成配置建议。

响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "source_server_id": 1,
  "source_server_name": "server-a",
  "target_server_id": 2,
  "target_server_name": "server-b",
  "plan_id": null,
  "status": "preview",
  "goal": "让目标服务器可以运行该项目",
  "summary": "根据 server-a 的环境状态，为 server-b 生成配置方案。",
  "risk_level": "medium",
  "steps": [
    {
      "order": 1,
      "title": "启动 Docker 服务",
      "description": "目标服务器已安装 Docker，但 Docker 当前未运行。",
      "command": "sudo systemctl start docker",
      "risk_level": "low",
      "requires_confirmation": true
    }
  ],
  "context": {
    "source_environment_snapshot": {},
    "target_environment_snapshot": {}
  }
}
```

### 3. AI 主动任务规划与执行

```http
POST /projects/{project_id}/ai/plan-action
```

用途：

- 前端传入自然语言需求
- 后端结合项目、目标服务器、环境快照、Git 状态生成结构化计划
- 可只返回预览，也可在确认后直接转成 executor 任务

请求体：

```json
{
  "goal": "帮我检查 server-b 上这个项目当前状态，并在安全前提下尝试同步代码",
  "target_server_id": 2,
  "source_server_id": 1,
  "allow_command_generation": true,
  "auto_execute": false,
  "confirmed": false
}
```

字段说明：

- `goal`：用户在前端输入的自然语言需求
- `target_server_id`：目标服务器
- `source_server_id`：可选，作为参考环境/参考仓库
- `allow_command_generation`：是否允许 AI 生成命令
- `auto_execute`：是否直接进入执行阶段
- `confirmed`：只有当 `auto_execute=true` 且用户确认后才应传 `true`

预览模式响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "goal": "帮我检查 server-b 上这个项目当前状态，并在安全前提下尝试同步代码",
  "status": "preview",
  "message": "AI action plan generated. Review before execution.",
  "target_server": {
    "id": 2,
    "name": "server-b",
    "connection_mode": "executor",
    "project_path": "/home/hzy/project/web"
  },
  "plan": {
    "plan_type": "action_plan",
    "status": "preview",
    "risk_level": "medium",
    "steps": [
      {
        "order": 1,
        "title": "确认仓库状态",
        "command": "git status --short --branch",
        "risk_level": "low"
      },
      {
        "order": 2,
        "title": "尝试安全拉取",
        "command": "git pull --ff-only",
        "risk_level": "medium"
      }
    ]
  }
}
```

当 `auto_execute=true` 且目标服务器为 `executor` 时，响应会变成异步入队：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "goal": "帮我检查 server-b 上这个项目当前状态，并在安全前提下尝试同步代码",
  "status": "queued",
  "message": "AI action plan queued for executor execution.",
  "tasks": [
    {
      "id": "task_xxx",
      "task_type": "run_local_script",
      "status": "queued",
      "executor_id": "server-b"
    }
  ],
  "safety_report": []
}
```

## 十、配置计划执行接口

配置计划执行接口用于用户人工确认后执行配置方案。

当前执行接口已经包含安全检查，并会根据 `connection_mode` 分流：

```text
local -> 模拟执行，避免误操作本机
executor -> 创建异步执行任务，由目标机器上的 executor 拉取并执行
```

注意：即使 `confirmed=true`，后端仍会再次检查命令安全性。`blocked` 命令不会执行。

### 1. 执行配置计划

```http
POST /projects/{project_id}/servers/{server_id}/execute-config-plan
```

请求体：

```json
{
  "confirmed": true,
  "steps": [
    {
      "order": 1,
      "title": "启动 Docker 服务",
      "command": "sudo systemctl start docker",
      "risk_level": "low"
    }
  ]
}
```

`local` 模式响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "server_id": 1,
  "server_name": "server-a",
  "project_path": "/home/huancheng/AutoEnv/ProjectPilot",
  "connection_mode": "local",
  "status": "completed",
  "safety_report": [
    {
      "order": 1,
      "title": "启动 Docker 服务",
      "command": "sudo systemctl start docker",
      "declared_risk_level": "low",
      "safety": {
        "level": "medium",
        "allowed": true,
        "reason": "Requires confirmation because it matches: \\bsudo\\b"
      }
    }
  ],
  "results": [
    {
      "order": 1,
      "title": "启动 Docker 服务",
      "command": "sudo systemctl start docker",
      "risk_level": "low",
      "safety": {
        "level": "medium",
        "allowed": true,
        "reason": "Requires confirmation because it matches: \\bsudo\\b"
      },
      "status": "success",
      "exit_code": 0,
      "stdout": "Docker started",
      "stderr": ""
    }
  ]
}
```

`executor` 模式响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "server_id": 1,
  "server_name": "server-a",
  "project_path": "/home/huancheng/AutoEnv/ProjectPilot",
  "connection_mode": "executor",
  "status": "queued",
  "message": "Config plan queued for executor execution.",
  "safety_report": [
    {
      "order": 1,
      "title": "Check Python",
      "command": "python3 --version",
      "declared_risk_level": "low",
      "safety": {
        "level": "low",
        "allowed": true,
        "reason": "Read-only command."
      }
    }
  ],
  "tasks": [
    {
      "id": "task_xxx",
      "project_id": 1,
      "server_id": 1,
      "task_type": "run_local_script",
      "status": "queued",
      "executor_id": "server-a"
    }
  ]
}
```

如果命令被拦截，示例：

```json
{
  "command": "rm -rf /",
  "status": "blocked",
  "exit_code": null,
  "stderr": "Blocked by dangerous pattern: \\brm\\s+-rf\\b"
}
```

## 十一、Executor 任务接口

当前前端在 `executor` 模式下如果需要更细的异步状态，可以查询任务接口。

### 1. 获取全部 Executor 任务

```http
GET /executor/tasks
```

支持查询参数：

```text
project_id
server_id
status
```

响应示例：

```json
[
  {
    "id": "task_xxx",
    "project_id": 1,
    "server_id": 1,
    "task_type": "detect_environment",
    "status": "completed",
    "payload": {},
    "result": {},
    "executor_id": "server-a",
    "error_type": null,
    "message": null,
    "created_at": "2026-06-01T11:00:54",
    "claimed_at": "2026-06-01T11:00:59",
    "completed_at": "2026-06-01T11:01:00"
  }
]
```

### 2. 获取单个 Executor 任务

```http
GET /executor/tasks/{task_id}
```

## 十二、报告接口

### 1. 生成项目报告

```http
POST /reports/project
```

请求体：

```json
{
  "project_id": 1,
  "include_ai_analysis": true
}
```

响应示例：

```json
{
  "project_id": 1,
  "project_name": "ProjectPilot",
  "format": "markdown",
  "content": "# ProjectPilot 项目状态报告\n\n## 项目基本信息\n..."
}
```

## 十三、操作日志接口

操作日志用于记录检测、AI 配置计划生成、人工确认、命令执行等关键行为。

### 1. 获取全部操作日志

```http
GET /operation-logs
```

响应示例：

```json
[
  {
    "id": 1,
    "project_id": 1,
    "server_id": 2,
    "operation_type": "execute_config_plan",
    "risk_level": "medium",
    "status": "completed",
    "summary": "执行 AI 配置计划",
    "created_at": "2026-05-18T10:30:00"
  }
]
```

### 2. 获取某项目操作日志

```http
GET /projects/{project_id}/operation-logs
```

### 3. 获取某服务器操作日志

```http
GET /servers/{server_id}/operation-logs
```

## 十四、AI 相关接口汇总

当前前端可以直接使用的 AI / 智能分析相关接口有：

- `GET /ai/settings`
  用途：读取当前 AI provider / model / 是否已配置 API Key

- `POST /projects/{project_id}/ai/analyze-env`
  用途：基于最新环境快照做环境风险分析

- `POST /projects/{project_id}/ai/config-plan`
  用途：根据源/目标服务器环境生成配置计划

- `POST /projects/{project_id}/ai/plan-action`
  用途：根据自然语言需求生成主动执行计划，并可在确认后直接转为 executor 任务

- `POST /projects/{project_id}/ai/analyze-git`
  用途：调用 eddz 的 smart_git 能力，对仓库做状态、doctor、map、sync_plan、commit_plan 等分析

`analyze-git` 请求体示例：

```json
{
  "analyses": ["status", "doctor", "map", "sync_plan", "commit_plan"]
}
```

## 十五、前端主要页面与推荐接口

### 项目列表页

推荐接口：

- GET /projects
- POST /projects
- DELETE /projects/{project_id}

### 项目详情页

推荐接口：

- GET /projects/{project_id}/status
- POST /projects/{project_id}/servers/{server_id}/detect
- POST /projects/{project_id}/ai/analyze-env
- POST /projects/{project_id}/ai/analyze-git
- POST /projects/{project_id}/ai/config-plan
- POST /projects/{project_id}/ai/plan-action
- POST /reports/project

### 服务器列表页

推荐接口：

- GET /servers
- POST /servers
- POST /servers/{server_id}/check-connection
- DELETE /servers/{server_id}

### 服务器详情页

推荐接口：

- GET /servers/{server_id}/status
- GET /servers/{server_id}/projects
- GET /servers/{server_id}/git-status
- GET /servers/{server_id}/env-snapshots

### 项目服务器绑定页

推荐接口：

- GET /projects/{project_id}/servers
- GET /servers
- POST /projects/{project_id}/bind-server
- DELETE /projects/{project_id}/servers/{server_id}

### AI 配置计划页

推荐接口：

- POST /projects/{project_id}/ai/config-plan
- POST /projects/{project_id}/servers/{server_id}/execute-config-plan
- GET /executor/tasks
- GET /projects/{project_id}/operation-logs

### 报告页

推荐接口：

- POST /reports/project

## 十六、最终核心闭环

最终系统希望形成以下闭环：

```text
添加项目
-> 添加服务器
-> 绑定项目和服务器
-> 触发检测
-> local 模式同步完成 / executor 模式创建异步任务
-> executor 拉取任务并执行
-> 保存 GitStatus 和 EnvironmentSnapshot
-> 查看项目/服务器综合状态
-> AI 分析环境问题
-> AI 分析 Git 状态与下一步建议
-> AI 生成配置计划
-> 用户人工审核
-> 执行配置计划
-> 记录操作日志
-> 生成项目报告
```
