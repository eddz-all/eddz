# ProjectPilot 智能 Git 模块开发方案

## 1. 模块定位

智能 Git 模块是 ProjectPilot 的核心大脑之一，负责理解 Git 仓库状态、解释风险、生成安全操作计划，并为 CLI、后端、桌面 App、Executor 和 TUI 提供结构化输出。

本模块不负责服务器管理、Executor、桌面 App、TUI、团队记忆、后端任务调度和远程部署。这些由其他模块或队友负责。

一句话定位：

```text
智能 Git 模块 = Git 状态理解引擎 + 安全操作规划器 + 恢复建议中心
```

它要解决的不是“把 Git 命令包一层”，而是帮助普通开发者理解：

```text
我现在在哪个分支？
我改了什么？
这些改动在哪一层？
本地和远程差了什么？
下一步最安全的操作是什么？
如果做错了怎么恢复？
```

## 2. 当前基础

当前项目已经具备智能 Git v0.1 的底座。

已有能力：

- `projectpilot git status .`：结构化 Git 状态采集；
- `projectpilot git doctor .`：仓库健康诊断；
- `projectpilot git suggest .`：下一步建议；
- `projectpilot git commit-plan .`：提交计划；
- `projectpilot git add .`：安全暂存计划和执行；
- `projectpilot git commit .`：安全提交计划和执行；
- `projectpilot git pull .`：安全 fast-forward pull；
- `projectpilot git push .`：安全 push；
- `projectpilot git merge .`：安全 fast-forward merge；
- `projectpilot git stash .`：安全 stash；
- `projectpilot git tag .`：安全 tag；
- `projectpilot git revert .`：安全 revert；
- `projectpilot git cherry-pick .`：安全 cherry-pick；
- `projectpilot git danger-plan .`：高风险操作阻止计划；
- `projectpilot git audit .`：操作审计记录；
- 多数命令支持 `--json`；
- 已有测试覆盖，当前测试通过。

当前阶段的问题不是“能不能做”，而是需要把它从：

```text
安全 Git CLI
```

升级成：

```text
Git 状态理解引擎
```

## 3. 核心目标

智能 Git 模块第一阶段的目标是形成一个完整闭环：

```text
读取仓库状态
  ↓
解释 Git 当前状态
  ↓
判断风险等级
  ↓
生成下一步操作建议
  ↓
输出结构化计划
  ↓
用户确认后安全执行
  ↓
写入审计记录
  ↓
必要时提供恢复建议
```

这个闭环成立后，智能 Git 模块就能作为 ProjectPilot 的核心创新能力发布。

## 4. 必须解决的 Git 痛点

普通开发者使用 Git 的困扰主要集中在十类问题：

1. 分支管理混乱；
2. 合并冲突难理解；
3. `merge`、`rebase`、`cherry-pick` 分不清；
4. 提交历史不干净；
5. 误操作后不知道如何恢复；
6. 暂存区概念不直观；
7. 远程同步问题；
8. 团队协作流程不统一；
9. 大文件和敏感信息误提交；
10. GUI 和命令行之间割裂。

这些问题可以归纳为一句话：

```text
Git 最大的困难不是命令多，而是状态和历史不直观。
```

所以智能 Git 模块的设计重点应该围绕两个核心概念：

```text
状态：working tree / staged / local commits / remote
历史：branch / commit / merge / rebase / reflog
```

## 5. 第一阶段核心能力

第一阶段建议重点完成五个能力。

### 5.1 Git 状态四区图

命令建议：

```bash
projectpilot git map .
```

目标：

把 Git 状态解释成四个区域：

```text
Working Tree -> Staged -> Local Commits -> Remote
```

用户应该能一眼看懂：

- 哪些文件还没有 `git add`；
- 哪些文件已经 staged；
- 哪些提交只在本地；
- 远程是否领先；
- 本地是否领先；
- 当前分支是否 diverged；
- 当前是否存在 conflict。

示例输出：

