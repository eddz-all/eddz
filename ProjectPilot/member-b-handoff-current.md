# ProjectPilot 成员 B 当前对接说明

本文档用于同步成员 A 后端当前状态，以及成员 B 后续需要配合的检测与执行能力。

## 1. 当前整体状态

成员 A 后端已经完成以下主线能力：

```text
项目管理
服务器管理
项目-服务器绑定
Git 状态快照
环境快照
AI 环境分析
AI 配置计划生成
执行前安全检查
操作日志
```

当前已经接入成员 B 的本地检测能力：

```python
from projectpilot.integration.member_b import (
    detect_local_git_status,
    detect_local_environment,
)
```

后端当前接入位置：

```text
backend/services/detection_service.py
```

当前已验证：

```text
POST /projects/1/servers/1/detect
```

可以调用成员 B 的本地 Git 检测和本地环境检测，并将结果写入：

```text
GitStatus
EnvironmentSnapshot
OperationLog
```

## 2. 成员 A 与成员 B 的职责边界

成员 A 负责：

```text
FastAPI 接口
数据库读写
AI 调用
状态聚合
操作日志
前端接口稳定性
```

成员 B 负责：

```text
本地/远程 Git 检测
本地/远程环境检测
远程命令或脚本执行
底层执行安全能力
```

重要约定：

```text
B 不直接写数据库
B 不直接调用前端接口
B 返回结构化 dict
A 负责保存 dict 结果并返回给前端
```

## 3. connection_mode 设计

当前 `Server` 表新增：

```text
connection_mode
```

允许值：

```text
local
ssh
executor
```

含义：

```text
local
本机测试模式。A 后端调用 B 的本地检测函数。

ssh
远程 SSH 模式。A 后端调用 B 的远程检测或远程执行函数。

executor
未来 Agent/Executor 模式。目标机器主动拉取任务，目前后端只预留，未完整实现。
```

当前 seed 中：

```text
server-a -> local
server-b -> ssh
```

## 4. 当前已经接入的 B 函数

### 4.1 本地 Git 检测

当前 A 后端调用：

```python
detect_local_git_status(project_path)
```

期望成功返回字段：

```json
{
  "success": true,
  "branch": "main",
  "remote_url": null,
  "ahead": 0,
  "behind": 0,
  "has_uncommitted_changes": false,
  "last_commit": "fca15b6 Initial ProjectPilot backend",
  "raw_data": {}
}
```

A 后端会保存为：

```text
GitStatus
```

### 4.2 本地环境检测

当前 A 后端调用：

```python
detect_local_environment(project_path)
```

期望成功返回字段：

```json
{
  "success": true,
  "os": "Linux",
  "architecture": "x86_64",
  "python_version": "3.11.6",
  "node_version": "24.15.0",
  "docker_installed": true,
  "docker_running": false,
  "cuda_version": "581.42",
  "disk_usage": "3%",
  "raw_data": {}
}
```

A 后端会保存为：

```text
EnvironmentSnapshot
```

## 5. 当前尚未完整接入的 B 能力

当前后端已经预留并部分接入以下方向，但还没有完成真实远程验证。

### 5.1 远程连接检测

B 已提供方向：

```python
from projectpilot.executor.remote import check_connection
```

后续 A 希望在：

```text
POST /servers/{server_id}/check-connection
```

中接入真实 SSH 连接检测。

建议返回：

```json
{
  "success": true,
  "connected": true,
  "host": "projectpilot-server-b",
  "latency_ms": 35,
  "message": "Connection successful",
  "stdout": "",
  "stderr": "",
  "exit_code": 0
}
```

### 5.2 远程 Git 检测

B 已提供方向：

```python
from projectpilot.executor.remote import detect_remote_git_status
```

后续 A 希望在：

```text
POST /projects/{project_id}/servers/{server_id}/detect
```

且：

```text
server.connection_mode = ssh
```

时调用该能力。

建议函数形态：

```python
detect_remote_git_status(host, project_path, timeout=20, auth_mode="key")
```

其中：

```text
host
建议使用 ~/.ssh/config 中的 Host 别名。

project_path
目标服务器上的项目绝对路径。
```

### 5.3 远程环境检测

B 已提供方向：

```python
from projectpilot.executor.remote import detect_remote_environment
```

后续 A 希望在：

```text
POST /projects/{project_id}/servers/{server_id}/detect
```

且：

```text
server.connection_mode = ssh
```

时调用该能力。

建议函数形态：

```python
detect_remote_environment(host, project_path, timeout=20, auth_mode="key")
```

