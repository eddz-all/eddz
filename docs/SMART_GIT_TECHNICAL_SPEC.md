# ProjectPilot 智能 Git 技术规格文档

> 用途：本文件用于后续开发会话直接作为 `/goal` 的技术依据。
> 范围：只覆盖智能 Git 模块，不覆盖后端 UI、桌面 App、TUI、远程部署、团队记忆和服务器管理。

## 1. 总目标

ProjectPilot 智能 Git 模块要从当前的“安全 Git CLI”升级为“Git 状态理解引擎”。

它负责：

- 读取任意 Git 仓库状态；
- 解释 working tree、staged、local commits、remote 的关系；
- 判断当前分支、远程同步和操作风险；
- 生成安全下一步建议；
- 输出结构化 JSON 给后端、Executor、桌面 App 和 TUI；
- 在用户误操作后提供恢复建议；
- 保持所有写操作默认 dry-run，只有明确批准后才执行。

它不负责：

- 后端 API 服务；
- 服务器管理；
- Executor 轮询和任务调度；
- 桌面 App UI；
- TUI UI；
- 团队记忆数据库；
- 远程 SSH 连接实现。

一句话边界：

```text
智能 Git 只负责判断和规划，不负责调度和展示；后端负责存储和审批，Executor 负责执行。
```

## 2. 当前代码基础

当前仓库已有以下能力：

```text
projectpilot git status
projectpilot git explain
projectpilot git suggest
projectpilot git report
projectpilot git diff
projectpilot git log
projectpilot git fetch
projectpilot git commit-plan
projectpilot git add-plan
projectpilot git add
projectpilot git commit
projectpilot git push
projectpilot git pull
projectpilot git switch
projectpilot git merge
projectpilot git stash
projectpilot git tag
projectpilot git revert
projectpilot git cherry-pick
projectpilot git danger-plan
projectpilot git audit
projectpilot git doctor
projectpilot git quickstart
```

关键文件：

```text
projectpilot/cli.py
projectpilot/git/inspector.py
projectpilot/git/parser.py
projectpilot/git/analyzer.py
projectpilot/git/recommender.py
projectpilot/git/commit_planner.py
projectpilot/git/operation_planner.py
projectpilot/git/safe_executor.py
projectpilot/git/audit.py
projectpilot/git/doctor.py
projectpilot/models/git_status.py
projectpilot/models/operation_plan.py
projectpilot/models/doctor.py
tests/test_git_intelligence.py
```

已有模型：

- `GitStatus`
- `GitFileChange`
- `OperationPlan`
- `OperationResult`
- `DoctorReport`
- `CommitPlan`
- `AuditEntry`

已有安全原则：

- 大多数写操作默认 dry-run；
- `--apply` 才真正执行；
- 高风险操作通过 blocked plan 暴露；
- `pull` 只允许 fast-forward；
- `push` 只允许正常 upstream 且非 diverged；
- `commit` 只提交已 staged 文件；
- 执行后写 audit。

后续实现必须复用这些能力，不能另起一套 Git 执行逻辑。

## 3. 新增命令目标

本阶段新增或增强 6 个命令：

```text
projectpilot git map
projectpilot git branches
projectpilot git sync-plan
projectpilot git recover
projectpilot git analyze
projectpilot git commit-plan v2 增强
```

优先级：

```text
P0: git map
P0: git sync-plan
P1: git branches
P1: git analyze
P2: git recover
P2: commit-plan v2
```

推荐先实现：

```text
git map -> git sync-plan -> git analyze -> git branches -> git recover -> commit-plan v2
```

原因：

- `git map` 解决 Git 状态不直观；
- `git sync-plan` 给后端和 UI 提供可直接使用的同步判断；
- `git analyze` 聚合已有和新增能力，最适合后端接入；
- `git branches` 解决分支管理混乱；
- `git recover` 解决误操作焦虑；
- `commit-plan v2` 是已有能力增强，放后面更稳。

## 4. 对外集成方式

智能 Git 模块提供三种调用方式。

### 4.1 CLI 调用

适合：

- 非 Python 后端；
- Executor；
- shell 脚本；
- 用户手动调试。

要求所有新命令支持：

```bash
--json
```

示例：

```bash
projectpilot git map /path/to/repo --json
projectpilot git sync-plan /path/to/repo --json
projectpilot git analyze /path/to/repo --include map sync-plan commit-plan --json
```

### 4.2 Python SDK 调用

适合：

- Python 后端；
- Python 测试；
- 本地集成。

建议新增：

```text
projectpilot/integration/smart_git.py
```

提供：

```python
from pathlib import Path

def analyze_repository(
    project_path: str | Path,
    analyses: list[str] | None = None,
) -> dict:
    ...
```

`analyses` 支持：

