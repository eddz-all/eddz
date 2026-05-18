# ProjectPilot 智能 Git 下一阶段开发计划

## 1. 当前状态

当前已经完成智能 Git MVP。

已支持命令：

```bash
projectpilot git status
projectpilot git explain
projectpilot git suggest
projectpilot git report
projectpilot git diff
projectpilot git log
projectpilot git fetch
projectpilot git commit-plan
```

当前能力特点：

- 以只读分析为主；
- `fetch` 是唯一低风险执行命令；
- 不会自动 `add`、`commit`、`pull`、`push`；
- 已能分析工作区变更并生成提交计划；
- 已有基础测试覆盖。

下一阶段目标是：**从智能分析进入受控执行**。

---

## 2. 下一阶段目标

实现一套安全、可解释、可确认的 Git 操作流程。

核心原则：

- 默认先分析，再执行；
- 所有会改变仓库状态的操作必须显示计划；
- 中风险操作需要用户确认；
- 高风险操作暂不执行，只提示风险；
- 执行后重新检测状态；
- 每次执行都能被记录和复盘。

---

## 3. 功能优先级

### 3.1 第一优先级：确认机制

先实现统一确认机制，再接真实操作。

需要支持：

```bash
projectpilot git add --apply
projectpilot git commit --apply
projectpilot git push --apply
```

不带 `--apply` 时只展示计划，不执行。

示例：

```bash
projectpilot git commit
```

输出：

```text
This command would create a commit.
Suggested message: Add intelligent commit planning
Files:
- projectpilot/git/commit_planner.py
- tests/test_git_intelligence.py

Run again with --apply to execute.
```

真正执行：

```bash
projectpilot git commit --apply
```

这样可以避免用户误触。

---

## 4. 新命令设计

### 4.1 git add-plan

先做文件暂存计划，不直接执行。

```bash
projectpilot git add-plan
```

输出：

- 建议 add 的文件；
- 需要复核的文件；
- 建议排除的文件；
- 对应原因；
- 推荐命令。

这个命令可以复用当前 `commit-plan` 的分类逻辑。

### 4.2 git add

受控执行 `git add`。

```bash
projectpilot git add
projectpilot git add --apply
projectpilot git add --include README.md projectpilot/cli.py --apply
```

规则：

- 默认只展示计划；
- `--apply` 才执行；
- 默认只 add `Suggested include` 文件；
- `Needs review` 文件需要用户显式传入 `--include`；
- `Suggested exclude` 文件默认禁止 add，除非显式 `--force-include`。

### 4.3 git commit

受控执行 `git commit`。

```bash
projectpilot git commit
projectpilot git commit --message "Add intelligent commit planning" --apply
```

规则：

- 如果没有 staged 文件，不执行；
- 如果有 unstaged/untracked 文件，提示是否需要先 add；
- 不自动 add 文件；
- 默认使用智能生成的 commit message；
- 用户可用 `--message` 覆盖；
- `--apply` 才真正执行。

### 4.4 git push

受控执行 `git push`。

```bash
projectpilot git push
projectpilot git push --apply
```

规则：

- 没有 upstream 时，只建议 `git push -u origin HEAD`，不自动执行；
- 工作区不干净时可以 push，但要提示风险；
- 分支 diverged 时禁止 push；
- 默认禁止 force push；
- 不支持 `--force`，后续阶段再考虑。

### 4.5 git pull

受控执行 `git pull --ff-only`。

```bash
projectpilot git pull
projectpilot git pull --apply
```

规则：

- 只允许 fast-forward pull；
- 工作区不干净时不执行；
- 分支 diverged 时不执行；
- 没有 upstream 时不执行；
- 执行前建议先 `fetch`；
- 执行后重新生成状态摘要。

---

## 5. 风险分级升级

### 5.1 低风险，可直接执行或弱确认

- `status`;
- `explain`;
- `suggest`;
- `report`;
- `diff`;
- `log`;
- `fetch`.

### 5.2 中风险，需要 `--apply`

- `add`;
- `commit`;
- `push`;
- `pull --ff-only`;
- `stash`.

### 5.3 高风险，下一阶段仍不执行

- `reset --hard`;
- `clean -fd`;
- `push --force`;
- `rebase`;
- 删除分支；
- 修改远程地址。

