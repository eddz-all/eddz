# ProjectPilot 主机 AI 与 SSH 远程管理完整方案

## 0. 阅读指南

这篇文档只讲一件事：

```text
主机 AI 如何通过 Executor 管理多台 SSH 服务器。
```

完整产品形态看 `ProjectPilot最终产品方案.md`，本文只补执行层。先记住最终决定：

| 问题 | 决定 |
| --- | --- |
| 谁执行命令 | Executor，不是 AI Planner |
| 主模式 | Central Executor，部署在主机后端侧 |
| 补充模式 | Local Executor，部署在用户本机或内网机器 |
| SSH 配置 | Executor 读取所在机器的 `~/.ssh/config` 或后端托管 Host 配置 |
| 私钥 | 不交给 AI Planner；Local Executor 优先走系统 `ssh-agent` / Keychain |
| 接口 | 只保留 `/executor/poll` 和 `/executor/tasks/{task_id}/result` |
| 执行边界 | 白名单命令、路径限制、审批、审计、快照、可回滚优先 |

推荐阅读顺序：

```text
1. 目标
2. 关键原则
3. 总体架构
5. SSH 连接方案
6. Executor 任务模式
12. 安全设计
15. 执行计划
```

## 1. 目标

ProjectPilot 的目标不是让 AI 无限制接管服务器，而是做一个可控、可审计、可恢复的智能项目管理系统。

核心能力包括：

- 本地 Git 状态检测；
- 远程服务器 Git 状态检测；
- 远程服务器环境检测；
- 远程配置建议生成；
- 受控远程执行；
- 操作结果入库；
- 前端统一展示；
- AI 基于状态和历史生成建议。

最终形态：

```text
前端
  ↓
主机后端 / 数据库 / AI
  ↓ 已批准任务
Executor 执行器层
  ↓ SSH
远程服务器
```

架构更新说明：

```text
AI = 决策大脑
Executor = 手
后端 = 神经系统 + 当前状态记忆
数据库 = 历史记录 + 审计证据
```

Executor 有两种模式：

```text
Central Executor
  部署在主机后端所在机器。
  读取主机上的 SSH config 或托管 SSH Host 配置。
  作为服务器集中管理的主模式。

Local Executor
  部署在用户本机或内网机器。
  读取本机 ~/.ssh/config 和 ssh-agent。
  作为私钥不出本机、主机不能直连内网时的补充模式。
```

## 2. 关键原则

### 2.1 AI 不直接持有 SSH 私钥

SSH 私钥不应该交给 AI Planner。私钥可以由受控 Executor 读取或托管，取决于执行模式。

主机 AI 不应该直接拿到：

- `~/.ssh/id_rsa`;
- `~/.ssh/id_ed25519`;
- 私钥文本；
- 服务器 root 密码。

推荐方式：

```text
主机 AI 生成任务
用户批准计划
Executor 读取 SSH config 或托管 Host 配置
Executor 使用 ssh-agent / Keychain / 受控密钥路径连接服务器
Executor 上传执行结果
```

Central Executor 可以集中管理服务器 SSH Host 和密钥路径，但仍然不能让 AI 直接读取私钥文本或自由拼接命令。

### 2.2 第一阶段只做只读检测

第一阶段允许：

- `check_connection`;
- `detect_git`;
- `detect_environment`;
- `git_fetch`;
- `git_diff`;
- `git_log`.

第一阶段禁止：

- 任意命令执行；
- `rm -rf`;
- `git reset --hard`;
- `git clean -fd`;
- `git push --force`;
- 自动 rebase；
- 自动 merge；
- 自动修改服务器配置。

### 2.3 后端是控制中心，Executor 是执行者

后端负责：

- 项目管理；
- 服务器管理；
- 任务创建；
- 权限校验；
- 风险分级；
- 数据库存储；
- 审计记录；
- AI 分析；
- 前端接口。

Executor 负责：

- 读取或托管 SSH 配置；
- 连接服务器；
- 执行已批准任务；
- 上传结构化结果；
- 保存或读取执行器连接配置；
- 显示连接状态。

