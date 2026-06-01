# 开发记录 2

## 当前进展概述

本阶段在第一阶段基础后端之上，继续完成了环境检测数据存储、综合状态查询、AI 分析接口雏形，并对后端代码结构进行了整理。

本阶段重点包括：

- 新增 EnvironmentSnapshot 环境快照模型
- 为环境快照增加 raw_data 字段
- 新增环境快照相关接口
- 新增项目和服务器综合状态接口
- 新增 AI 环境分析接口雏形
- 将原本集中在 main.py 中的接口拆分到 routers 目录
- 将请求体模型拆分到 schemas.py
- 将可复用逻辑拆分到 services 目录

## 新增 EnvironmentSnapshot

新增文件：

```text
backend/models/environment_snapshot.py
```

EnvironmentSnapshot 用于保存一次环境检测快照。

当前设计中，一条 EnvironmentSnapshot 表示：

```text
在某一个时刻，某个项目在某台服务器上的环境状态。
```

主要字段：

- id
- project_id
- server_id
- os
- architecture
- python_version
- node_version
- docker_installed
- docker_running
- cuda_version
- disk_usage
- raw_data
- created_at

## raw_data 字段设计

环境信息非常宽泛，不能把所有可能的环境项都设计成固定字段。

因此当前采用：

```text
摘要字段 + raw_data
```

的设计方式。

摘要字段用于前端快速展示和常见环境对比，例如：

- Python 版本
- Node.js 版本
- Docker 状态
- CUDA 版本
- 磁盘占用

raw_data 用于保存更完整、不固定的环境详情，例如：

- Python 包版本
- Node 包版本
- 系统命令版本
- conda 环境
- pip freeze 信息
- 项目特定依赖信息

这样可以避免每新增一种检测项就修改数据库表结构。

## 新增环境快照接口

新增接口：

- POST /projects/{project_id}/env-snapshots
- GET /projects/{project_id}/env-snapshots
- GET /servers/{server_id}/env-snapshots
- GET /projects/{project_id}/servers/{server_id}/env-snapshots/latest

说明：

- POST 用于保存一条环境检测快照。
- 项目维度 GET 用于查看某个项目的环境快照历史。
- 服务器维度 GET 用于查看某台服务器相关的环境快照历史。
- latest 接口用于查看某个项目在某台服务器上的最新环境状态。

## 新增综合状态接口

新增接口：

- GET /projects/{project_id}/status
- GET /servers/{server_id}/status

项目综合状态接口会返回：

- 项目基本信息
- 绑定的服务器列表
- 每台服务器上的项目路径
- 每台服务器的最新 Git 状态
- 每台服务器的最新环境快照

服务器综合状态接口会返回：

- 服务器基本信息
- 服务器绑定的项目列表
- 每个项目在该服务器上的路径
- 每个项目的最新 Git 状态
- 每个项目的最新环境快照

这两个接口主要面向前端详情页和总览页。

## 新增 AI 环境分析接口雏形

新增接口：

```text
POST /projects/{project_id}/ai/analyze-env
```

请求体示例：

```json
{
  "question": "请分析这个项目在各服务器上的环境风险",
  "focus": "environment"
}
```

当前版本尚未接入真实大模型，而是使用模拟分析函数生成结构化结果。

返回内容包括：

- project_id
- project_name
- focus
- question
- summary
- issues
- suggestions
- risk_level
- context

其中 context 会返回本次分析所基于的最新环境快照数据，便于调试和前端展示。

后续真实接入 AI 时，主要替换 services/ai_service.py 中的模拟分析逻辑。

## 后端结构重构

重构前，大部分接口、请求模型和辅助函数都集中在：

```text
backend/main.py
```

随着功能增加，main.py 开始变得过长，不利于维护。

因此本阶段将代码拆分为：

```text
backend/
├── main.py
├── database.py
├── schemas.py
├── models/
├── routers/
│   ├── projects.py
│   ├── servers.py
│   ├── bindings.py
│   ├── git_status.py
│   ├── environment_snapshots.py
│   ├── status.py
│   └── ai.py
└── services/
    ├── formatters.py
    └── ai_service.py
```

## 各目录职责

### main.py

后端入口文件。

当前主要负责：

- 创建 FastAPI app
- 自动创建数据库表
- 注册各个 router
- 提供 / 和 /health 基础接口

### schemas.py

保存请求体模型。

例如：

- ProjectCreate
- ServerCreate
- ProjectServerBind
- GitStatusCreate
- EnvironmentSnapshotCreate
- AIAnalyzeRequest

### routers

保存接口定义。

其中：

- projects.py：项目接口
- servers.py：服务器接口
- bindings.py：项目服务器绑定接口
- git_status.py：Git 状态接口
- environment_snapshots.py：环境快照接口
- status.py：综合状态接口
- ai.py：AI 分析接口

### services

保存可复用业务逻辑。

当前包括：

- formatters.py：将数据库对象转换成 JSON 字典
- ai_service.py：模拟 AI 环境分析逻辑

后续真实接入 AI 时，优先修改 ai_service.py。

## 测试情况

本阶段完成后，执行了编译检查：

```bash
python3 -m compileall backend
```

检查通过。

同时确认 FastAPI app 可以正常导入，接口已成功注册。

## 当前接口分组

当前已经实现的主要接口包括：

- 项目管理接口
- 服务器管理接口
- 项目服务器绑定接口
- Git 状态快照接口
- 环境快照接口
- 项目综合状态接口
- 服务器综合状态接口
- AI 环境分析接口

## 当前阶段理解

当前系统已经从简单的数据管理，逐步发展为一个可以组织项目状态、服务器状态、Git 状态和环境状态的后端平台。

其中：

- GitStatus 用于记录 Git 状态快照
- EnvironmentSnapshot 用于记录环境状态快照
- status 接口用于生成前端可直接展示的综合状态
- AI 接口用于基于已有状态数据生成分析建议

## 下一步计划

下一步可以考虑实现报告生成模块。

计划新增：

```text
POST /reports/project
```

该接口可以基于：

- 项目信息
- 服务器绑定关系
- 最新 Git 状态
- 最新环境快照
- AI 分析结果

生成一份 Markdown 格式的项目状态报告。

报告模块完成后，ProjectPilot 将具备更完整的展示和答辩材料输出能力。
