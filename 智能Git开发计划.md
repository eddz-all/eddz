# ProjectPilot 智能 Git 开发计划

## 1. 项目定位

ProjectPilot 第一阶段先聚焦为一个 **智能 Git 助手**。

它不是简单地封装 `git status`、`git pull`、`git push`，而是帮助用户理解当前仓库状态、识别操作风险、生成下一步建议，并在用户确认后执行部分安全 Git 操作。

核心目标：

- 看懂当前 Git 仓库状态；
- 解释当前状态意味着什么；
- 判断 pull、commit、push 等操作是否安全；
- 给出下一步建议；
- 对危险操作进行风险提示和确认；
- 为后续多项目、多服务器、团队协作能力打基础。

## 2. 第一版能力边界

第一版只做 **本地 Git 仓库智能分析**，暂不做多服务器、远程 SSH、环境检测、Web 界面和团队共享记忆。

第一版关注的问题：

- 当前目录是不是 Git 仓库；
- 当前分支是什么；
- 是否有远程仓库；
- 是否存在未提交修改；
- 是否存在未跟踪文件；
- 本地分支是否领先远程；
- 本地分支是否落后远程；
- 是否存在冲突、rebase、merge 中间状态；
- 当前是否适合 pull；
- 当前是否适合 commit；
- 当前是否适合 push；
- 有哪些文件可能不应该提交；
- 下一步最推荐做什么。

## 3. MVP 命令设计

建议先实现 CLI 工具，命令名暂定为 `projectpilot`。

### 3.1 状态查看

```bash
projectpilot git status
```

输出结构化 Git 状态，包括：

- 仓库路径；
- 当前分支；
- 当前 commit；
- upstream 分支；
- 工作区是否干净；
- staged 文件；
- unstaged 文件；
- untracked 文件；
- ahead / behind 状态；
- merge / rebase 状态。

### 3.2 智能解释

```bash
projectpilot git explain
```

用自然语言解释当前仓库状态，例如：

```text
当前仓库在 main 分支。
本地有 3 个未提交文件，其中 1 个已暂存，2 个尚未暂存。
本地分支比 origin/main 领先 1 个提交，可以考虑 push。
由于工作区不干净，不建议直接 pull。
```

### 3.3 操作建议

```bash
projectpilot git suggest
```

根据当前状态生成建议，例如：

- 先查看未提交修改；
- 先提交本地修改；
- 可以安全 push；
- pull 前建议 stash 或 commit；
- 当前正在 merge，需要先解决冲突；
- 当前没有远程分支，需要设置 upstream。

### 3.4 报告生成

```bash
projectpilot git report
```

生成 Markdown 报告，默认输出到：

```text
.projectpilot/reports/git-status-YYYYMMDD-HHMMSS.md
```

报告包含：

- 仓库基本信息；
- Git 状态摘要；
- 风险等级；
- 文件变更列表；
- ahead / behind 分析；
- 操作建议；
- 可选命令参考。

## 4. 第二版：受控执行

在只读分析稳定之后，再加入受控执行能力。

### 4.1 安全操作

```bash
projectpilot git fetch
projectpilot git add
projectpilot git commit
projectpilot git push
```

安全规则：

- `fetch` 默认低风险，可直接执行；
- `add` 需要明确文件范围；
- `commit` 需要用户确认提交信息；
- `push` 需要确认目标远程和分支。

### 4.2 中风险操作

```bash
projectpilot git pull
projectpilot git stash
```

执行前必须检查：

- 工作区是否干净；
- 是否存在未跟踪文件；
- 是否落后远程；
- 是否可能产生冲突。

### 4.3 高风险操作

高风险操作第一阶段只提示，不执行。

包括：

- `reset --hard`;
- `clean -fd`;
- `push --force`;
- 删除分支；
- 修改远程地址；
- rebase 公共分支。

如果后续支持执行，必须二次确认。

## 5. 风险分级规则

### 5.1 低风险

- 查看状态；
- 查看 diff；
- 查看 log；
- fetch；
- 生成报告。

### 5.2 中风险

- add；
- commit；
- pull；
- stash；
- push 到自己的分支。

### 5.3 高风险

- reset；
- clean；
- force push；
- rebase 公共分支；
- 删除分支；
- 覆盖本地修改。

## 6. 核心模块设计

建议使用 Python 实现核心引擎。

```text
projectpilot/
  cli.py
  git/
    inspector.py
    parser.py
    analyzer.py
    recommender.py
    reporter.py
    executor.py
    risk.py
  models/
    git_status.py
    recommendation.py
    risk.py
  utils/
    shell.py
    paths.py
```

### 6.1 inspector

负责调用 Git 命令并收集原始信息。

需要支持：