两种模式的差别：

| 模式 | 部署位置 | SSH 配置来源 | 适合场景 |
| --- | --- | --- | --- |
| Central Executor | 主机后端所在机器 | 主机 `~/.ssh/config` 或后端托管 Host 配置 | 主机能直连所有服务器，追求速度和集中管理 |
| Local Executor | 用户本机或内网机器 | 本机 `~/.ssh/config`、ssh-agent、Keychain | 私钥不出本机，或主机不能直连内网服务器 |

最终默认主模式是 Central Executor；Local Executor 是补充模式。

## 3. 总体架构

```text
┌────────────────────┐
│      前端 UI        │
│ 项目 / 服务器 / AI   │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│    主机后端 Backend │
│ 任务 / 权限 / 数据库 │
└─────────┬──────────┘
          │ approved task / result
          ▼
┌────────────────────┐
│   Executor 执行器    │
│ Central / Local│
└─────────┬──────────┘
          │ ssh
          ▼
┌────────────────────┐
│     远程服务器       │
│ Git / Docker / 环境 │
└────────────────────┘
```

## 4. Executor App / Service 设计

### 4.1 两种形态

Executor 有两种最终形态：

```text
Central Executor
  部署在主机后端所在机器。
  适合集中控制多台服务器。

Local Executor
  部署在用户本机或内网机器。
  适合复用本机 SSH config，或服务器只在内网可达。
```

Local Executor 第一版推荐做成 macOS 原生窗口应用：

```text
ProjectPilot Executor.app
```

窗口能力：

- 配置后端地址；
- 配置 token；
- 配置 executor_id；
- 选择 allowed-root；
- 扫描 `~/.ssh/config`;
- 展示 SSH Host 列表；
- 测试连接；
- 启动 / 停止 Local Executor；
- 查看最近任务；
- 查看最近错误。

Central Executor 第一版可以做成后端同机 Worker：

```text
projectpilot-executor
```

能力：

- 读取主机上的 SSH config；
- 管理服务器连接池；
- 获取已批准任务；
- 执行 Git / Docker / 环境命令；
- 上传执行结果；
- 写入审计日志。

### 4.2 Executor 配置

Local Executor 配置文件：

```text
~/.projectpilot/executor.json
```

示例：

```json
{
  "server_url": "http://backend.example.test",
  "token": "executor-token",
  "executor_id": "eddz-mac-local",
  "mode": "local",
  "allowed_root": "/Users/eddz/work",
  "interval": 5
}
```

Central Executor 可以使用：

```text
/etc/projectpilot/executor.toml
```

或后端数据库中的托管 Executor 配置。

安全要求：

- 文件权限尽量设置为 `0600`;
- token 不在 UI 明文展示；
- SSH 私钥不交给 AI Planner；
- Local Executor 优先走系统 `ssh`、`ssh-agent` 和 Keychain；
- Central Executor 可以配置受控密钥路径，但必须限制文件权限和服务器范围。

## 5. SSH 连接方案

### 5.1 自动加载 SSH 配置

Executor 读取：

```text
~/.ssh/config
```

扫描其中的 Host：

```sshconfig
Host dev-server
  HostName 192.168.1.20
  User ubuntu
  Port 22
  IdentityFile ~/.ssh/id_ed25519

Host prod-server
  HostName prod.example.com
  User deploy
  Port 2222
  ProxyJump gateway
```

Executor 设置页展示：

```text
dev-server
prod-server
```

### 5.2 不建议手写完整 SSH 解析器

OpenSSH 配置支持很多语法：

- `Include`;
- `Host *`;
- 通配符；
- `ProxyJump`;
- `ProxyCommand`;
- 多个 `IdentityFile`;
- `User`;
- `Port`;
- `ControlMaster`;
- `ControlPersist`.

因此建议：

1. 自己只扫描可见 Host 别名；
2. 用 OpenSSH 自己展开最终配置：

```bash
ssh -G dev-server
```

获得：

```text
hostname 192.168.1.20
user ubuntu
port 22
identityfile ~/.ssh/id_ed25519
```

### 5.3 连接测试