```text
Repository: /Users/eddz/work/engine
Branch: main
Upstream: none
Risk: medium

Working Tree
  M README.md
  ?? docs/SMART_GIT_MODULE_PLAN.md

Staged
  empty

Local Commits
  no upstream configured

Remote
  no upstream configured

Next Steps
  1. Review unstaged changes.
  2. Stage related files with projectpilot git add.
  3. Create a commit after reviewing the commit plan.
```

JSON 输出建议：

```json
{
  "repo_path": "/Users/eddz/work/engine",
  "branch": "main",
  "upstream": null,
  "risk": "medium",
  "zones": {
    "working_tree": [],
    "staged": [],
    "local_commits": {
      "ahead": 0,
      "commits": []
    },
    "remote": {
      "behind": 0,
      "diverged": false,
      "has_upstream": false
    }
  },
  "next_steps": []
}
```

价值：

这是智能 Git 模块最重要的创新点。它把 Git 的抽象状态变成开发者能直接理解的状态地图。

### 5.2 分支关系诊断

命令建议：

```bash
projectpilot git branches .
```

目标：

解决分支太多、upstream 关系不清、本地和远程分支混乱的问题。

需要展示：

- 当前分支；
- 本地分支列表；
- 远程分支列表；
- 每个本地分支是否有 upstream；
- 本地领先和远程领先数量；
- 哪些分支已经合并；
- 哪些本地分支远程已删除；
- 哪些分支长期未更新；
- 哪些分支可以安全删除；
- 当前是否适合新建分支。

示例输出：

```text
Current Branch
  main
  upstream: none
  status: local only

Branches
  main
    upstream: none
    status: active
    recommendation: set upstream before push

  feature/git-map
    upstream: origin/feature/git-map
    ahead: 2
    behind: 0
    status: active
    recommendation: ready for PR or push

  fix/old-login-bug
    upstream: origin/fix/old-login-bug
    status: merged
    recommendation: can delete local branch
```

JSON 输出建议：

```json
{
  "current_branch": "main",
  "branches": [
    {
      "name": "main",
      "upstream": null,
      "ahead": 0,
      "behind": 0,
      "status": "active",
      "recommendation": "set_upstream_before_push",
      "safe_to_delete": false
    }
  ],
  "summary": {
    "total_local": 1,
    "without_upstream": 1,
    "merged": 0,
    "safe_to_delete": 0
  }
}
```

价值：

让用户知道哪些分支还能用、哪些能删、哪些有远程关系风险。

### 5.3 远程同步决策器

命令建议：

```bash
projectpilot git sync-plan .
```

目标：

专门回答这些问题：

```text
我现在能不能 push？
我应该 pull 还是 fetch？
为什么 push 被拒绝？
现在是不是 diverged？
我能不能 rebase？
什么时候绝对不能 force push？
```

核心判断规则：

| 状态 | 建议 |
| --- | --- |
| clean + behind | 可以 `git pull --ff-only` |
| clean + ahead | 可以 `git push` |
| clean + diverged | 需要选择 merge 或 rebase |
| dirty + behind | 先 commit 或 stash，再同步 |
| dirty + diverged | 阻止自动操作，先保护本地改动 |
| no upstream | 先设置 upstream |
| protected branch | 禁止改写历史 |

示例输出：

```text
Sync Status
  branch: main
  upstream: origin/main
  ahead: 1
  behind: 2
  state: diverged
  working tree: dirty

Decision
  Do not push now.

Reason
  Your local branch and remote branch both have unique commits.
  Your working tree also has uncommitted changes.

Recommended Path
  1. Commit or stash local changes.
  2. Fetch remote changes.
  3. Choose merge if you want to preserve collaboration history.
  4. Choose rebase only if your local commits are not shared.
```

JSON 输出建议：

```json
{
  "branch": "main",
  "upstream": "origin/main",
  "ahead": 1,
  "behind": 2,
  "sync_state": "diverged",
  "working_tree_state": "dirty",
  "can_push": false,
  "can_pull_ff_only": false,
  "recommended_action": "commit_or_stash_then_choose_merge_or_rebase",
  "blocked_operations": [
    {
      "operation": "push",
      "reason": "branch_is_diverged"
    }
  ]
}
```

价值：

这是后端和 UI 最需要的智能判断能力之一。它可以直接作为桌面 App 的“同步建议”数据源。

