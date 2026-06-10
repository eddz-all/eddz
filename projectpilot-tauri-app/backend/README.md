# ProjectPilot Backend

这是从 `ProjectPilot.zip` 整合进桌面 App 工程的 FastAPI 后端。

## 启动

```bash
cd backend
pip install -r requirements.txt
python seed.py
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

`python seed.py` rebuilds `/Users/eddz/work/projectpilot-demo` and registers
those local repositories in the backend. The generated repositories are intended
for Git Workspace screenshots and demos.

健康检查：

```text
http://127.0.0.1:8000/health
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 当前已实现

- 项目 CRUD
- 服务器 CRUD
- 项目和服务器绑定
- Git 状态快照
- 环境快照
- 项目/服务器综合状态
- 服务器连接模式 `local` / `ssh` / `executor`
- 服务器连接检测
- 项目检测触发接口
- 操作日志
- mock AI 环境分析
- mock AI 配置计划
- Markdown 报告生成
- 配置计划安全检查
- `ssh` 模式优先调用成员 B 兼容函数，未提供模块时回退到系统 OpenSSH

## 下一步后端补齐

- 登录认证
- 团队记忆
- 真实 AI 接入

## 成员 B 模块接入

后端会优先尝试导入以下模块名：

- `services.member_b_runner`
- `member_b_runner`
- `member_b`
- `member_b_integration`

如果模块里提供这些函数，后端会直接调用：

- `check_server_connection`
- `detect_remote_git_status`
- `detect_remote_environment`
- `run_remote_command` 或 `run_remote_script`
- `classify_command_risk`

如果没有找到成员 B 模块，`ssh` 模式会使用系统 OpenSSH 客户端执行远程命令。