任务：

```json
{
  "type": "check_connection",
  "ssh_host": "dev-server"
}
```

执行：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 dev-server "echo projectpilot-ok"
```

成功返回：

```json
{
  "success": true,
  "connected": true,
  "ssh_host": "dev-server",
  "latency_ms": 42,
  "message": "Connection successful"
}
```

失败返回：

```json
{
  "success": false,
  "connected": false,
  "ssh_host": "dev-server",
  "error_type": "ssh_connection_failed",
  "message": "Permission denied (publickey)."
}
```

## 6. Executor 任务模式

### 6.1 两种取任务方式

Central Executor 和 Local Executor 可以使用不同的取任务方式。

```text
Central Executor
  可以由后端队列直接派发任务，也可以由 worker 主动拉取任务。

Local Executor
  推荐使用轮询，避免用户电脑开放公网端口。
```

Local Executor 使用轮询的优点：

- 用户电脑不用开放公网端口；
- 不需要后端 SSH 到用户电脑；
- 不需要端口映射；
- 不需要内网穿透；
- 私钥留在本机；
- 后端仍可统一调度。

### 6.2 后端接口

第一版只需要两个 Executor 接口：

```text
POST /executor/poll
POST /executor/tasks/{task_id}/result
```

### 6.3 Executor 取任务请求

```json
{
  "executor_id": "host-executor-01",
  "mode": "central",
  "token": "executor-token",
  "capabilities": [
    "check_connection",
    "detect_git",
    "detect_environment",
    "git_fetch",
    "git_log",
    "git_diff"
  ],
  "status": "online"
}
```

### 6.4 后端无任务返回

```json
{
  "task": null
}
```

### 6.5 后端有任务返回

```json
{
  "task": {
    "id": "task_001",
    "type": "detect_git",
    "ssh_host": "dev-server",
    "project_path": "/srv/projectpilot"
  }
}
```

### 6.6 Executor 上传结果

```json
{
  "task_id": "task_001",
  "executor_id": "eddz-mac-local",
  "success": true,
  "result": {
    "success": true,
    "branch": "main",
    "remote_url": "git@example.com:team/projectpilot.git",
    "ahead": 0,
    "behind": 2,
    "has_uncommitted_changes": false,
    "last_commit": "abc123 fix deploy config"
  }
}
```

## 7. Git 管理方案

### 7.1 本地 Git 检测

本地检测函数：

```python
detect_local_git_status(project_path: str) -> dict
```

返回：

```json
{
  "success": true,
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "upstream": "origin/main",
  "remote_url": "git@example.com:team/projectpilot.git",
  "ahead": 1,
  "behind": 0,
  "has_uncommitted_changes": true,
  "is_clean": false,
  "state": "normal",
  "staged_count": 1,
  "unstaged_count": 2,
  "untracked_count": 3,
  "conflicted_count": 0,
  "last_commit": "abc123 update backend"
}
```

### 7.2 远程 Git 检测

任务：

```json
{
  "type": "detect_git",
  "ssh_host": "dev-server",
  "project_path": "/srv/projectpilot"
}
```

远程执行：

```bash
ssh dev-server "cd /srv/projectpilot && git status --porcelain=v2 --branch --untracked-files=all"
ssh dev-server "cd /srv/projectpilot && git remote -v"
ssh dev-server "cd /srv/projectpilot && git log -1 --pretty=%h\ %s"
```

Executor 解析为结构化数据后上传。

### 7.3 Git 状态分类

| 状态 | 条件 | 是否允许自动操作 |
| --- | --- | --- |
| clean | 无本地改动 | 允许检测 |
| dirty | 有 unstaged / untracked | 禁止自动 pull |
| ahead | ahead > 0, behind = 0 | 可建议 push |
| behind | ahead = 0, behind > 0 | 可建议 pull --ff-only |
| diverged | ahead > 0, behind > 0 | 禁止自动处理 |
| conflict | 有冲突文件 | 禁止自动处理 |
| no_upstream | 无 upstream | 只建议配置 upstream |

### 7.4 安全 Git 操作

允许模板：

```text
git status
git log
git diff
git fetch
git pull --ff-only
git push
```

执行条件：

#### git fetch

允许条件：

- 仓库存在；
- remote 存在。

#### git pull --ff-only

允许条件：

- working tree clean；
- ahead = 0；
- behind > 0；
- 分支有 upstream。

禁止条件：

- dirty；
- diverged；
- conflict；
- no upstream。

#### git push

允许条件：

- working tree clean；
- ahead > 0；
- behind = 0；
- 分支有 upstream。

禁止条件：

- dirty；
- behind > 0；
- diverged；
- conflict；
- force push。

### 7.5 禁止的 Git 操作

默认禁止：

```text
git reset --hard
git clean -fd
git push --force
git rebase
git merge
git checkout -- .
```

这些操作未来可以作为高风险操作，但必须：

- AI 生成计划；
- 后端标记 high risk；
- 前端要求用户确认；
- Executor 二次确认；
- 全量写审计日志。

## 8. 远程环境检测方案

### 8.1 目标

远程环境检测用于判断服务器是否具备运行项目的条件。

检测内容：

- 操作系统；
- CPU 架构；
- Python 版本；
- Node.js 版本；
- Docker 是否安装；
- Docker 是否运行；
- CUDA / GPU 状态；
- 磁盘占用；
- 常见端口；
- 项目目录是否存在；
- 环境变量摘要；
- 包管理器状态。

### 8.2 任务格式

```json
{
  "type": "detect_environment",
  "ssh_host": "dev-server",
  "project_path": "/srv/projectpilot"
}
```

### 8.3 远程命令模板

基础环境：

```bash
uname -s
uname -m
python3 --version
node --version
npm --version
docker --version
docker info
df -h /
```

项目路径：

```bash
test -d /srv/projectpilot && echo exists || echo missing
```

CUDA：

```bash
nvidia-smi --query-gpu=driver_version --format=csv,noheader
```

Docker Compose：

```bash
docker compose version
```

### 8.4 返回格式

```json
{
  "success": true,
  "ssh_host": "dev-server",
  "os": "Linux",
  "architecture": "x86_64",
  "python_version": "3.11.8",
  "node_version": "20.11.0",
  "docker_installed": true,
  "docker_running": true,
  "cuda_version": "12.1",
  "disk_usage": "68%",
  "project_path_exists": true,
  "raw_data": {
    "commands": {
      "uname": "Linux",
      "python3": "Python 3.11.8",
      "node": "v20.11.0",
      "docker": "Docker version 26.1.0"
    }
  }
}
```

## 9. 远程配置环境方案

### 9.1 AI 生成配置建议

AI 不直接执行配置命令。

AI 输出配置计划：

```json
{
  "plan_id": "plan_001",
  "server": "dev-server",
  "summary": "Install missing Node.js dependency and start Docker service.",
  "steps": [
    {
      "id": "step_1",
      "command": "node --version",
      "risk_level": "low",
      "requires_confirmation": false,
      "reason": "Check current Node.js version."
    },
    {
      "id": "step_2",
      "command": "npm install",
      "cwd": "/srv/projectpilot",
      "risk_level": "medium",
      "requires_confirmation": true,
      "reason": "Install project dependencies."
    },
    {
      "id": "step_3",
      "command": "sudo systemctl restart docker",
      "risk_level": "high",
      "requires_confirmation": true,
      "reason": "Restarting Docker may affect running containers."
    }
  ]
}
```

### 9.2 风险分级

| 风险 | 示例 | 是否自动执行 |
| --- | --- | --- |
| low | `git status`, `python3 --version`, `df -h` | 可以 |
| medium | `npm install`, `pip install`, `git pull --ff-only` | 需要确认 |
| high | `systemctl restart`, `docker compose up -d`, 数据库迁移 | 强确认 |
| blocked | `rm -rf`, `git reset --hard`, `push --force` | 默认禁止 |

### 9.3 配置执行边界

第一阶段只生成建议，不执行。

第二阶段允许执行低风险命令。

第三阶段允许执行中风险命令，但必须用户确认。

高风险命令默认只生成说明，不直接执行。

## 10. 数据库设计建议

### 10.1 Project

```text
id
name
repo_url
created_at
updated_at
```

### 10.2 Server

```text
id
name
ssh_host_alias
description
created_at
updated_at
```

注意：

```text
ssh_host_alias = ~/.ssh/config 里的 Host 名称
```

不要保存私钥。

### 10.3 ProjectServer

```text
id
project_id
server_id
project_path
allowed
created_at
updated_at
```

### 10.4 GitStatus

```text
id
project_id
server_id nullable
branch
upstream
remote_url
ahead
behind
has_uncommitted_changes
is_clean
state
last_commit
raw_data
created_at
```

### 10.5 EnvironmentSnapshot

```text
id
project_id
server_id nullable
os
architecture
python_version
node_version
docker_installed
docker_running
cuda_version
disk_usage
project_path_exists
raw_data
created_at
```

### 10.6 ExecutorTask

```text
id
executor_id
project_id
server_id nullable
type
status
payload
result
error_type
message
created_at
started_at
finished_at
```

### 10.7 OperationLog

```text
id
actor_type
actor_id
project_id
server_id nullable
task_id
operation
risk_level
command
cwd
success
stdout_summary
stderr_summary
raw_data
created_at
```

## 11. 后端接口建议

### 11.1 Executor 取任务

```text
POST /executor/poll
```

请求：

```json
{
  "executor_id": "host-executor-01",
  "mode": "central",
  "capabilities": ["detect_git", "detect_environment"],
  "status": "online"
}
```

返回：

```json
{
  "task": {
    "id": "task_001",
    "type": "detect_git",
    "ssh_host": "dev-server",
    "project_path": "/srv/projectpilot"
  }
}
```

### 11.2 Executor 上传结果

```text
POST /executor/tasks/{task_id}/result
```

请求：

```json
{
  "executor_id": "host-executor-01",
  "success": true,
  "result": {}
}
```

### 11.3 前端触发检测

```text
POST /projects/{project_id}/servers/{server_id}/detect
```

后端行为：

```text
创建 ExecutorTask
等待 Executor 获取任务
接收结果
保存 GitStatus / EnvironmentSnapshot
返回前端
```

### 11.4 前端查看状态

```text
GET /projects/{project_id}/status
GET /projects/{project_id}/servers
GET /projects/{project_id}/operations
```

## 12. 安全设计

### 12.1 Token 鉴权

Executor 每次请求后端都带：

```http
Authorization: Bearer <executor-token>
```

后端校验：

- token 是否存在；
- token 是否绑定 executor_id；
- token 是否被禁用；
- token 是否有执行该任务权限。

### 12.2 路径限制

本机项目路径必须在：

```text
allowed_root
```

远程服务器路径必须在：

```text
allowed_paths
```

例如：

```json
{
  "ssh_host": "dev-server",
  "allowed_paths": [
    "/srv/projectpilot",
    "/srv/apps"
  ]
}
```

### 12.3 命令白名单

任务类型白名单：

```text
check_connection
detect_git
detect_environment
git_fetch
git_log
git_diff
```

禁止直接传：

```json
{
  "command": "any shell command"
}
```

### 12.4 审计

每次操作记录：

- 谁发起；
- 哪台机器执行；
- 哪台服务器；
- 哪个项目路径；
- 什么命令模板；
- 风险等级；
- 是否成功；
- stdout 摘要；
- stderr 摘要；
- 时间。

## 13. 异常处理

### 13.1 SSH 连接失败

```json
{
  "success": false,
  "error_type": "ssh_connection_failed",
  "message": "Permission denied (publickey)."
}
```

### 13.2 命令超时

```json
{
  "success": false,
  "error_type": "command_timeout",
  "message": "Command timed out after 30 seconds."
}
```

### 13.3 路径不允许

```json
{
  "success": false,
  "error_type": "path_not_allowed",
  "message": "Project path is outside allowed paths."
}
```

### 13.4 非 Git 仓库

```json
{
  "success": false,
  "error_type": "not_git_repository",
  "message": "The target path is not a Git repository."
}
```

### 13.5 分支分叉

```json
{
  "success": true,
  "state": "blocked",
  "reason": "Local and remote branches have diverged.",
  "ahead": 2,
  "behind": 1,
  "allowed_operations": {
    "push": false,
    "pull": false
  }
}
```

## 14. AI 工作方式

### 14.1 AI 输入

AI 可以读取：

- 项目信息；
- 服务器列表；
- 最新 GitStatus；
- 最新 EnvironmentSnapshot；
- OperationLog；
- 用户目标。

### 14.2 AI 输出

AI 输出：

- 分析说明；
- 风险判断；
- 建议任务；
- 配置计划；
- 是否需要人工确认。

AI 不直接输出无限制 shell 执行。

### 14.3 示例

用户：

```text
帮我看看 dev-server 为什么不能部署
```

AI 生成任务：

```json
[
  {
    "type": "check_connection",
    "ssh_host": "dev-server"
  },
  {
    "type": "detect_git",
    "ssh_host": "dev-server",
    "project_path": "/srv/projectpilot"
  },
  {
    "type": "detect_environment",
    "ssh_host": "dev-server",
    "project_path": "/srv/projectpilot"
  }
]
```

结果回来后 AI 分析：

```text
dev-server 可以连接，但项目分支落后 origin/main 2 个提交。
Docker 已安装但未运行。
建议先启动 Docker，再执行 git pull --ff-only。
```

## 15. 执行计划

先做能闭环的最小版本，再逐步放开写操作。

| 阶段 | 目标 | 必做 | 验收点 |
| --- | --- | --- | --- |
| 1. 本地闭环 | Local Executor 能连后端并上报本机状态 | 后端地址/token、`executor_id`、本地 Git/环境检测、`/executor/poll`、`/executor/tasks/{task_id}/result` | 后端能看到 Executor 在线和检测结果 |
| 2. SSH 管理 | 能从 Executor 所在机器读取 SSH Host | 扫描 `~/.ssh/config`、`ssh -G` 展开配置、连接测试、Host 别名入库、不上传私钥 | 前端能列出服务器并测试连接 |
| 3. 远程只读检测 | 能看清远程项目状态 | `check_connection`、`detect_remote_git_status`、`detect_remote_environment`、超时控制、stdout/stderr 结构化 | 后端能展示远程 Git 和环境快照 |
| 4. 安全 Git 执行 | 低风险 Git 操作可审批执行 | `git_fetch`、`git_pull_ff_only`、`git_push_safe`、dirty/diverged/conflict 阻断、审计日志 | 用户批准后执行成功，失败可解释 |
| 5. 环境配置计划 | AI 生成修复计划，Executor 只执行已批准步骤 | 命令风险分类、白名单、用户确认、中风险受控执行、高风险默认禁止 | 每一步有计划、审批、结果、审计 |
| 6. 产品化 | 变成稳定可用的执行层 | 常驻服务、开机自启、实时通知、多服务器总览、日志面板、权限分级 | 可以长期运行并支撑团队使用 |

MVP 只保留四块：

| 模块 | 范围 |
| --- | --- |
| macOS Desktop App | 填后端地址和 token、扫描 SSH config、选择 Host、测试连接、启动 Local Executor |
| 后端 | `/executor/poll`、`/executor/tasks/{task_id}/result`、创建连接/Git/环境检测任务 |
| Executor | `check_connection`、`detect_remote_git_status`、`detect_remote_environment` |
| 前端 | 服务器列表、检测按钮、Git 状态、环境状态 |

底线：

```text
只读检测优先
白名单任务优先
私钥不交给 AI Planner
危险操作不自动执行
所有操作可审计
```

## 16. 最终结论

方案可行。最终执行层就是：

```text
AI Planner 负责计划
后端负责调度、权限和审批
数据库负责历史、快照和审计
Executor 负责 SSH 连接和命令执行
```

Central Executor 是主模式，Local Executor 是补充模式。这样既能让主机 AI 统一管理服务器，又不会让 AI Planner 自由读取私钥或无限制执行 shell。