```text
status
doctor
map
branches
sync_plan
commit_plan
recover
```

默认：

```text
status, doctor, map, sync_plan, commit_plan
```

### 4.3 Executor 任务调用

适合：

- 项目目录在用户本机；
- 项目目录在远程服务器；
- 后端不能直接访问仓库路径。

推荐新增 Executor task type：

```text
smart_git_analyze
```

任务示例：

```json
{
  "id": "task_smart_git_01",
  "type": "smart_git_analyze",
  "project_id": "project_01",
  "binding_id": "binding_local_mac",
  "project_path": "/Users/eddz/work/engine",
  "analyses": ["status", "doctor", "map", "sync_plan", "commit_plan"]
}
```

Executor 行为：

1. 校验 `project_path` 在 `allowed_root` 内；
2. 调用 Python SDK 或 CLI；
3. 上传 JSON 结果给后端；
4. 不执行任何写操作。

远程仓库场景：

- 方案 A：远程服务器上部署 agent/Executor，在远程本地路径执行 `smart_git_analyze`；
- 方案 B：Central/Local Executor 通过 SSH 调用远程检测命令，再把结果转换成同一 JSON；
- 第一阶段优先支持方案 A 或本地 Executor 调用，不强行做远程 CLI 注入。

## 5. 后端连接链路

### 5.1 只分析不执行

```text
Frontend/Desktop
  -> Backend: request project analysis
  -> Backend: create smart_git_analyze task
  -> Executor: poll task
  -> Executor: run projectpilot git analyze <path> --json
  -> Executor: submit result
  -> Backend: save snapshots/reports
  -> Frontend/Desktop: display map/sync/commit suggestions
```

### 5.2 需要执行 Git 操作

```text
Frontend/Desktop
  -> Backend: request operation suggestion
  -> Smart Git: generate OperationPlan
  -> Backend: save plan
  -> Frontend/Desktop: user approves plan
  -> Backend: create apply_git_operation task
  -> Executor: validate expected_command
  -> Executor: execute
  -> Executor: submit result
  -> Backend: save audit/result
```

关键要求：

- 智能 Git 生成 `OperationPlan`；
- 后端保存计划；
- 用户批准；
- Executor 收到 `approved: true` 和完整审批元数据；
- Executor 校验 `approval_expires_at` 和 `expected_command`；
- 执行结果写 audit。

智能 Git 不直接向后端发 HTTP 请求。

## 6. 统一返回格式

所有新命令 JSON 顶层应尽量遵循同一风格。

### 6.1 成功格式

```json
{
  "success": true,
  "schema_version": "smart-git.v1",
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "upstream": "origin/main",
  "commit": "abc123",
  "risk": "medium",
  "state": "normal",
  "reports": {},
  "operation_plans": [],
  "blocked_operations": [],
  "next_steps": [],
  "warnings": []
}
```

### 6.2 失败格式

```json
{
  "success": false,
  "schema_version": "smart-git.v1",
  "error_type": "not_git_repository",
  "message": "The target path is not a Git repository.",
  "repo_path": null
}
```

推荐错误类型：

```text
not_git_repository
path_not_found
git_not_installed
git_command_failed
unsupported_analysis
unknown_error
```

### 6.3 文本输出规则

文本输出用于人读，JSON 输出用于机器读。

规则：

- 后端和 Executor 只依赖 JSON；
- 文本输出可以是中英文，但字段名和 JSON key 必须稳定；
- 文本输出不要作为后端解析对象；
- 新命令必须先保证 JSON，再优化文本体验。

## 7. `git map` 技术规格

### 7.1 命令

```bash
projectpilot git map [path] [--json]
```

### 7.2 模块文件

新增：

```text
projectpilot/git/state_map.py
projectpilot/models/state_map.py
```

### 7.3 模型建议

```python
from dataclasses import asdict, dataclass, field

@dataclass(frozen=True)
class StateMapFile:
    path: str
    status: str
    area: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LocalCommitSummary:
    ahead: int
    commits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RemoteSummary:
    has_upstream: bool
    upstream: str | None
    behind: int
    diverged: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GitStateMap:
    repo_path: str
    branch: str | None
    upstream: str | None
    commit: str | None
    state: str
    risk: str
    working_tree: list[StateMapFile] = field(default_factory=list)
    staged: list[StateMapFile] = field(default_factory=list)
    conflicted: list[StateMapFile] = field(default_factory=list)
    untracked: list[StateMapFile] = field(default_factory=list)
    local_commits: LocalCommitSummary | None = None
    remote: RemoteSummary | None = None
    next_steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        ...
```

可以先用简单 dict 实现，但长期建议使用 dataclass，保持现有模型风格。

### 7.4 构建函数