返回字段需要尽量与本地环境检测保持一致：

```text
os
architecture
python_version
node_version
docker_installed
docker_running
cuda_version
disk_usage
raw_data
```

### 5.4 远程脚本执行

B 已提供：

```python
from projectpilot.executor.remote import run_remote_script
```

当前 A 后端已在：

```text
backend/services/execution_service.py
```

中接入该入口。

当前执行分流：

```text
local -> 模拟执行
ssh -> 调用 run_remote_script
executor -> 暂时 not_executed
```

当前对应接口：

```text
POST /projects/{project_id}/servers/{server_id}/execute-config-plan
```

请求体：

```json
{
  "confirmed": true,
  "steps": [
    {
      "order": 1,
      "title": "查看 Python 版本",
      "command": "python3 --version",
      "risk_level": "low"
    }
  ]
}
```

## 6. 执行安全规则

A 后端已经增加命令安全检查。

命令会被分为：

```text
low
medium
blocked
```

blocked 命令即使用户 `confirmed=true` 也不会执行。

当前会拦截：

```text
rm -rf
mkfs
dd if=
shutdown
reboot
sudo apt remove
sudo apt purge
curl ... | bash
wget ... | sh
写入 /etc/ 的重定向
```

因此 B 的执行函数可以假设：

```text
A 会先做第一层命令安全检查
```

但仍建议 B 保留自己的底层安全限制，例如：

```text
路径必须是绝对路径
host 必须合法
脚本 hash 校验
执行超时
stdout/stderr/exit_code 完整返回
```

## 7. SSH 配置约定

当前 B 的远程函数主要接收：

```text
host: str
```

因此建议使用 SSH Host 别名，而不是直接在代码里拼接用户名、端口和密钥。

推荐在 A 后端所在机器配置：

```text
~/.ssh/config
```

示例：

```sshconfig
Host projectpilot-server-b
  HostName 192.168.1.101
  User ubuntu
  Port 22
  IdentityFile ~/.ssh/id_ed25519
```

数据库中：

```text
server.host = projectpilot-server-b
server.connection_mode = ssh
```

B 的执行函数内部相当于使用：

```bash
ssh projectpilot-server-b
```

由 SSH 自动读取用户名、端口和密钥配置。

## 8. 当前前端相关接口

成员 B 不需要直接调用这些接口，但需要知道 A 后端最终会通过这些接口触发 B 的能力。

### 检测项目状态

```text
POST /projects/{project_id}/servers/{server_id}/detect
```

内部会触发：

```text
Git 检测
环境检测
保存数据库
写操作日志
```

### 检查服务器连接

```text
POST /servers/{server_id}/check-connection
```

未来可接入 B 的 `check_connection`。

### 执行配置计划

```text
POST /projects/{project_id}/servers/{server_id}/execute-config-plan
```

内部会触发：

```text
安全检查
根据 connection_mode 分流
local 模拟 / ssh 调 B / executor 预留
写操作日志
```

## 9. 当前验证结果

当前已经验证：

```text
server-a connection_mode = local
ProjectPilot + server-a 绑定路径 = /home/huancheng/AutoEnv/ProjectPilot
```

调用：

```text
POST /projects/1/servers/1/detect
```

返回中已经出现：

```text
git_result.source = member_b_local
environment_result.source = member_b_local
```

说明本地检测对接成功。

## 10. 希望 B 下一步协助确认

请成员 B 重点确认以下问题：

```text
1. detect_remote_git_status 是否可以直接用于 A 后端 ssh 模式？
2. detect_remote_environment 是否可以直接用于 A 后端 ssh 模式？
3. check_connection 是否推荐替换 A 当前 mock 连接检测？
4. run_remote_script 当前是否要求 host 必须是 ~/.ssh/config Host 别名？
5. run_remote_script 是否支持 username/port 直接传参，还是必须走 SSH config？
6. 执行失败时，错误字段 error_type/message/stdout/stderr/exit_code 是否稳定？
7. executor 模式是否需要 A 后端实现任务队列接口，还是暂时不做？
```

## 11. 对接优先级建议

建议下一步按以下顺序继续：

```text
1. 接入 check_connection 的真实 SSH 检测
2. 接入 detect_remote_git_status
3. 接入 detect_remote_environment
4. 用一台真实 SSH 测试服务器验证低风险命令执行
5. 再考虑 executor agent 模式
```

当前不要优先做 executor，因为它需要额外的任务队列、轮询、结果回传和前端状态展示，复杂度更高。