- `git rev-parse --show-toplevel`;
- `git status --porcelain=v2 --branch`;
- `git branch --show-current`;
- `git remote -v`;
- `git log -1 --oneline`;
- `git diff --name-status`;
- `git diff --cached --name-status`;
- `git ls-files --others --exclude-standard`;

### 6.2 parser

负责把 Git 命令输出解析成结构化数据。

不要只依赖人类可读的 `git status` 文本，优先使用：

```bash
git status --porcelain=v2 --branch
```

### 6.3 analyzer

负责判断仓库状态。

例如：

- 是否是 Git 仓库；
- 是否有 upstream；
- 工作区是否干净；
- 是否 ahead；
- 是否 behind；
- 是否 diverged；
- 是否处于 merge / rebase 状态；
- 是否存在潜在危险文件。

### 6.4 recommender

负责生成下一步建议。

建议分为：

- primary action：最推荐操作；
- warnings：风险提示；
- alternatives：可选操作；
- commands：参考命令。

### 6.5 reporter

负责生成 Markdown / JSON 报告。

第一版先实现 Markdown，后续再支持 JSON。

### 6.6 executor

负责受控执行 Git 操作。

第一版可以先不实现，或者只实现 `fetch`。

## 7. 数据结构草案

### 7.1 GitStatus

```python
class GitStatus:
    repo_path: str
    branch: str | None
    upstream: str | None
    commit: str | None
    is_clean: bool
    ahead: int
    behind: int
    staged_files: list[str]
    unstaged_files: list[str]
    untracked_files: list[str]
    conflicted_files: list[str]
    state: str
```

### 7.2 Recommendation

```python
class Recommendation:
    level: str
    title: str
    reason: str
    suggested_commands: list[str]
    requires_confirmation: bool
```

### 7.3 RiskAssessment

```python
class RiskAssessment:
    level: str
    reasons: list[str]
    blocked_operations: list[str]
    allowed_operations: list[str]
```

## 8. 第一阶段开发任务

### 8.1 初始化项目

- 创建 Python 项目结构；
- 配置 CLI 入口；
- 添加基础 README；
- 添加测试目录；
- 配置格式化和测试工具。

推荐技术：

- Python 3.11+；
- Typer；
- Pydantic；
- pytest；
- rich。

### 8.2 实现 Git 状态采集

- 检测当前目录是否为 Git 仓库；
- 获取仓库根目录；
- 获取当前分支；
- 获取 upstream；
- 获取 ahead / behind；
- 获取 staged / unstaged / untracked 文件；
- 获取冲突状态。

### 8.3 实现状态分析

- 判断 clean / dirty；
- 判断 can_pull；
- 判断 can_push；
- 判断 needs_commit；
- 判断 no_upstream；
- 判断 diverged；
- 判断 in_merge_or_rebase。

### 8.4 实现建议生成

- 根据状态生成主建议；
- 根据风险生成警告；
- 输出推荐命令；
- 避免自动建议危险命令。

### 8.5 实现报告生成

- 生成 Markdown 报告；
- 保存到 `.projectpilot/reports/`；
- 报告包含时间戳；
- 报告中保留原始状态摘要和智能建议。

### 8.6 添加测试

优先测试：

- 非 Git 目录；
- 干净仓库；
- 有未提交修改；
- 有未跟踪文件；
- ahead；
- behind；
- diverged；
- 无 upstream；
- merge 冲突状态。

## 9. 验收标准

第一版完成时，应满足：

- 在任意 Git 仓库中可以运行 `projectpilot git status`；
- 输出不是简单 Git 原文，而是结构化摘要；
- `projectpilot git explain` 可以解释当前状态；
- `projectpilot git suggest` 可以给出合理下一步；
- `projectpilot git report` 可以生成 Markdown 报告；
- 非 Git 目录下有清晰错误提示；
- 不会自动执行高风险 Git 操作；
- 有基本测试覆盖。

## 10. 后续扩展方向

智能 Git 稳定后，再扩展：

- 多仓库扫描；
- 项目级 Git 健康评分；
- commit message 生成；
- PR 前检查；
- changelog 生成；
- 与 AI API 集成生成更自然的解释；
- 远程服务器 Git 状态检测；
- 团队共享 Git 操作记录；
- Web 可视化界面。

## 11. 推荐开发顺序

```text
初始化 CLI 项目
↓
实现 Git 状态采集
↓
实现结构化状态模型
↓
实现状态解释
↓
实现风险判断
↓
实现操作建议
↓
实现 Markdown 报告
↓
补测试
↓
再考虑受控执行
```

第一阶段只要能做到“看懂 Git 状态并给出可信建议”，ProjectPilot 的智能 Git 原型就成立了。