```python
def build_state_map(path: Path) -> GitStateMap:
    status = inspect_repository(path)
    ...
```

输入：

- 本地 repo path；
- 复用 `inspect_repository`。

输出：

- `GitStateMap`。

### 7.5 状态区域定义

```text
working_tree: tracked 文件中 worktree_status 非 "." 或 " "
staged: tracked 文件中 index_status 非 "." 或 " "
untracked: status 中的 untracked_files
conflicted: status 中的 conflicted_files
local_commits: ahead > 0 时展示本地未推送提交摘要
remote: upstream、behind、diverged 状态
```

### 7.6 risk 规则

```text
low:
  clean + upstream normal

medium:
  dirty
  no upstream
  ahead only
  behind only

high:
  conflicted
  diverged
  rebase/merge/cherry-pick/revert state
```

### 7.7 next_steps 规则

示例：

```text
no upstream -> "Set an upstream before push."
dirty + no staged -> "Review working tree changes and stage related files."
staged -> "Review commit plan before committing."
ahead -> "Push local commits when ready."
behind + clean -> "Fast-forward pull is available."
diverged -> "Fetch and choose merge or rebase before pushing."
conflict -> "Resolve conflicts, stage files, then continue the current operation."
```

### 7.8 JSON 示例

```json
{
  "success": true,
  "schema_version": "smart-git.v1",
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "upstream": null,
  "commit": "abc123",
  "risk": "medium",
  "state": "normal",
  "reports": {
    "map": {
      "working_tree": [
        {
          "path": "README.md",
          "status": "M",
          "area": "working_tree"
        }
      ],
      "staged": [],
      "untracked": [
        {
          "path": "docs/SMART_GIT_TECHNICAL_SPEC.md",
          "status": "??",
          "area": "untracked"
        }
      ],
      "conflicted": [],
      "local_commits": {
        "ahead": 0,
        "commits": []
      },
      "remote": {
        "has_upstream": false,
        "upstream": null,
        "behind": 0,
        "diverged": false
      },
      "next_steps": [
        "Review working tree changes.",
        "Set an upstream before pushing."
      ]
    }
  },
  "operation_plans": [],
  "blocked_operations": [],
  "next_steps": [
    "Review working tree changes.",
    "Set an upstream before pushing."
  ],
  "warnings": []
}
```

### 7.9 CLI 文本输出示例

```text
Repository: /Users/eddz/work/engine
Branch: main
Upstream: none
Risk: medium

Working Tree
  M README.md

Staged
  empty

Untracked
  ?? docs/SMART_GIT_TECHNICAL_SPEC.md

Local Commits
  no upstream configured

Remote
  no upstream configured

Next Steps
  1. Review working tree changes.
  2. Set an upstream before pushing.
```

## 8. `git sync-plan` 技术规格

### 8.1 命令

```bash
projectpilot git sync-plan [path] [--json]
```

### 8.2 模块文件

新增：

```text
projectpilot/git/sync_planner.py
projectpilot/models/sync_plan.py
```

### 8.3 核心判断

输入来自 `GitStatus`：

```text
branch
upstream
ahead
behind
is_clean
state
conflicted_files
```

同步状态：

```text
no_upstream
up_to_date
ahead
behind
diverged
dirty
conflict
operation_in_progress
```

判断规则：

| 状态 | can_push | can_pull_ff_only | recommended_action |
| --- | --- | --- | --- |
| no upstream | false | false | set_upstream |
| clean + ahead > 0 + behind = 0 | true | false | push |
| clean + ahead = 0 + behind > 0 | false | true | pull_ff_only |
| clean + ahead > 0 + behind > 0 | false | false | choose_merge_or_rebase |
| dirty + behind > 0 | false | false | commit_or_stash_before_pull |
| dirty + ahead > 0 | false by default | false | commit_or_stash_before_push |
| conflict | false | false | resolve_conflicts |
| merge/rebase/cherry-pick state | false | false | continue_or_abort_operation |

### 8.4 OperationPlan 复用

`sync-plan` 不直接执行，但可以生成可审批计划：

- push 计划：复用 `build_push_operation_plan`
- pull 计划：复用 `build_pull_operation_plan`
- fetch 计划：可以返回低风险 command `["git", "fetch"]`

### 8.5 JSON 示例

```json
{
  "success": true,
  "schema_version": "smart-git.v1",
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "upstream": "origin/main",
  "risk": "high",
  "reports": {
    "sync_plan": {
      "sync_state": "diverged",
      "working_tree_state": "dirty",
      "ahead": 1,
      "behind": 2,
      "can_push": false,
      "can_pull_ff_only": false,
      "recommended_action": "commit_or_stash_then_choose_merge_or_rebase",
      "explanation": "Local and remote both contain unique commits, and the working tree has uncommitted changes."
    }
  },
  "operation_plans": [],
  "blocked_operations": [
    {
      "operation": "push",
      "reason": "branch_is_diverged"
    },
    {
      "operation": "pull",
      "reason": "working_tree_is_dirty_or_not_fast_forward"
    }
  ],
  "next_steps": [
    "Commit or stash local changes.",
    "Fetch remote changes.",
    "Choose merge or rebase after reviewing remote commits."
  ],
  "warnings": []
}
```