高风险操作只输出：

```text
ProjectPilot will not run this operation yet.
Reason: this can permanently discard or rewrite work.
```

---

## 6. 模块设计调整

建议新增：

```text
projectpilot/
  git/
    operation_planner.py
    safe_executor.py
    audit.py
  models/
    operation_plan.py
    audit_log.py
```

### 6.1 operation_planner

负责生成操作计划。

例如：

- AddPlan；
- CommitPlan；
- PushPlan；
- PullPlan。

计划必须包含：

- 操作类型；
- 风险等级；
- 是否需要确认；
- 是否允许执行；
- 阻止原因；
- 将要执行的命令；
- 执行前状态摘要。

### 6.2 safe_executor

负责真正执行 Git 命令。

要求：

- 只执行白名单命令；
- 禁止 shell 拼接；
- 所有命令参数必须数组化；
- 执行前验证 plan 是否允许；
- 执行后重新 inspect；
- 返回执行结果和新状态。

### 6.3 audit

记录受控执行历史。

建议写入：

```text
.projectpilot/audit/git-operations.jsonl
```

每行记录：

```json
{
  "timestamp": "2026-05-18T15:00:00",
  "operation": "commit",
  "risk": "medium",
  "command": ["git", "commit", "-m", "message"],
  "success": true,
  "before_commit": "abc123",
  "after_commit": "def456"
}
```

---

## 7. 数据结构草案

### 7.1 OperationPlan

```python
class OperationPlan:
    operation: str
    risk: str
    allowed: bool
    requires_apply: bool
    command: list[str]
    reason: str
    blockers: list[str]
    warnings: list[str]
```

### 7.2 OperationResult

```python
class OperationResult:
    operation: str
    success: bool
    stdout: str
    stderr: str
    before_status: GitStatus
    after_status: GitStatus
```

### 7.3 AuditEntry

```python
class AuditEntry:
    timestamp: str
    operation: str
    risk: str
    command: list[str]
    success: bool
    before_commit: str | None
    after_commit: str | None
```

---

## 8. 推荐开发顺序

### 阶段 A：计划系统

1. 新增 `OperationPlan` 数据结构；
2. 实现 `add-plan`；
3. 实现 `commit` 的 dry-run 计划；
4. 实现 `push` 的 dry-run 计划；
5. 实现 `pull` 的 dry-run 计划。

### 阶段 B：受控执行

1. 实现统一 `--apply` 参数；
2. 实现 `git add --apply`；
3. 实现 `git commit --apply`；
4. 实现 `git push --apply`；
5. 实现 `git pull --apply`。

### 阶段 C：审计记录

1. 新增 `.projectpilot/audit/`；
2. 每次执行写入 JSONL；
3. 新增命令：

```bash
projectpilot git audit
```

用于查看最近操作。

### 阶段 D：体验优化

1. 更好的提交信息生成；
2. 更好的文件分组；
3. 对配置文件、lock 文件、生成文件做更准确判断；
4. 输出更清晰的 next step。

---

## 9. 下一步最小实现建议

最小下一步不要一次做完 add / commit / push / pull。

建议先做：

```bash
projectpilot git add-plan
projectpilot git add --apply
```

原因：

- add 是中风险里最容易控制的；
- 可以复用 `commit-plan`；
- 可以验证 `--apply` 机制；
- 可以为 commit 做铺垫。

完成后再做：

```bash
projectpilot git commit
projectpilot git commit --apply
```

这样智能 Git 的流程就会变成：

```text
status
↓
commit-plan
↓
add-plan
↓
add --apply
↓
commit --apply
```

这个闭环完成后，ProjectPilot 就不只是“看懂 Git”，而是开始能“安全地辅助完成 Git 工作流”。

---

## 10. 验收标准

下一阶段完成后，应满足：

- 不带 `--apply` 的命令不会修改仓库；
- `add --apply` 只暂存建议 include 的文件；
- `commit --apply` 只在存在 staged 文件时执行；
- `pull --apply` 只允许 fast-forward；
- `push --apply` 会阻止 diverged 分支；
- 所有执行操作都有测试；
- 所有执行操作后重新输出状态；
- 高风险命令不会被执行；
- 操作记录可以追溯。

