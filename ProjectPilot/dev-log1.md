# 开发记录 1

## 当前进度

ProjectPilot 后端已经完成第一阶段基础搭建，当前使用：

- FastAPI
- SQLite
- SQLAlchemy

目前后端已经可以：

- 启动 FastAPI 服务
- 提供基础健康检查接口
- 自动创建数据库表
- 管理项目
- 管理服务器
- 建立项目和服务器的绑定关系
- 保存 Git 状态快照
- 查询 Git 状态历史
- 查询某个项目在某台服务器上的最新 Git 状态

## 当前项目结构

```text
ProjectPilot/
└── backend/
    ├── main.py
    ├── database.py
    ├── seed.py
    └── models/
        ├── project.py
        ├── server.py
        ├── project_server_mapping.py
        └── git_status.py
```

## 已实现的数据模型

### Project

用于保存项目基本信息。

主要字段：

- id
- name
- path
- description
- created_at

### Server

用于保存服务器基本信息。

主要字段：

- id
- name
- host
- port
- username
- description
- created_at

### ProjectServerMapping

用于保存项目和服务器之间的绑定关系。

之所以单独建这张表，是因为：

- 一个项目可以部署在多台服务器上
- 一台服务器也可以部署多个项目
- project_path 属于“项目和服务器之间的关系”，不应该直接放在 Server 表里

主要字段：

- id
- project_id
- server_id
- project_path
- created_at

### GitStatus

用于保存 Git 状态快照。

当前设计中，一条 GitStatus 表示：

```text
在某一个时刻，某个项目在某台服务器上的 Git 状态。
```

主要字段：

- id
- project_id
- server_id
- branch
- remote_url
- ahead
- behind
- has_uncommitted_changes
- last_commit
- created_at

## 已实现的接口

### 基础接口

- GET /
- GET /health

### 项目接口

- POST /projects
- GET /projects
- GET /projects/{project_id}
- DELETE /projects/{project_id}

说明：

- 创建项目时会检查 path 是否重复。

### 服务器接口

- POST /servers
- GET /servers
- GET /servers/{server_id}
- DELETE /servers/{server_id}

说明：

- 创建服务器时会检查 host + port 是否重复。

### 项目和服务器绑定接口

- POST /projects/{project_id}/bind-server
- GET /projects/{project_id}/servers
- GET /servers/{server_id}/projects
- DELETE /projects/{project_id}/servers/{server_id}

### Git 状态接口

- POST /projects/{project_id}/git-status
- GET /projects/{project_id}/git-status
- GET /servers/{server_id}/git-status
- GET /projects/{project_id}/servers/{server_id}/git-status/latest

说明：

- 当前 GitStatus 是快照型设计。
- 每次 POST 会新增一条 Git 状态检测快照。
- 历史查询接口会返回符合条件的 Git 状态快照列表。
- latest 接口会返回某个项目在某台服务器上的最新一条 Git 状态快照。

## 测试数据脚本

已添加：

```text
backend/seed.py
```

该脚本用于插入测试数据，包括：

- 示例项目
- 示例服务器
- 项目和服务器绑定关系
- GitStatus 测试快照

运行方式：

```bash
cd /home/huancheng/AutoEnv/ProjectPilot/backend
python3 seed.py
```

## 当前设计理解

当前后端将几个概念分开处理：

- Project：表示项目本身
- Server：表示服务器本身
- ProjectServerMapping：表示某个项目部署在某台服务器上的某个路径
- GitStatus：表示某个时刻的一次 Git 状态检测结果

这样设计的好处是：

- 可以保存 Git 状态历史
- 可以查看某个项目在某台服务器上的最新状态
- 可以支持后续 AI 分析状态变化
- 可以为报告生成和操作审计提供数据基础

## 下一步计划

下一步准备实现 EnvironmentSnapshot 模块。

它用于保存环境检测快照，例如：

- 操作系统
- Python 版本
- Node.js 版本
- Docker 是否安装
- Docker 是否运行
- CUDA 版本
- 磁盘占用

该模块完成后，成员 B 的环境检测结果就可以交给成员 A 的后端保存，并在后续用于 AI 分析和环境差异报告生成。
