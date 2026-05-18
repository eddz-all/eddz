# ProjectPilot 智能 Git 审计记录开发计划

## 1. 背景

当前 ProjectPilot 智能 Git 已经完成受控执行闭环：

```bash
projectpilot git add --apply
projectpilot git commit --apply
projectpilot git push --apply
projectpilot git pull --apply
```

这些命令已经具备：

- dry-run 默认行为；
- `--apply` 才执行；
- 操作前生成计划；
- 执行后重新检测状态；
- 高风险场景阻止执行。

下一步需要补上 **操作审计记录**。

原因：

- 用户需要知道 ProjectPilot 实际执行过什么；
- 团队场景需要追踪谁在什么时候改过 Git 状态；
- 出问题时需要能回看操作历史；
- 后续团队共享记忆和多服务器管理都依赖审计基础。

---

## 2. 阶段目标

实现一套轻量、可追溯、可查询的 Git 操作审计系统。

核心目标：

- 所有 `--apply` 操作自动写审计日志；
- 审计记录使用 JSONL，便于追加和解析；
- 支持查看最近操作；
- 支持按操作类型过滤；
- 不记录敏感大内容，只记录必要元信息；
- 审计记录本身默认不建议提交到 Git。

---

## 3. 审计文件位置

建议写入：

```text
.projectpilot/audit/git-operations.jsonl
```

目录结构：

```text
.projectpilot/
  audit/
    git-operations.jsonl
  reports/
    ...
```

`.gitignore` 中应继续忽略：

```gitignore
.projectpilot/reports/
.projectpilot/audit/
```

---

## 4. 审计记录格式

每次执行一个 `--apply` 操作，追加一行 JSON。

示例：

```json
{
  "timestamp": "2026-05-18T16:30:00+08:00",
  "operation": "commit",
  "risk": "medium",
  "command": ["git", "commit", "-m", "Add controlled git commit workflow"],
  "success": true,
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "before_commit": "abc123",
  "after_commit": "def456",
  "before_clean": false,
  "after_clean": true,
  "stdout_summary": "[main def456] Add controlled git commit workflow",
  "stderr_summary": ""
}
```

### 字段说明

- `timestamp`：操作时间，使用本地时区 ISO 格式；
- `operation`：`add` / `commit` / `push` / `pull`；
- `risk`：操作风险等级；
- `command`：实际执行的 Git 命令数组；
- `success`：是否成功；
- `repo_path`：仓库根目录；
- `branch`：执行后的当前分支；
- `before_commit`：执行前 commit；
- `after_commit`：执行后 commit；
- `before_clean`：执行前工作区是否干净；
- `after_clean`：执行后工作区是否干净；
- `stdout_summary`：stdout 简要内容；
- `stderr_summary`：stderr 简要内容。

---

## 5. 新命令设计

### 5.1 查看最近审计记录

```bash
projectpilot git audit
```

默认显示最近 20 条记录。

输出示例：

```text
Recent Git operations:

1. 2026-05-18 16:30:00 commit success
   branch: main
   command: git commit -m "Add controlled git commit workflow"
   before: abc123
   after: def456

2. 2026-05-18 16:28:10 add success
   branch: main
   command: git add -- README.md projectpilot/cli.py
   before: abc123
   after: abc123
```

### 5.2 控制条数

```bash
projectpilot git audit --limit 10
```

### 5.3 按操作过滤

```bash
projectpilot git audit --operation commit
projectpilot git audit --operation push
```

### 5.4 JSON 输出

```bash
projectpilot git audit --json
```

---

## 6. 模块设计

建议新增：

```text
projectpilot/
  git/
    audit.py
  models/
    audit_log.py
```

### 6.1 models/audit_log.py

定义：

```python
class AuditEntry:
    timestamp: str
    operation: str
    risk: str
    command: list[str]
    success: bool
    repo_path: str
    branch: str | None
    before_commit: str | None
    after_commit: str | None
    before_clean: bool
    after_clean: bool
    stdout_summary: str
    stderr_summary: str
```

### 6.2 git/audit.py

负责：

- 生成审计记录；
- 写入 JSONL；
- 读取 JSONL；
- 过滤记录；
- 限制返回数量；
- 压缩 stdout/stderr 摘要长度。

函数建议：

```python
def write_audit_entry(result: OperationResult) -> AuditEntry
def read_audit_entries(repo_path: Path, limit: int = 20, operation: str | None = None) -> list[AuditEntry]
def audit_log_path(repo_path: Path) -> Path
```

---

## 7. 执行流程调整

当前受控执行流程：

```text
生成 OperationPlan
↓
执行 Git 命令
↓
重新 inspect
↓
返回 OperationResult
```

加入审计后：

```text
生成 OperationPlan
↓
执行 Git 命令
↓
重新 inspect
↓
生成 OperationResult
↓
写入 AuditEntry
↓
返回 OperationResult
```

需要覆盖的命令：

- `add --apply`;
- `commit --apply`;
- `push --apply`;
- `pull --apply`.

---

## 8. 安全与隐私规则

审计日志不应该记录：

- 完整 diff；
- 文件内容；
- commit message 以外的敏感正文；
- 环境变量；
- token；
- 远程 URL 中的凭据。

需要注意：

- `command` 里可能包含远程 URL，后续如果支持 `remote` 操作，需要脱敏；
- 当前 `add/commit/push/pull` 命令风险较低；
- stdout/stderr 只保留前 N 个字符，例如 500 字符；
- `.projectpilot/audit/` 默认不提交。

---

## 9. 测试计划

需要新增测试：

### 9.1 写入审计

- 执行 `run_add` 后生成一条 audit；
- 执行 `run_commit` 后生成一条 audit；
- 执行 `run_push` 后生成一条 audit；
- 执行 `run_pull` 后生成一条 audit。

### 9.2 读取审计

- 可以读取最近记录；
- `limit` 生效；
- `operation` 过滤生效；
- 没有审计文件时返回空列表。

### 9.3 CLI audit

- `projectpilot git audit` 能显示记录；
- `projectpilot git audit --json` 输出 JSON；
- `projectpilot git audit --operation commit` 能过滤。

### 9.4 不记录 dry-run

- `git add` 不带 `--apply` 不写入审计；
- `git commit` 不带 `--apply` 不写入审计；
- `git push` 不带 `--apply` 不写入审计；
- `git pull` 不带 `--apply` 不写入审计。

---

## 10. 验收标准

完成后应满足：

- 所有 `--apply` 操作都会写入 `.projectpilot/audit/git-operations.jsonl`；
- dry-run 不写审计；
- 审计记录包含 before / after commit；
- 审计记录包含 before / after clean 状态；
- `projectpilot git audit` 可以查看最近操作；
- `--limit` 可控制数量；
- `--operation` 可过滤操作；
- `--json` 可输出机器可读结果；
- `.projectpilot/audit/` 不会被 commit-plan 建议提交；
- 测试覆盖核心路径。

---

## 11. 推荐开发顺序

```text
新增 AuditEntry 数据结构
↓
新增 audit.py 写入/读取 JSONL
↓
让 safe_executor 在成功或失败后写 audit
↓
新增 projectpilot git audit 命令
↓
补测试
↓
用 ProjectPilot 自己 add/commit 本轮改动
```

完成后，ProjectPilot 智能 Git 的闭环将变成：

```text
检查状态
↓
生成计划
↓
用户确认 --apply
↓
执行 Git 操作
↓
记录审计日志
↓
再次检查状态
↓
支持历史回看
```