### 5.4 恢复建议中心

命令建议：

```bash
projectpilot git recover .
```

第一阶段目标：

先不自动恢复，只提供解释和建议。

需要展示：

- 当前 HEAD；
- 当前分支；
- 最近 reflog；
- 最近一次 commit；
- 最近一次 checkout / switch；
- 最近一次 merge / reset / rebase；
- 可恢复点；
- 对应恢复命令；
- 风险说明。

示例输出：

```text
Recovery Overview
  current branch: main
  current HEAD: abc123 update executor docs

Recent HEAD Movements
  1. abc123 HEAD@{0}: commit: update executor docs
  2. def456 HEAD@{1}: checkout: moving from feature/demo to main
  3. 789abc HEAD@{2}: commit: add backend polling

Common Recovery Options
  Undo last commit but keep changes:
    git reset --soft HEAD~1
    risk: medium

  Undo last commit and unstage changes:
    git reset --mixed HEAD~1
    risk: medium

  Return to previous HEAD:
    git reset --hard def456
    risk: high
    warning: this can discard working tree changes
```

JSON 输出建议：

```json
{
  "current_branch": "main",
  "head": "abc123",
  "reflog": [],
  "recovery_options": [
    {
      "scenario": "undo_last_commit_keep_changes",
      "command": ["git", "reset", "--soft", "HEAD~1"],
      "risk": "medium",
      "auto_execute": false
    }
  ]
}
```

价值：

这是解决“误操作恢复焦虑”的核心能力。第一版只解释，不执行，就已经很有价值。

### 5.5 提交质量升级

现有命令：

```bash
projectpilot git commit-plan .
```

升级目标：

把它从“能不能提交”升级为“怎么提交更干净”。

需要增加：

- 检查 commit message 是否太随意；
- 根据 staged diff 建议 commit message；
- 检查无关文件是否混在一起；
- 建议拆分为多个 commit；
- 检查 `.env`、密钥、token；
- 检查大文件；
- 检查构建产物和缓存；
- 建议 `.gitignore` 规则。

示例输出：

```text
Commit Plan
  status: needs review

Suggested Commits

1. feat(git): add status map command
   files:
   - projectpilot/git/state_map.py
   - tests/test_git_state_map.py

2. docs: document smart git module plan
   files:
   - docs/SMART_GIT_MODULE_PLAN.md

Warnings
  README.md is modified but not related to the staged Python files.
  Consider committing docs separately.
```

JSON 输出建议：

```json
{
  "status": "needs_review",
  "suggested_commits": [
    {
      "message": "feat(git): add status map command",
      "files": []
    }
  ],
  "warnings": [],
  "blocked_files": []
}
```

价值：

它能直接改善提交历史质量，也能减少 PR 里混入无关改动。

## 6. 交付标准

### 6.1 基础合格版

当前项目基本已经达到基础合格版。

能力要求：

- Git 状态检测；
- doctor 诊断；
- suggest 建议；
- commit-plan；
- safe add / commit / pull / push；
- audit；
- JSON 输出；
- 测试覆盖。

判断：

```text
这是一个可用的安全 Git CLI。
```

### 6.2 GitHub 可发布版

建议达到这个阶段后正式作为智能 Git 模块宣传。

能力要求：

- `git map`；
- `git branches`；
- `git sync-plan`；
- `git recover`；
- `commit-plan v2`；
- README demo；
- JSON schema 文档；
- 单元测试；
- 至少一个完整演示流程。

判断：

```text
这是一个有创新表达的 Git 状态理解工具。
```

### 6.3 优秀展示版

后续增强方向：

- conflict doctor；
- reflog 恢复向导；
- 敏感信息守卫；
- 大文件和 Git LFS 建议；
- 分支清理建议；
- AI 生成 commit 摘要；
- AI 生成 PR 摘要；
- 团队 Git 策略配置。

判断：

```text
这是 ProjectPilot 的智能 Git 大脑。
```

## 7. 和队友模块的接口边界

智能 Git 模块应该提供稳定的结构化输出，供后端、桌面 App、TUI、Executor 使用。

### 7.1 CLI 调用边界

所有智能命令都应该支持：