## 9. `git branches` 技术规格

### 9.1 命令

```bash
projectpilot git branches [path] [--json]
```

### 9.2 模块文件

新增：

```text
projectpilot/git/branch_lifecycle.py
projectpilot/models/branch_lifecycle.py
```

### 9.3 Git 命令

建议使用：

```bash
git branch --format=%(refname:short)|%(upstream:short)|%(committerdate:iso8601)|%(objectname:short)|%(subject)
git branch -r --format=%(refname:short)|%(committerdate:iso8601)|%(objectname:short)|%(subject)
git branch --merged
git for-each-ref refs/heads refs/remotes --format=...
```

第一版可以简单实现：

- 本地分支；
- 当前分支；
- upstream；
- 是否 merged；
- 是否缺 upstream；
- 最后提交摘要；
- 可删除建议。

### 9.4 分支状态

```text
active
current
merged
no_upstream
remote_gone
stale
protected
unknown
```

第一版 `remote_gone` 可以通过 upstream 不存在判断，后续增强。

### 9.5 safe_to_delete 规则

```text
false:
  current branch
  protected branches: main, master, develop, release/*
  branch has unpushed commits
  branch not merged

true:
  non-current
  merged into current/default branch
  no unique local commits
```

第一版不要执行删除，只给建议。

### 9.6 JSON 示例

```json
{
  "success": true,
  "schema_version": "smart-git.v1",
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "reports": {
    "branches": {
      "current_branch": "main",
      "branches": [
        {
          "name": "main",
          "is_current": true,
          "upstream": null,
          "ahead": 0,
          "behind": 0,
          "status": "no_upstream",
          "safe_to_delete": false,
          "recommendation": "set_upstream_before_push"
        }
      ],
      "summary": {
        "total_local": 1,
        "without_upstream": 1,
        "merged": 0,
        "safe_to_delete": 0
      }
    }
  },
  "operation_plans": [],
  "blocked_operations": [],
  "next_steps": [
    "Set upstream for main before pushing."
  ],
  "warnings": []
}
```

## 10. `git recover` 技术规格

### 10.1 命令

```bash
projectpilot git recover [path] [--json] [--limit 10]
```

第一版只解释，不执行。

### 10.2 模块文件

新增：

```text
projectpilot/git/recovery.py
projectpilot/models/recovery.py
```

### 10.3 Git 命令

```bash
git reflog --date=iso -n <limit>
git status --porcelain=v2 --branch
git rev-parse --short HEAD
git log -1 --pretty=%h %s
```

### 10.4 恢复场景

第一版提供固定建议：

```text
undo_last_commit_keep_changes:
  git reset --soft HEAD~1
  risk: medium
  execute: false

undo_last_commit_unstage_changes:
  git reset --mixed HEAD~1
  risk: medium
  execute: false

return_to_previous_head:
  git reset --hard <reflog_target>
  risk: high
  execute: false

inspect_reflog_target:
  git show <sha>
  risk: read-only
  execute: false
```

高风险命令只作为说明，不进入 `allowed` 执行计划。

### 10.5 JSON 示例

```json
{
  "success": true,
  "schema_version": "smart-git.v1",
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "reports": {
    "recover": {
      "head": "abc123",
      "reflog": [
        {
          "selector": "HEAD@{0}",
          "commit": "abc123",
          "action": "commit",
          "message": "commit: update docs"
        }
      ],
      "recovery_options": [
        {
          "scenario": "undo_last_commit_keep_changes",
          "command": ["git", "reset", "--soft", "HEAD~1"],
          "risk": "medium",
          "auto_execute": false,
          "warning": "This rewrites local history but keeps changes staged."
        }
      ]
    }
  },
  "operation_plans": [],
  "blocked_operations": [
    {
      "operation": "reset-hard",
      "reason": "high_risk_recovery_requires_manual_confirmation"
    }
  ],
  "next_steps": [
    "Inspect reflog entries before choosing a recovery command."
  ],
  "warnings": []
}
```

## 11. `git analyze` 技术规格

### 11.1 命令

```bash
projectpilot git analyze [path] [--include status doctor map sync-plan branches commit-plan recover] [--json]
```

如果未指定 `--include`，默认：

```text
status doctor map sync-plan commit-plan
```

### 11.2 模块文件

