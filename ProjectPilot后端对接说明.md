# ProjectPilot 后端对接说明

这份文档发给后端同学即可。后端不需要关心 SSH 执行细节，也不需要运行 Rust 编译环境；后端只需要实现任务下发和结果接收协议。

## 部署关系

```text
后端同学电脑
  - 运行后端服务
  - 生成 shell 任务
  - 通过 SSH 登录你的 Ubuntu，打开 TUI 审阅任务

你的 Ubuntu
  - 安装 projectpilot-tui / projectpilot-agent
  - TUI 轮询后端拿任务
  - 审阅、编辑、批准 shell
  - 在 Ubuntu 本机执行 shell
  - 把 stdout/stderr/exit_code 回传给后端
```

核心原则：shell 最终在你的 Ubuntu 本机执行，不在后端同学电脑执行。

## 后端需要实现的接口

MVP 只需要两个接口：

```text
POST /executor/poll
POST /executor/tasks/{task_id}/result
```

TUI 会用 HTTP Bearer Token 调用后端：

```http
Authorization: Bearer <token>
Content-Type: application/json
```

开发阶段可以先用 HTTP。正式环境建议放在可信内网、VPN、SSH 隧道或 HTTPS 后面。

## 1. 轮询任务

```text
POST /executor/poll
```

TUI 请求体：

```json
{
  "executor_id": "ubuntu_sys",
  "mode": "tui",
  "capabilities": [
    "run_script",
    "apply_script",
    "execute_script",
    "run_remote_script",
    "apply_remote_script",
    "execute_remote_script"
  ],
  "status": "online"
}
```

字段说明：

```text
executor_id   当前执行端 ID。建议固定，例如 ubuntu_sys。
mode          当前客户端模式，TUI 会传 tui。
capabilities 这个客户端能处理的任务类型。
status        在线状态。
```

无任务时返回：

```json
{
  "task": null
}
```

有任务时返回：

```json
{
  "task": {
    "id": "task_001",
    "type": "run_script",
    "executor_id": "ubuntu_sys",
    "project_path": "/home/hzy/project",
    "interpreter": "bash",
    "script": "set -euo pipefail\necho hello\npwd\n",
    "params": {
      "env": {},
      "args": []
    }
  }
}
```

任务字段说明：

```text
id            必填，任务唯一 ID。
type          必填，推荐用 run_script。也支持 apply_script / execute_script。
executor_id   推荐填写，指定哪台执行端可以领取任务。
project_path  必填，Ubuntu 上的绝对路径，例如 /home/hzy/project。
interpreter   bash 或 sh，默认 bash。
script        必填，要展示给审阅人并执行的 shell 内容。
params.env    可选，环境变量对象。
params.args   可选，传给 bash/sh 的参数数组。
```

建议后端只下发这些本地执行任务：

```text
run_script
apply_script
execute_script
```

旧的 remote 类型仍兼容，但当前目标拓扑下不推荐使用：

```text
run_remote_script
apply_remote_script
execute_remote_script
```

## 2. 接收执行结果

```text
POST /executor/tasks/{task_id}/result
```

TUI 执行成功后会发送类似：

```json
{
  "task_id": "task_001",
  "executor_id": "ubuntu_sys",
  "success": true,
  "error_type": null,
  "message": "Script executed successfully",
  "started_at": "1779891923401",
  "finished_at": "1779891923415",
  "duration_ms": 14,
  "result": {
    "success": true,
    "task_id": "task_001",
    "task_type": "run_script",
    "operation": "run_script",
    "execution_mode": "local",
    "ssh_auth_mode": null,
    "ssh_host": null,
    "project_path": "/home/hzy/project",
    "command": "cd /home/hzy/project && bash -s --",
    "stdout": "hello\n/home/hzy/project\n",
    "stderr": "",
    "exit_code": 0,
    "script_sha256": "final-script-sha256",
    "original_script_sha256": "original-script-sha256",
    "script_modified": false,
    "script_size": 34,
    "approved_by": "projectpilot-tui"
  }
}
```