```bash
--json
```

队友模块不应该解析文本输出，而应该读取 JSON。

### 7.2 后端调用边界

后端可以调用：

```bash
projectpilot git status . --json
projectpilot git doctor . --json
projectpilot git map . --json
projectpilot git branches . --json
projectpilot git sync-plan . --json
projectpilot git recover . --json
projectpilot git commit-plan . --json
```

后端负责：

- 保存结果；
- 展示给前端；
- 创建 Executor 任务；
- 做用户审批；
- 写数据库。

智能 Git 模块负责：

- 分析状态；
- 判断风险；
- 生成建议；
- 生成命令计划；
- 给出恢复建议。

### 7.3 Executor 调用边界

Executor 不应该自己判断 Git 业务逻辑。

推荐流程：

```text
智能 Git 模块生成 OperationPlan
  ↓
后端保存计划并等待用户审批
  ↓
Executor 收到 approved task
  ↓
Executor 校验 expected_command
  ↓
Executor 执行
  ↓
Executor 上传结果
```

智能 Git 模块不直接连接服务器，也不直接管理远程任务。

## 8. 推荐开发顺序

### 阶段 A：Git 状态四区图

目标：

- 新增 `projectpilot/git/state_map.py`；
- 新增 `projectpilot git map`；
- 支持文本输出；
- 支持 JSON 输出；
- 添加测试。

优先级最高。

### 阶段 B：分支关系诊断

目标：

- 新增 `projectpilot/git/branch_lifecycle.py`；
- 新增 `projectpilot git branches`；
- 识别 upstream、merged、gone、safe-to-delete；
- 添加测试。

### 阶段 C：远程同步决策器

目标：

- 新增 `projectpilot/git/sync_planner.py`；
- 新增 `projectpilot git sync-plan`；
- 复用已有 pull / push planner；
- 输出 can_push、can_pull、blocked_operations。

### 阶段 D：恢复建议中心

目标：

- 新增 `projectpilot/git/recovery.py`；
- 新增 `projectpilot git recover`；
- 解析 reflog；
- 给出恢复建议；
- 第一版不执行恢复命令。

### 阶段 E：commit-plan v2

目标：

- 增强现有 `commit_planner.py`；
- 支持拆分提交建议；
- 支持低质量 message 检测；
- 支持敏感文件和大文件初步检测；
- 输出 suggested_commits。

## 9. 推荐目录结构

建议逐步形成：

```text
projectpilot/
  git/
    inspector.py
    parser.py
    analyzer.py
    recommender.py
    reporter.py
    operation_planner.py
    safe_executor.py
    audit.py
    state_map.py
    branch_lifecycle.py
    sync_planner.py
    recovery.py
    sensitive_guard.py
    commit_planner.py

  models/
    git_status.py
    operation_plan.py
    audit_log.py
    state_map.py
    branch_lifecycle.py
    sync_plan.py
    recovery.py
```

## 10. GitHub 展示建议

智能 Git 模块在 GitHub 上可以这样介绍：

```text
ProjectPilot Smart Git helps developers understand Git state, plan safe operations, and recover from mistakes.
```

中文介绍：

```text
ProjectPilot 智能 Git 模块帮助开发者看懂 Git 当前状态、整理提交历史、规划安全操作，并在误操作后提供恢复建议。
```

README 演示建议：

```bash
projectpilot git map .
projectpilot git branches .
projectpilot git sync-plan .
projectpilot git commit-plan .
projectpilot git recover .
```

演示重点：

- Git 四区图；
- 当前风险；
- 下一步建议；
- dry-run 安全计划；
- 审计记录；
- 恢复建议。

## 11. 最终结论

你负责的智能 Git 模块已经有可行基础。

当前状态可以判断为：

```text
基础安全 Git CLI 已经成立。
```

下一步目标应该是：

```text
升级为 Git 状态理解引擎。
```

最重要的五个交付物是：

```text
1. git map
2. git branches
3. git sync-plan
4. git recover
5. commit-plan v2
```

这五个完成后，智能 Git 模块就能支撑 ProjectPilot 的核心创新点，也足够作为 GitHub 发布版的重要亮点。