新增：

```text
projectpilot/integration/smart_git.py
```

可选新增：

```text
projectpilot/git/analyze.py
projectpilot/models/smart_git.py
```

### 11.3 聚合逻辑

伪代码：

```python
def analyze_repository(project_path, analyses=None):
    analyses = analyses or ["status", "doctor", "map", "sync_plan", "commit_plan"]
    payload = base_payload(project_path)
    if "status" in analyses:
        payload["reports"]["status"] = inspect_repository(path).to_dict()
    if "doctor" in analyses:
        payload["reports"]["doctor"] = build_doctor_report(path).to_dict()
    if "map" in analyses:
        payload["reports"]["map"] = build_state_map(path).to_dict()
    if "sync_plan" in analyses:
        payload["reports"]["sync_plan"] = build_sync_plan(path).to_dict()
    if "branches" in analyses:
        payload["reports"]["branches"] = build_branch_lifecycle_report(path).to_dict()
    if "commit_plan" in analyses:
        payload["reports"]["commit_plan"] = build_commit_plan(path).to_dict()
    if "recover" in analyses:
        payload["reports"]["recover"] = build_recovery_report(path).to_dict()
    return payload
```

### 11.4 JSON 示例

```json
{
  "success": true,
  "schema_version": "smart-git.v1",
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "upstream": null,
  "commit": "abc123",
  "risk": "medium",
  "state": "normal",
  "reports": {
    "status": {},
    "doctor": {},
    "map": {},
    "sync_plan": {},
    "commit_plan": {}
  },
  "operation_plans": [],
  "blocked_operations": [],
  "next_steps": [],
  "warnings": []
}
```

### 11.5 后端推荐调用

```bash
projectpilot git analyze /path/to/repo \
  --include status doctor map sync-plan commit-plan \
  --json
```

后端应保存：

- `repo_path`
- `branch`
- `upstream`
- `commit`
- `risk`
- `state`
- `reports.status`
- `reports.doctor`
- `reports.map`
- `reports.sync_plan`
- `reports.commit_plan`
- `operation_plans`
- `blocked_operations`
- `next_steps`

## 12. `commit-plan v2` 技术规格

现有 `commit-plan` 保持兼容。

新增字段建议：

```json
{
  "quality": {
    "status": "needs_review",
    "warnings": [],
    "suggested_messages": [],
    "suggested_commits": []
  },
  "guards": {
    "sensitive_files": [],
    "large_files": [],
    "ignored_candidates": []
  }
}
```

第一版增强点：

- 检查 staged 文件是否为空；
- 检查 staged 文件是否包含明显敏感文件名：
  - `.env`
  - `.env.local`
  - `id_rsa`
  - `id_ed25519`
  - `.pem`
  - `.key`
- 检查大文件，默认阈值可先设为 10MB；
- 对 mixed docs/code changes 给出拆分建议；
- 生成 suggested message。

敏感文件第一版只做文件名和扩展名规则，不做内容扫描。

未来再做内容规则：

```text
API_KEY=
SECRET=
TOKEN=
password=
-----BEGIN PRIVATE KEY-----
```

## 13. CLI 修改点

文件：

```text
projectpilot/cli.py
```

新增 parser：

```python
map_command = git_subparsers.add_parser("map", help="Show Git state map.")
add_path_argument(map_command)
map_command.add_argument("--json", action="store_true")
map_command.set_defaults(handler=handle_git_map)

branches_command = git_subparsers.add_parser("branches", help="Explain branch relationships.")
add_path_argument(branches_command)
branches_command.add_argument("--json", action="store_true")
branches_command.set_defaults(handler=handle_git_branches)

sync_plan_command = git_subparsers.add_parser("sync-plan", help="Plan safe remote sync.")
add_path_argument(sync_plan_command)
sync_plan_command.add_argument("--json", action="store_true")
sync_plan_command.set_defaults(handler=handle_git_sync_plan)

recover_command = git_subparsers.add_parser("recover", help="Explain recovery options from reflog.")
add_path_argument(recover_command)
recover_command.add_argument("--limit", type=int, default=10)
recover_command.add_argument("--json", action="store_true")
recover_command.set_defaults(handler=handle_git_recover)

analyze_command = git_subparsers.add_parser("analyze", help="Run smart Git analysis bundle.")
add_path_argument(analyze_command)
analyze_command.add_argument("--include", nargs="+", default=[])
analyze_command.add_argument("--json", action="store_true")
analyze_command.set_defaults(handler=handle_git_analyze)
```

新增 handlers：

```python
def handle_git_map(args): ...
def handle_git_branches(args): ...
def handle_git_sync_plan(args): ...
def handle_git_recover(args): ...
def handle_git_analyze(args): ...
```

打印函数：

