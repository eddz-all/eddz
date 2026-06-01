# 成员 B 检测与执行模块对接说明

本文档用于说明成员 A 后端未来需要接入成员 B 的哪些函数，以及这些函数应该返回什么格式。

成员 B 的核心职责不是写数据库，也不是写前端，而是提供：

```text
真实项目和真实服务器的检测能力、远程执行能力、安全判断能力。
```

成员 A 后端会负责：

- 调用成员 B 的函数
- 保存检测结果
- 返回给前端
- 生成综合状态
- 生成 AI 分析和报告
- 记录操作日志

## 一、整体对接原则

成员 B 不直接操作数据库。

成员 B 只需要返回结构化 dict 数据。

成员 A 后端负责把这些 dict 保存到：

- GitStatus
- EnvironmentSnapshot
- OperationLog

整体流程：

```text
前端点击检测
-> A 后端接收请求
-> A 查询项目、服务器、项目路径
-> A 调用 B 的检测函数
-> B 返回结构化结果
-> A 保存数据库
-> A 返回给前端
```

## 二、B 需要提供的核心函数

## 1. 本地 Git 状态检测

### 函数建议

```python
def detect_local_git_status(project_path: str) -> dict:
    ...
```

### 作用

检测本地项目目录的 Git 状态。

### 输入

- project_path：本地项目路径

### 成功返回示例

```json
{
  "success": true,
  "branch": "main",
  "remote_url": "git@example.com:team/projectpilot.git",
  "ahead": 1,
  "behind": 0,
  "has_uncommitted_changes": true,
  "last_commit": "abc123 update backend"
}
```

### 失败返回示例

```json
{
  "success": false,
  "error_type": "not_git_repository",
  "message": "The target path is not a Git repository."
}
```

### A 后端保存位置

保存为 GitStatus。

本地检测时：

```text
server_id = null
```

## 2. 远程 Git 状态检测

### 函数建议

```python
def detect_remote_git_status(
    host: str,
    port: int,
    username: str,
    project_path: str
) -> dict:
    ...
```

### 作用

通过 SSH 连接服务器，在指定项目路径下检测 Git 状态。

### 输入

- host：服务器地址
- port：SSH 端口
- username：用户名
- project_path：项目在服务器上的路径

### 成功返回示例

```json
{
  "success": true,
  "branch": "main",
  "remote_url": "git@example.com:team/projectpilot.git",
  "ahead": 0,
  "behind": 2,
  "has_uncommitted_changes": false,
  "last_commit": "def456 fix deploy config"
}
```

### 失败返回示例

```json
{
  "success": false,
  "error_type": "ssh_connection_failed",
  "message": "Failed to connect to server."
}
```

### A 后端保存位置

保存为 GitStatus。

远程检测时：

```text
server_id = 对应服务器 id
```

## 3. 本地环境检测

### 函数建议

```python
def detect_local_environment(project_path: str | None = None) -> dict:
    ...
```

### 作用

检测本地运行环境。

### 推荐检测内容

- 操作系统
- CPU 架构
- Python 版本
- Node.js 版本
- Docker 是否安装
- Docker 是否运行
- CUDA 版本
- 磁盘占用
- Python 包版本
- Node 包版本
- 常见命令版本

### 成功返回示例

```json
{
  "success": true,
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

### A 后端保存位置

保存为 EnvironmentSnapshot。

本地检测时：

```text
server_id = null
```

## 4. 远程环境检测

### 函数建议

```python
def detect_remote_environment(
    host: str,
    port: int,
    username: str,
    project_path: str | None = None
) -> dict:
    ...
```

### 作用

通过 SSH 连接服务器，检测远程服务器环境状态。

### 成功返回示例

```json
{
  "success": true,
  "os": "Linux",
  "architecture": "x86_64",
  "python_version": "3.10.12",
  "node_version": "18.19.0",
  "docker_installed": true,
  "docker_running": false,
  "cuda_version": null,
  "disk_usage": "82%",
  "raw_data": {
    "python_packages": {
      "fastapi": "0.110.0"
    },
    "commands": {
      "git": "2.39.0",
      "docker": "24.0.0"
    }
  }
}
```

### A 后端保存位置

保存为 EnvironmentSnapshot。

远程检测时：

```text
server_id = 对应服务器 id
```

## 5. 服务器连接检测

### 函数建议

```python
def check_server_connection(
    host: str,
    port: int,
    username: str
) -> dict:
    ...
