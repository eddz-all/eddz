# ProjectPilot 成员 B 本地检测对接计划

## 1. 背景

成员 A 已经规划了后端和数据库，成员 B 负责提供真实项目和真实环境的检测能力。

根据 `member-b-integration.md`，成员 B 第一阶段应优先交付：

```python
def detect_local_git_status(project_path: str) -> dict:
    ...

def detect_local_environment(project_path: str | None = None) -> dict:
    ...
```

成员 B 不直接写数据库，不直接操作后端 API，只返回结构化 `dict`。

成员 A 后端负责：

- 调用成员 B 函数；
- 保存 `GitStatus`；
- 保存 `EnvironmentSnapshot`；
- 返回前端；
- 做综合状态和 AI 分析。

---

## 2. 当前可复用能力

当前 ProjectPilot 已经具备：

- Git 仓库识别；
- 分支、upstream、ahead、behind 检测；
- staged / unstaged / untracked / conflicted 检测；
- last commit 获取；
- Git 风险分析；
- doctor 健康检查；
- 命令执行封装。

因此第一阶段不需要重写检测逻辑，只需要新增一个后端可调用的集成层。

建议新增：

```text
projectpilot/
  integration/
    __init__.py
    member_b.py
```

---

## 3. 第一阶段函数设计

### 3.1 detect_local_git_status

签名：

```python
def detect_local_git_status(project_path: str) -> dict:
    ...
```

成功返回：

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

建议额外返回字段，方便后端后续扩展：

```json
{
  "repo_path": "/abs/path",
  "upstream": "origin/main",
  "state": "normal",
  "staged_count": 1,
  "unstaged_count": 2,
  "untracked_count": 3,
  "conflicted_count": 0,
  "is_clean": false
}
```

失败返回：

```json
{
  "success": false,
  "error_type": "not_git_repository",
  "message": "The target path is not a Git repository."
}
```

### 3.2 detect_local_environment

签名：

```python
def detect_local_environment(project_path: str | None = None) -> dict:
    ...
```

成功返回：

```json
{
  "success": true,
  "os": "Darwin",
  "architecture": "arm64",
  "python_version": "3.14.4",
  "node_version": "20.11.0",
  "docker_installed": true,
  "docker_running": false,
  "cuda_version": null,
  "disk_usage": "68%",
  "raw_data": {
    "commands": {
      "git": "2.54.0",
      "python": "3.14.4"
    }
  }
}
```

失败返回使用统一格式：

```json
{
  "success": false,
  "error_type": "unknown_error",
  "message": "..."
}
```

---

## 4. 错误格式

所有失败统一为：

```json
{
  "success": false,
  "error_type": "error_code",
  "message": "Human readable error message"
}
```

第一阶段需要支持：

- `path_not_found`;
- `not_git_repository`;
- `command_not_found`;
- `unknown_error`.

---

## 5. 实现细节

### 5.1 Git 检测

复用：

```python
inspect_repository(Path(project_path))
```

额外调用：

```bash
git log -1 --pretty=%h %s
```

remote URL 选择：

1. 如果有 upstream，取 upstream 对应 remote；
2. 否则优先取 `origin`；
3. 否则取第一个 remote；
4. 没有 remote 返回 `None`。

### 5.2 环境检测

使用 Python 标准库和安全命令：

- `platform.system()`;
- `platform.machine()`;
- `sys.version`;
- `shutil.disk_usage`;
- `shutil.which`;
- `subprocess` 执行低风险版本命令。

检测命令：

- `git --version`;
- `python3 --version`;
- `node --version`;
- `docker --version`;
- `docker info`;
- `nvidia-smi --query-gpu=driver_version --format=csv,noheader`.

命令不存在时不要失败，只填 `None` 或 `false`。

---

## 6. 测试计划

### 6.1 detect_local_git_status

覆盖：

- 非 Git 目录；
- 干净 Git 仓库；
- dirty Git 仓库；
- 有 remote/upstream 的仓库。

### 6.2 detect_local_environment

覆盖：

- 返回 success；
- 有 os / architecture / python_version；
- raw_data.commands 中至少包含 git / python；
- project_path 不存在时返回 path_not_found。

---

## 7. 验收标准

完成后应满足：

- 后端可直接 `import projectpilot.integration.member_b`；
- 可以调用 `detect_local_git_status`;
- 可以调用 `detect_local_environment`;
- 成功和失败都返回 dict；
- 不依赖 CLI；
- 不写数据库；
- 不需要后端 API；
- 测试通过；
- README 说明成员 B 第一阶段接口。

