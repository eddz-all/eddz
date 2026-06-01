# Dev Log 4：连接模式与执行安全接入记录

## 当前进度

本阶段完成了两个关键升级：

```text
1. 为 Server 增加 connection_mode 字段
2. 为配置计划执行接口增加安全检查，并接入成员 B 的 SSH 执行入口
```

这一步的目标是让后端能够清楚地区分：

```text
本机测试
远程 SSH 服务器
未来 Executor Agent 模式
```

同时避免 AI 生成的危险命令被直接执行。

## connection_mode 字段

当前 `Server` 增加了：

```text
connection_mode
```

允许值为：

```text
local
ssh
executor
```

含义如下：

```text
local
表示本机测试模式。后端调用成员 B 的本地检测函数，不进行远程 SSH。

ssh
表示远程 SSH 模式。后端通过成员 B 的 SSH 能力检测或执行远程服务器任务。

executor
表示未来的 Executor Agent 模式。目标服务器主动向后端拉取任务，当前暂未完整实现。
```

当前 seed 数据中：

```text
server-a -> local
server-b -> ssh
```

其中：

```text
server-a
用于本机真实检测 ProjectPilot。

server-b
用于模拟未来远程服务器。
```

## 数据库兼容

因为 SQLite 已经存在旧的 `servers` 表，而 `Base.metadata.create_all()` 不会自动给旧表新增字段，所以当前增加了轻量兼容逻辑：

```text
backend/database.py
```

启动时会检查 `servers` 表是否存在 `connection_mode` 字段。

如果不存在，则自动执行：

```sql
ALTER TABLE servers ADD COLUMN connection_mode VARCHAR NOT NULL DEFAULT 'ssh'
```

这样可以避免手动删除数据库或重建表。

## 检测逻辑变化

当前检测入口仍然是：

```text
POST /projects/{project_id}/servers/{server_id}/detect
```

但内部会根据 `server.connection_mode` 分流。

当前逻辑：

```text
local
调用成员 B 的 detect_local_git_status 和 detect_local_environment。

ssh
暂时保留 mock 检测结果，后续可接入成员 B 的远程检测函数。

executor
暂时预留。
```

因此前端接口保持不变，只是后端内部根据服务器模式选择不同实现。

## 执行接口变化

当前执行入口仍然是：

```text
POST /projects/{project_id}/servers/{server_id}/execute-config-plan
```

请求体仍然包含：

```json
{
  "confirmed": true,
  "steps": []
}
```

其中：

```text
confirmed
表示用户已经在前端手动确认执行。

steps
表示 AI 生成或前端传回来的配置步骤。
```

也就是说，最终 App 中的“确认”应该是用户在界面上手动点击确认，而不是 AI 自动确认。

## 命令安全检查

新增安全检查逻辑：

```text
backend/services/execution_service.py
```

每一条命令都会被分类：

```text
low
低风险，通常是只读命令。

medium
中风险，可能修改环境，需要用户确认。

blocked
危险命令，后端直接拦截，即使 confirmed=true 也不执行。
```

低风险示例：

```text
python3 --version
node --version
git status
docker --version
```

中风险示例：

```text
sudo apt install docker.io
pip install xxx
npm install
systemctl start docker
```

直接阻断示例：

```text
rm -rf
mkfs
dd if=
sudo apt remove
sudo apt purge
curl ... | bash
wget ... | sh
写入 /etc/ 的重定向命令
```

当前测试结果表明：

```text
rm -rf /
```

会被识别为：

```text
blocked
```

不会执行，并且会写入 OperationLog。

## B 的 SSH 执行入口

成员 B 提供的 SSH 执行能力为：

```python
from projectpilot.executor.remote import run_remote_script
```

当前后端已经接入该入口。

执行分流逻辑如下：

```text
connection_mode = local
继续模拟执行，不实际改动本机。

connection_mode = ssh
调用成员 B 的 run_remote_script，尝试通过 SSH 在远程服务器执行命令。

connection_mode = executor
暂时返回 not_executed，并提示 executor_not_implemented。
```

## SSH 的工作方式

SSH 模式不是提前保持连接，而是：

```text
每次需要执行时临时建立 SSH 连接
执行脚本
收集 stdout / stderr / exit_code
关闭连接
```

大致流程：

```text
前端确认执行
↓
后端安全检查
↓
后端调用 B 的 run_remote_script
↓
B 内部通过 SSH 连接远程服务器
↓
远程服务器执行脚本
↓
返回执行结果
↓
后端写入 OperationLog
```

## SSH 配置方式

B 当前的 SSH 执行函数主要接收一个 `host` 字符串。

因此推荐用：

```text
~/.ssh/config
```

配置 SSH Host 别名。

示例：

```sshconfig
Host projectpilot-server-b
  HostName 192.168.1.101
  User ubuntu
  Port 22
  IdentityFile ~/.ssh/id_ed25519
```

然后数据库中：

```text
server.host = projectpilot-server-b
```

B 的函数内部执行 SSH 时，就可以直接使用：

```bash
ssh projectpilot-server-b
```

并自动读取 `HostName`、`User`、`Port` 和 `IdentityFile`。

## 当前限制

当前 SSH 执行已经接入入口，但还没有真实服务器进行完整验证。

如果调用：

```text
POST /projects/1/servers/2/execute-config-plan
```

由于 `server-b` 当前是：

```text
host = 192.168.1.101
connection_mode = ssh
project_path = /srv/projectpilot
```

如果本机无法 SSH 到该地址，执行会失败。

这是预期行为。

## 当前阶段结论

本阶段完成了从“模拟执行”到“可接真实 SSH 执行”的结构升级。

当前链路为：

```text
AI 生成配置计划
↓
前端展示计划
↓
用户手动确认执行
↓
后端再次安全检查
↓
根据 connection_mode 选择执行方式
↓
local 模拟 / ssh 调 B / executor 预留
↓
执行结果写入 OperationLog
```

## 下一步建议

后续可以继续做：

```text
1. 准备一台真实可 SSH 的测试服务器
2. 在 ~/.ssh/config 中配置 Host 别名
3. 将 server-b 的 host 改成 SSH Host 别名
4. 测试低风险命令的远程执行
5. 接入 B 的远程环境检测和远程 Git 检测函数
6. 继续完善 AI 配置计划的命令安全提示词
```