```

### 作用

检测服务器是否可以连接。

### 成功返回示例

```json
{
  "success": true,
  "connected": true,
  "message": "Connection successful",
  "latency_ms": 35
}
```

### 失败返回示例

```json
{
  "success": false,
  "connected": false,
  "error_type": "timeout",
  "message": "SSH connection timeout"
}
```

### A 后端用途

用于最终接口：

```text
POST /servers/{server_id}/check-connection
```

前端可在服务器列表页展示在线、离线或连接失败原因。

## 6. 远程命令执行

### 函数建议

```python
def run_remote_command(
    host: str,
    port: int,
    username: str,
    command: str,
    cwd: str | None = None,
    timeout: int = 30
) -> dict:
    ...
```

### 作用

通过 SSH 在远程服务器执行用户确认后的命令。

该函数主要用于 AI 配置计划执行。

### 输入

- host：服务器地址
- port：SSH 端口
- username：用户名
- command：要执行的命令
- cwd：执行目录，可选
- timeout：超时时间

### 成功返回示例

```json
{
  "success": true,
  "exit_code": 0,
  "stdout": "Docker started",
  "stderr": ""
}
```

### 失败返回示例

```json
{
  "success": false,
  "exit_code": 1,
  "stdout": "",
  "stderr": "Permission denied",
  "error_type": "permission_denied",
  "message": "Command failed due to permission error."
}
```

### A 后端用途

用于最终接口：

```text
POST /projects/{project_id}/servers/{server_id}/execute-config-plan
```

当前 A 后端是模拟执行，未来会替换为调用该函数。

## 7. 命令风险判断

### 函数建议

```python
def classify_command_risk(command: str) -> dict:
    ...
```

### 作用

判断命令风险等级。

虽然第一版配置计划由前端整体审核，但 B 仍建议提供风险判断能力，供 AI 生成计划和后端执行前校验使用。

### 返回示例

```json
{
  "risk_level": "high",
  "requires_confirmation": true,
  "allowed": false,
  "reason": "git reset --hard may discard local changes."
}
```

### 风险等级建议

低风险：

- git status
- git log
- python --version
- node --version
- docker --version

中风险：

- pip install
- npm install
- systemctl start
- git pull

高风险：

- rm -rf
- git reset --hard
- git clean -fd
- git push --force
- rebase

## 三、建议的统一错误格式

所有 B 的函数失败时，建议统一返回：

```json
{
  "success": false,
  "error_type": "error_code",
  "message": "Human readable error message"
}
```

常见 error_type 建议：

- path_not_found
- not_git_repository
- ssh_connection_failed
- command_timeout
- permission_denied
- docker_not_installed
- command_not_found
- unknown_error

## 四、A 后端会在哪里调用 B

## 1. 检测项目服务器状态

最终接口：

```text
POST /projects/{project_id}/servers/{server_id}/detect
```

A 后端内部会调用：

```python
detect_remote_git_status(...)
detect_remote_environment(...)
```

然后保存：

- GitStatus
- EnvironmentSnapshot

## 2. 批量检测项目所有服务器

最终接口：

```text
POST /projects/{project_id}/detect
```

A 后端会遍历项目绑定的服务器，对每台服务器调用 B 的检测函数。

## 3. 检测服务器连接

最终接口：

```text
POST /servers/{server_id}/check-connection
```

A 后端内部会调用：

```python
check_server_connection(...)
```

## 4. 执行 AI 配置计划

最终接口：

```text
POST /projects/{project_id}/servers/{server_id}/execute-config-plan
```

A 后端内部会调用：

```python
run_remote_command(...)
```

逐条执行用户确认后的命令。

## 五、B 第一阶段优先级

建议 B 按以下顺序交付。

### 第一阶段：本地检测

- detect_local_git_status
- detect_local_environment

目标：

先让本地项目检测跑通。

### 第二阶段：远程连接

- check_server_connection
- run_remote_command

目标：

先能稳定连接服务器并执行安全命令。

### 第三阶段：远程检测

- detect_remote_git_status
- detect_remote_environment

目标：

完成服务器项目状态检测。

### 第四阶段：安全和批量能力

- classify_command_risk
- 批量检测辅助函数
- 错误分类完善
- 超时和异常处理

## 六、A 和 B 的边界

成员 B 负责：

- 执行本地命令
- 执行远程 SSH 命令
- 解析命令输出
- 返回结构化检测结果
- 判断命令风险

成员 A 负责：

- 提供 API
- 查询项目和服务器信息
- 调用 B 的函数
- 保存检测结果
- 返回给前端
- 生成 AI 分析和报告
- 记录操作日志

一句话总结：

```text
B 负责获取真实世界的数据，A 负责管理和使用这些数据。
```