```python
def print_state_map(report): ...
def print_branch_lifecycle(report): ...
def print_sync_plan(report): ...
def print_recovery_report(report): ...
def print_smart_git_analysis(report): ...
```

JSON 打印复用：

```python
print_json(payload)
```

如果当前 `cli.py` 已有 `print_json` 风格，沿用现有实现。

## 14. Executor 修改点

当前文件：

```text
projectpilot/executor/client.py
```

当前 `EXECUTOR_CAPABILITIES` 增加：

```python
"smart_git_analyze"
```

`execute_task` 增加：

```python
if task_type == "smart_git_analyze":
    return execute_smart_git_analyze(task, config)
```

新增函数：

```python
def execute_smart_git_analyze(task: dict[str, Any], config: ExecutorConfig) -> dict[str, Any]:
    project_path = task.get("project_path")
    if not project_path:
        return failure("missing_project_path", "Task is missing project_path.")
    try:
        resolved_path = resolve_allowed_project_path(str(project_path), config.allowed_root)
    except PathNotAllowedError as exc:
        return failure("path_not_allowed", str(exc))

    analyses = task.get("analyses")
    if analyses is not None and not isinstance(analyses, list):
        return failure("invalid_analyses", "analyses must be a string array.")

    from projectpilot.integration.smart_git import analyze_repository
    return analyze_repository(resolved_path, analyses=[str(item) for item in analyses] if analyses else None)
```

注意：

- `smart_git_analyze` 是 read-only；
- 不需要 `approved: true`；
- 必须受 `allowed_root` 限制；
- 不能执行写操作；
- 结果直接交给后端存储。

后端存储层可以把 `smart_git_analyze` 结果作为 generic report，也可以拆成多张表。

## 15. Backend 存储建议

后端最低可保存一张通用分析结果表：

```text
SmartGitAnalysis
  id
  project_id
  binding_id
  executor_id
  repo_path
  branch
  upstream
  commit
  risk
  state
  reports_json
  operation_plans_json
  blocked_operations_json
  next_steps_json
  warnings_json
  captured_at
```

如果后端已有 `GitStatus`、`EnvironmentSnapshot`，也可以拆分保存：

```text
GitStatus <- reports.status
DoctorReport <- reports.doctor
GitStateMap <- reports.map
SyncPlan <- reports.sync_plan
CommitPlan <- reports.commit_plan
RecoveryReport <- reports.recover
```

第一阶段推荐保存完整 JSON，避免过早拆表。

## 16. 测试计划

### 16.1 新增测试文件

建议新增：

```text
tests/test_git_state_map.py
tests/test_git_sync_plan.py
tests/test_git_branch_lifecycle.py
tests/test_git_recovery.py
tests/test_smart_git_integration.py
```

也可以先合并到 `tests/test_git_intelligence.py`，但长期建议拆开。

### 16.2 `git map` 测试

场景：

- clean repo；
- unstaged change；
- staged change；
- untracked file；
- ahead branch；
- behind branch；
- diverged branch；
- conflict state；
- no upstream。

断言：

- JSON `success` 为 true；
- `reports.map` 存在；
- 文件进入正确区域；
- risk 正确；
- next_steps 合理。

### 16.3 `git sync-plan` 测试

场景：

- no upstream；
- clean and up-to-date；
- clean and ahead；
- clean and behind；
- clean and diverged；
- dirty and behind；
- conflict。

断言：

- `can_push`；
- `can_pull_ff_only`；
- `recommended_action`；
- `blocked_operations`。

### 16.4 `git branches` 测试

场景：

- one branch no upstream；
- branch with upstream；
- merged branch；
- current branch should not be safe to delete；
- protected branch should not be safe to delete。

### 16.5 `git recover` 测试

场景：

- repo with commits；
- reflog output exists；
- limit works；
- recovery options include soft/mixed suggestions；
- hard reset suggestion is blocked/high risk。

### 16.6 `git analyze` 测试

场景：

- default include；
- custom include；
- unsupported include returns clean error；
- non-git path returns failure JSON；
- CLI `--json` can be parsed。

### 16.7 Executor 测试

新增到 `tests/test_executor.py`：

- `smart_git_analyze` accepts allowed path；
- rejects outside allowed root；
- rejects invalid analyses；
- returns reports；
- does not require approved；
- does not execute write operation。

## 17. 验收标准

### 17.1 功能验收

必须通过：

```bash
projectpilot git map . --json
projectpilot git sync-plan . --json
projectpilot git analyze . --json
```

输出必须是合法 JSON，并包含：

```text
success
schema_version
repo_path
branch
risk
reports
next_steps
```

### 17.2 后端验收

后端可以通过 CLI 或 SDK 获得完整 JSON：