执行失败时：

```json
{
  "task_id": "task_001",
  "executor_id": "ubuntu_sys",
  "success": false,
  "error_type": "remote_script_failed",
  "message": "Remote script failed",
  "duration_ms": 20,
  "result": {
    "success": false,
    "stdout": "",
    "stderr": "some error\n",
    "exit_code": 1
  }
}
```

审阅人拒绝任务时：

```json
{
  "task_id": "task_001",
  "executor_id": "ubuntu_sys",
  "success": false,
  "error_type": "rejected",
  "message": "Rejected by reviewer",
  "duration_ms": 0,
  "result": {
    "success": false,
    "task_id": "task_001",
    "task_type": "run_script",
    "error_type": "rejected",
    "message": "Rejected by reviewer",
    "approved_by": "projectpilot-tui"
  }
}
```

后端返回 200 JSON 即可，例如：

```json
{
  "success": true
}
```

## 后端任务状态建议

建议最少维护这些状态：

```text
queued     已创建，等待 executor 领取
running    已被某个 executor 领取
succeeded  执行成功
failed     执行失败或被拒绝
```

`/executor/poll` 返回任务时，后端应把任务从 `queued` 改成 `running`，并记录领取它的 `executor_id`。

`/executor/tasks/{task_id}/result` 收到结果时，后端应校验：

```text
task_id 存在
executor_id 与领取任务的 executor_id 一致
任务当前处于 running 状态
```

生产环境建议加：

```text
lease_until     防止 TUI 掉线后任务永久 running
attempt_count   记录重试次数
result_id       保证结果上传幂等
created_at / updated_at / started_at / finished_at
```

## 后端生成任务的示例

后端内部创建任务时，建议结构如下：

```json
{
  "id": "task_deploy_001",
  "type": "run_script",
  "status": "queued",
  "executor_id": "ubuntu_sys",
  "project_path": "/home/hzy/project",
  "interpreter": "bash",
  "script": "set -euo pipefail\ngit status --short\nnpm test\n",
  "params": {
    "env": {},
    "args": []
  },
  "created_at": "2026-05-28T12:00:00Z"
}
```

## 本地参考后端

仓库里有一个可运行的假后端：

```text
script/fake_shell_backend.py
```

启动方式：

```bash
cd /Users/eddz/work/engine
./script/fake_shell_backend.py --host 0.0.0.0 --port 8790 --token dev-token
```

它已经实现了：

```text
GET  /health
GET  /tasks
POST /send-shell
POST /executor/poll
POST /executor/tasks/{task_id}/result
```

后端同学可以直接照这个文件实现真实服务。

## 手动测试命令

从后端侧创建一个测试任务：

```bash
curl -X POST http://127.0.0.1:8790/send-shell \
  -H 'Content-Type: application/json' \
  --data '{
    "executor_id": "ubuntu_sys",
    "project_path": "/home/hzy",
    "script": "set -euo pipefail\necho HELLO_FROM_UBUNTU\nwhoami\npwd\nuname -a\n"
  }'
```

在你的 Ubuntu 上运行 TUI：

```bash
~/.local/bin/projectpilot-tui \
  --server-url http://后端同学电脑IP:8790 \
  --token dev-token \
  --executor-id ubuntu_sys \
  --execution-mode local
```

TUI 拉到任务后，审阅人可以：

```text
a  批准并在 Ubuntu 本机执行
e  编辑脚本
r  拒绝任务
q  退出，不上传结果
```

## 后端同学需要收到的文件

只需要发这两个：

```text
ProjectPilot后端对接说明.md
script/fake_shell_backend.py
```

如果他还想看完整说明，再发：

```text
README.md
```

Linux agent 安装包不是给后端实现接口用的；它是部署到你的 Ubuntu 上用的。
