# ProjectPilot 智能 Git Doctor 开发计划

## 1. 背景

当前 ProjectPilot 智能 Git 已经具备：

- Git 状态识别；
- 自然语言解释；
- 操作建议；
- Markdown 报告；
- commit-plan；
- 受控 `add / commit / push / pull`；
- `--apply` 审计记录；
- `git audit` 历史查询。

下一步需要一个统一入口，把这些能力汇总成“当前仓库是否健康、下一步该做什么”的判断。

这个入口暂定为：

```bash
projectpilot git doctor
```

---

## 2. 阶段目标

实现一个 Git 健康检查命令。

它要回答：

- 当前仓库整体是否健康；
- 是否存在阻塞问题；
- 是否存在需要注意的问题；
- 当前最推荐的下一步是什么；
- 最近一次 ProjectPilot 操作是什么；
- 当前仓库是否适合执行 add / commit / push / pull。

---

## 3. 新命令设计

### 3.1 基础命令

```bash
projectpilot git doctor
```

默认检查当前目录。

### 3.2 指定仓库

```bash
projectpilot git doctor /path/to/repo
```

### 3.3 JSON 输出

```bash
projectpilot git doctor --json
```

用于后续 Web UI、多仓库扫描、多服务器状态汇总。

---

## 4. 输出示例

### 4.1 健康仓库

```text
Git Doctor

Health: healthy
Risk: low
Branch: main
Upstream: origin/main
Working tree: clean
Ahead/Behind: +0 / -0

Findings:
- Working tree is clean.
- Branch is aligned with upstream.
- Recent ProjectPilot operation: pull success at 2026-05-18T16:30:00+08:00.

Recommended next step:
- No Git action needed right now.
```

### 4.2 需要注意的仓库

```text
Git Doctor

Health: attention
Risk: medium
Branch: main
Upstream: not configured
Working tree: clean
Ahead/Behind: +0 / -0

Findings:
- Current branch has no upstream branch configured.
- No remote is configured.

Recommended next step:
- Configure a remote and upstream before using push or pull.
```

### 4.3 阻塞状态

```text
Git Doctor

Health: blocked
Risk: high
Branch: main
Upstream: origin/main
Working tree: dirty
Ahead/Behind: +1 / -1

Findings:
- Local and upstream branches have diverged.
- Working tree has unstaged changes.

Recommended next step:
- Inspect history and resolve divergence before push or pull.
```

---

## 5. 健康等级

### 5.1 healthy

满足：

- 仓库状态 normal；
- 无冲突；
- 工作区干净；
- 有 upstream；
- ahead = 0；
- behind = 0；
- 非 diverged；
- risk = low。

### 5.2 attention

存在中风险问题，但没有阻塞状态。

例如：

- 没有 remote；
- 没有 upstream；
- 有未提交修改；
- 有 untracked 文件；
- ahead > 0；
- behind > 0；
- 最近没有审计记录。

### 5.3 blocked

存在高风险或必须先处理的问题。

例如：

- merge / rebase / cherry-pick / revert 中间状态；
- 冲突文件；
- ahead > 0 且 behind > 0；
- 工作区不干净且需要 pull；
- push / pull 被当前状态阻止。

---

## 6. Doctor 数据结构

新增：

```text
projectpilot/
  git/
    doctor.py
  models/
    doctor.py
```

### 6.1 DoctorReport

```python
class DoctorReport:
    repo_path: str
    health: str
    risk: str
    branch: str | None
    upstream: str | None
    is_clean: bool
    ahead: int
    behind: int
    findings: list[str]
    recommended_next_step: str
    last_audit_operation: str | None
    can_add: bool
    can_commit: bool
    can_push: bool
    can_pull: bool
```

### 6.2 Operation readiness

Doctor 不直接执行操作，但需要告诉用户当前是否适合操作：

```text
add: allowed / blocked
commit: allowed / blocked
push: allowed / blocked
pull: allowed / blocked
```

这些判断可以复用：

- `build_add_plan`;
- `build_commit_operation_plan`;
- `build_push_operation_plan`;
- `build_pull_operation_plan`.

---

## 7. Doctor 逻辑

### 7.1 输入数据

Doctor 聚合：

- `inspect_repository`;
- `analyze_status`;
- `build_recommendations`;
- `read_audit_entries(limit=1)`;
- `build_add_plan`;
- `build_commit_operation_plan`;
- `build_push_operation_plan`;
- `build_pull_operation_plan`.

### 7.2 Findings 规则

基础 findings：

- 非 Git 仓库：直接报错；
- 无 remote；
- 无 upstream；
- 工作区干净 / 不干净；
- staged 文件数量；
- unstaged 文件数量；
- untracked 文件数量；
- conflicted 文件数量；
- ahead / behind / diverged；
- 当前 state；
- 最近一次审计操作。

### 7.3 Recommended next step 规则

优先级：

1. 如果有冲突：解决冲突；
2. 如果处于 merge/rebase：完成或中止当前操作；
3. 如果 diverged：先查看历史，暂不 push/pull；
4. 如果工作区有修改：运行 commit-plan；
5. 如果 behind 且干净：运行 pull；
6. 如果 ahead 且不 behind：运行 push；
7. 如果无 upstream：配置 upstream；
8. 如果健康：无需操作。

---

## 8. JSON 输出格式

示例：

```json
{
  "repo_path": "/Users/eddz/work/engine",
  "health": "attention",
  "risk": "medium",
  "branch": "main",
  "upstream": null,
  "is_clean": true,
  "ahead": 0,
  "behind": 0,
  "findings": [
    "Current branch has no upstream branch configured.",
    "No remote is configured."
  ],
  "recommended_next_step": "Configure a remote and upstream before using push or pull.",
  "last_audit_operation": "commit",
  "can_add": false,
  "can_commit": false,
  "can_push": false,
  "can_pull": false
}
```

---

## 9. 测试计划

需要覆盖：

### 9.1 健康状态

- 有 upstream；
- 工作区干净；
- ahead/behind 都为 0；
- health = healthy。

### 9.2 注意状态

- 无 upstream；
- 工作区有未提交修改；
- 有 untracked 文件；
- ahead > 0；
- behind > 0。

### 9.3 阻塞状态

- diverged；
- conflict；
- merge/rebase 状态；
- pull 被 dirty worktree 阻止。

### 9.4 审计集成

- 有 audit 记录时能显示最近操作；
- 无 audit 记录时提示没有历史操作。

### 9.5 CLI

- `git doctor` 输出人类可读报告；
- `git doctor --json` 输出结构化 JSON。

---

## 10. 验收标准

完成后应满足：

- `projectpilot git doctor` 可运行；
- 可以输出 health / risk / findings / next step；
- 可以显示 add / commit / push / pull readiness；
- 可以读取最近一次 audit；
- JSON 输出可用；
- 测试覆盖 healthy / attention / blocked；
- 当前仓库运行 doctor 时能说明：

```text
Health: attention
Reason: no upstream configured
Working tree: clean
```

---

## 11. 推荐开发顺序

```text
新增 DoctorReport 数据结构
↓
新增 doctor.py 聚合状态
↓
实现 health 判断
↓
实现 findings 和 recommended_next_step
↓
实现 CLI 输出
↓
实现 JSON 输出
↓
补测试
↓
用 ProjectPilot 自己 add/commit
```

完成后，ProjectPilot 智能 Git 会有一个非常自然的日常入口：

```bash
projectpilot git doctor
```

用户可以先运行 doctor，再根据建议进入 add / commit / push / pull / audit。