```bash
projectpilot git analyze /path/to/repo --json
```

并能展示：

- 当前分支；
- upstream；
- risk；
- Git 四区图；
- 同步建议；
- blocked operations；
- next steps。

### 17.3 Executor 验收

Executor 支持任务：

```json
{
  "type": "smart_git_analyze",
  "project_path": ".",
  "analyses": ["map", "sync_plan"]
}
```

并返回：

```json
{
  "success": true,
  "reports": {
    "map": {},
    "sync_plan": {}
  }
}
```

### 17.4 测试验收

必须运行：

```bash
.venv/bin/python -m unittest discover -s tests -p 'test*.py' -v
```

通过后才算完成。

如果项目环境装了 pytest，也可运行：

```bash
.venv/bin/python -m pytest -q
```

当前环境中可能没有 pytest，因此标准库 unittest 是必要验收方式。

## 18. 安全要求

智能 Git 模块必须遵守：

- 新增分析命令全部 read-only；
- `recover` 第一版不能执行 reset；
- `branches` 第一版不能执行 delete branch；
- `sync-plan` 只能生成计划，不能直接 pull/push；
- 所有写操作继续走已有 safe executor；
- 高风险命令只能出现在 blocked/recovery suggestion 中；
- 后端和 Executor 不解析文本输出；
- JSON schema key 尽量保持稳定；
- 不引入网络依赖；
- 不在智能 Git 模块中调用 AI API。

第一阶段用规则引擎实现，不依赖大模型。

未来如接入 AI，也只能基于结构化 JSON 生成解释或摘要，不能直接生成可执行 shell。

## 19. 实现阶段拆分

### 阶段 1：`git map`

文件：

```text
projectpilot/models/state_map.py
projectpilot/git/state_map.py
projectpilot/cli.py
tests/test_git_state_map.py
```

交付：

- `projectpilot git map .`
- `projectpilot git map . --json`
- 文本输出；
- JSON 输出；
- 测试。

### 阶段 2：`git sync-plan`

文件：

```text
projectpilot/models/sync_plan.py
projectpilot/git/sync_planner.py
projectpilot/cli.py
tests/test_git_sync_plan.py
```

交付：

- `projectpilot git sync-plan .`
- `projectpilot git sync-plan . --json`
- 输出 can_push / can_pull_ff_only；
- blocked_operations；
- 测试。

### 阶段 3：`git analyze` 和 SDK

文件：

```text
projectpilot/integration/smart_git.py
projectpilot/cli.py
tests/test_smart_git_integration.py
```

交付：

- `analyze_repository(path, analyses=None)`；
- `projectpilot git analyze . --json`；
- `--include` 参数；
- 统一 JSON 顶层；
- 测试。

### 阶段 4：Executor task 接入

文件：

```text
projectpilot/executor/client.py
tests/test_executor.py
```

交付：

- `smart_git_analyze` capability；
- task execution；
- allowed_root 校验；
- 测试。

### 阶段 5：`git branches`

文件：

```text
projectpilot/models/branch_lifecycle.py
projectpilot/git/branch_lifecycle.py
projectpilot/cli.py
tests/test_git_branch_lifecycle.py
```

交付：

- branch report；
- upstream 状态；
- safe_to_delete 建议；
- 测试。

### 阶段 6：`git recover`

文件：

```text
projectpilot/models/recovery.py
projectpilot/git/recovery.py
projectpilot/cli.py
tests/test_git_recovery.py
```

交付：

- reflog 读取；
- recovery options；
- 只解释不执行；
- 测试。

### 阶段 7：`commit-plan v2`

文件：

```text
projectpilot/git/commit_planner.py
projectpilot/models/commit_plan.py
tests/test_git_intelligence.py
```

交付：

- suggested messages；
- sensitive filename guard；
- large file guard；
- suggested commits；
- 兼容现有输出。

## 20. 代码风格要求

沿用当前项目风格：

- Python 标准库优先；
- 不新增不必要依赖；
- dataclass 模型；
- `to_dict()` 输出；
- CLI 支持文本和 JSON；
- Git 命令通过 `projectpilot.utils.shell.run_git`；
- 不用字符串拼接执行 shell；
- 测试使用 `unittest`；
- 每个模块职责单一。

错误处理：

- Python API 返回 failure dict 或抛现有明确异常要统一；
- CLI 顶层已有异常捕获；
- 对后端友好的 integration API 应返回 `success: false`，不要让异常直接泄露。

## 21. 与现有 OperationPlan 的关系

新模块不要重复定义执行计划。

已有：

```python
OperationPlan(
    operation: str,
    repo_path: str,
    risk: str,
    allowed: bool,
    requires_apply: bool,
    command: list[str],
    reason: str,
    blockers: list[str],
    warnings: list[str],
    rollback_commands: list[list[str]],
)
```

`sync-plan` 中允许直接嵌入现有 OperationPlan：

```json
{
  "operation": "pull",
  "repo_path": "...",
  "risk": "medium",
  "allowed": true,
  "requires_apply": true,
  "command": ["git", "pull", "--ff-only"],
  "blockers": []
}
```

恢复建议不要复用 `OperationPlan` 表示可执行计划，因为第一版不执行恢复命令。可以使用 `recovery_options`，并标记：

```json
"auto_execute": false
```

## 22. 后端同学对接说明

后端不要直接解析普通文本输出。

后端接入优先级：

1. 优先调用 Executor `smart_git_analyze` task；
2. 如果后端能访问项目路径，可直接调用 Python SDK；
3. 如果不是 Python 后端，可调用 CLI `projectpilot git analyze <path> --json`。

后端需要存：

```text
project_id
binding_id
executor_id
repo_path
branch
upstream
commit
risk
state
reports_json
operation_plans_json
blocked_operations_json
next_steps_json
warnings_json
captured_at
```

后端发执行任务时：

- 从智能 Git 的 `operation_plans` 中取 command；
- 用户批准后，生成 `apply_git_operation`；
- 传入 `expected_command`；
- Executor 必须逐字匹配 command。

## 23. 桌面 App / UI 展示建议

UI 可以基于 `git analyze` 展示：

```text
Header:
  repo_path, branch, upstream, risk

State Map:
  working_tree, staged, untracked, local_commits, remote

Sync Card:
  ahead, behind, sync_state, recommended_action

Next Steps:
  next_steps

Operation Plans:
  allowed plans, blocked operations

Warnings:
  warnings
```

UI 不需要自己判断 Git 状态。

## 24. 后续 AI 接入边界

第一阶段不接 AI API。

未来接入 AI 时：

AI 输入：

```json
{
  "status": {},
  "map": {},
  "sync_plan": {},
  "commit_plan": {},
  "team_policy": {},
  "recent_audit": []
}
```

AI 输出：

```json
{
  "plain_language_summary": "...",
  "recommended_next_step": "...",
  "risk_explanation": "...",
  "questions_for_user": []
}
```

AI 不能输出自由 shell 给 Executor。

如果 AI 建议操作，也必须转成已有 OperationPlan，并经过规则校验。

## 25. 可复制 `/goal` 提示

后续在新会话中可以直接使用下面的 `/goal`：

```text
/goal
请基于 /Users/eddz/work/engine/docs/SMART_GIT_TECHNICAL_SPEC.md 实现 ProjectPilot 智能 Git 模块第一阶段。

目标：
1. 新增 projectpilot git map，支持文本输出和 --json。
2. 新增 projectpilot git sync-plan，支持文本输出和 --json。
3. 新增 projectpilot git analyze，聚合 status、doctor、map、sync-plan、commit-plan，支持 --include 和 --json。
4. 新增 Python SDK：projectpilot.integration.smart_git.analyze_repository。
5. 接入 Executor read-only task：smart_git_analyze。
6. 补充 unittest 测试，确保 .venv/bin/python -m unittest discover -s tests -p 'test*.py' -v 通过。

实现约束：
- 复用现有 inspect_repository、build_doctor_report、build_commit_plan、OperationPlan 和 run_git。
- 不新增不必要依赖。
- 所有新增分析命令必须 read-only。
- 不实现 reset、delete branch、force push 等写操作。
- 后端/Executor 只依赖 JSON，不解析文本输出。
- 保持现有命令兼容。

优先顺序：
1. git map
2. git sync-plan
3. integration smart_git analyze_repository
4. git analyze CLI
5. Executor smart_git_analyze task
6. 测试与文档微调
```

如果一次性实现过大，可以把目标拆成：

```text
/goal
请基于 /Users/eddz/work/engine/docs/SMART_GIT_TECHNICAL_SPEC.md 只实现阶段 1：git map，包括模型、构建函数、CLI、JSON 输出和测试。
```

或：

```text
/goal
请基于 /Users/eddz/work/engine/docs/SMART_GIT_TECHNICAL_SPEC.md 实现后端对接最小闭环：integration.smart_git.analyze_repository、projectpilot git analyze --json、Executor smart_git_analyze task 和测试。
```

## 26. 完成定义

本技术规格对应的第一阶段完成定义：

```text
用户或后端可以对任意 Git 仓库运行：

projectpilot git analyze <repo> --json

并获得稳定结构：

- 当前状态；
- Git 四区图；
- 同步建议；
- commit-plan；
- next steps；
- blocked operations。

Executor 可以通过 smart_git_analyze 任务在 allowed root 内执行同样分析。
所有新增能力均为 read-only，测试全部通过。
```
