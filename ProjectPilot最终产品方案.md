# ProjectPilot 最终产品方案

## 0. 阅读指南

这篇文档是 ProjectPilot 的总方案。先记住一句话：

```text
ProjectPilot = AI 决策大脑 + 后端神经系统 + 数据库历史记录 + Executor 执行器 + 多端用户入口。
```

阅读顺序：

| 目的 | 先读 |
| --- | --- |
| 快速理解最终产品 | 1、2、12 |
| 拆开发任务 | 5、6、8、9、10 |
| 做后端和执行层 | 7、8.8、9.1、9.3 |

几个词的固定含义：

| 名称 | 含义 | 不负责什么 |
| --- | --- | --- |
| AI Planner | 分析状态、生成计划、判断风险、提出回滚建议 | 不直接自由敲命令 |
| 后端 | API、权限、审批、任务调度、状态流转 | 不直接代替用户绕过审批 |
| 数据库 | 保存项目状态、计划版本、审批、快照、审计历史 | 不做决策 |
| Executor | 连接 SSH，执行已批准的 Git/Docker/环境命令，采集结果 | 不是第二个 AI |
| Web 前端 | 团队和浏览器入口 | 不直接连接服务器 |
| 桌面 GUI App | 本机图形化入口、通知、Executor 管理 | 不绕过后端审批 |
| Rust TUI | 终端里的交互式入口 | 不直接拼接危险命令 |
| CLI | 脚本化和 CI 入口 | 不替代审批模型 |

当前最终决定：

| 问题 | 决定 |
| --- | --- |
| 主模式 | Central Executor 集中管理服务器 |
| 补充模式 | Local Executor 处理私钥不出本机、内网不可达场景 |
| AI 能不能直接敲命令 | 不能，必须先生成计划，用户批准后由 Executor 执行 |
| Git 范围 | 覆盖 status、branch、merge、rebase、cherry-pick、push、pull、冲突解释和回滚建议 |
| Docker 范围 | 覆盖 daemon、image、container、compose、logs、build、restart、volume、network、registry |
| 用户入口 | Web、桌面 GUI、Rust TUI、CLI 共用同一套后端、权限和审计 |

## 1. 一句话定位

ProjectPilot 最终要做成一个：

```text
面向开发者和团队的 AI 项目运维与 Git 协作控制台。
```

它不是单纯的 Git 工具，也不是单纯的 SSH 工具，而是一个把项目代码、服务器环境、Git 状态、部署风险、AI 分析、团队协作统一起来的平台。

最终用户打开 ProjectPilot 后，应该能清楚看到：

```text
我的项目现在在哪些机器上运行？
每台机器的 Git 状态是否一致？
远程服务器环境是否正常？
有没有未提交、落后、冲突、依赖缺失、Docker 异常？
AI 建议我下一步做什么？
哪些操作可以安全执行？
哪些操作必须人工确认？
所有执行历史是否可追踪？
```

## 2. 最终产品形态

ProjectPilot 最终由八个逻辑部分组成：

```text
1. Web 前端
2. macOS / Windows / Linux 桌面 GUI 主应用
3. Rust TUI 终端交互端 + CLI 脚本入口
4. 主机后端 API / 任务调度 / 审批系统
5. AI Planner 决策大脑
6. 数据库 / 历史记录 / 审计日志
7. Executor 执行器层
8. 远程服务器 SSH / Git / Docker 执行层
```

整体结构：

```text
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│       Web 前端        │  │    桌面 GUI 主应用     │  │   Rust TUI / CLI      │
│ 团队控制台 / 浏览器入口 │  │ 本机桌面入口 / 原生体验 │  │ 终端审批 / 自动化脚本   │
└───────────┬──────────┘  └───────────┬──────────┘  └───────────┬──────────┘
            │                         │                         │
            └─────────────────────────┼─────────────────────────┘
                                      ▼
┌──────────────────────────────┐
│      主机后端 API / 调度系统      │
│  权限 / 审批 / 任务队列 / 状态流   │
└───────────────┬──────────────┘
                │ 调用 / 保存 / 派发
                ▼
┌──────────────────────────────┐
│        AI Planner 决策大脑       │
│  分析 / 计划 / 风险 / 回滚建议     │
└───────────────┬──────────────┘
                │ 生成结构化计划
                ▼
┌──────────────────────────────┐
│      数据库 / 历史记录 / 审计    │
│ 状态快照 / ApprovedPlan / Log   │
└───────────────┬──────────────┘
                │ 已批准任务
                ▼
┌──────────────────────────────┐
│          Executor 执行器层      │
│ Central Exec / Local Exec     │
└───────────────┬──────────────┘
                │ SSH
                ▼
┌──────────────────────────────┐
│          远程服务器集群         │
│ Git / Docker / 环境 / 项目进程  │
└──────────────────────────────┘
```

Web 前端、桌面 GUI 主应用、Rust TUI 和 CLI 都是操作入口。Web 适合团队和浏览器访问，桌面 GUI App 适合个人日常本机使用，TUI 适合终端里的审批、编辑计划、执行和回滚，CLI 适合脚本化。它们调用同一个后端和同一套权限/审计/计划模型。

核心分工必须非常清楚：

```text
AI = 决策大脑
Executor = 手
后端 = 神经系统 + 当前状态记忆
数据库 = 历史记录 + 审计证据
```

AI 不直接自由敲命令。AI 负责分析、生成计划、判断风险和提出回滚建议；Executor 负责连接 SSH、执行 Git/Docker/环境命令、采集结果；后端负责 API、权限、审批、任务调度和状态流转；数据库负责保存项目状态、计划版本、审批记录、执行日志、快照和回滚历史。

最终执行层有两种模式：

```text
Central Executor 模式
  主机后端所在机器保存/加载 SSH config，集中连接多台服务器。
  这是服务器集中管理的主模式，速度快，执行链路短。

Local Executor 模式
  用户本机或内网机器运行 Local Executor，复用本机 ~/.ssh/config 和 ssh-agent。
  这是私钥不出本机、主机无法直连内网机器时的补充模式。
```

两种模式都不是第二个 AI。它们都是普通执行器，只执行已批准的结构化计划。

## 3. 用户最终怎么使用

### 3.1 第一次使用

用户安装 ProjectPilot Desktop App。

打开后看到原生桌面窗口：

```text
ProjectPilot Desktop

Backend URL:  http://主机后端地址
Token:        ********
Executor ID:  eddz-mac-local
Allowed Root: /Users/eddz/work
Executor:     Central / Local

[连接主机] [选择执行器模式] [扫描 SSH 配置] [进入控制台]
```

用户只需要做四件事：

1. 填后端地址；
2. 填后端生成的 Executor token；
3. 选择执行器模式；
4. 选择本机项目根目录。

然后点击：

```text
连接主机
```

桌面 GUI 主应用连接成功后，用户看到的是完整项目控制台。执行器负责真正连接 SSH、执行 Git/Docker/环境命令。

如果选择 Central Executor，主机后端所在机器负责保存或加载 SSH config，并集中连接多台服务器。

如果选择 Local Executor，本机执行器作为后台服务运行，负责本机检测、SSH 执行和权限边界。

### 3.2 添加远程服务器

桌面 GUI App、Central Executor 设置页或 Local Executor 设置页自动扫描：

```text
~/.ssh/config
```

展示：

```text
可用服务器

✓ dev-server       ubuntu@192.168.1.20:22
✓ prod-server      deploy@prod.example.com:2222
✓ gpu-lab          root@gpu.internal:22
```

用户点击：

```text
[测试连接]
```

ProjectPilot 使用执行器所在机器的 SSH 配置测试连接。Central Executor 使用主机上的 SSH config；Local Executor 使用用户本机的 SSH config。默认不上传私钥明文。

### 3.3 绑定项目

在 Web 前端、桌面 GUI App 或 TUI 中绑定：

```text
项目：ProjectPilot
本地路径：/Users/eddz/work/engine
远程 dev-server 路径：/srv/projectpilot
远程 prod-server 路径：/opt/projectpilot
Git remote：git@example.com:team/projectpilot.git
```

### 3.4 日常使用

用户打开 Web 前端或桌面 GUI App 看到：

```text
ProjectPilot

本机 eddz-mac
  Git: clean, main, ahead 0, behind 0
  环境: Python 3.14, Node 26, Docker stopped

dev-server
  Git: main, behind 2
  环境: Docker running, Node 20, disk 68%

prod-server
  Git: main, clean
  环境: Docker running, disk 82%
```

AI 总结：

```text
dev-server 落后远端 2 个提交，可以执行 git pull --ff-only。
本机 Docker 未运行，但不影响当前 Git 同步。
prod-server 状态正常。
```

前端展示按钮：

```text
[检测全部] [生成同步计划] [查看风险] [执行安全操作]
```

## 4. AI 最终扮演什么角色

AI 是项目控制台的大脑，但不是无限权限执行者。

AI 负责：

- 分析 Git 状态；
- 分析环境差异；
- 解释错误原因；
- 生成操作计划；
- 判断风险等级；
- 给出下一步建议；
- 帮用户理解复杂状态；
- 生成部署前检查报告。

AI 不应该直接：

- 持有 SSH 私钥；
- 绕过权限执行命令；
- 自动执行危险命令；
- 修改数据库审计记录；
- 跳过用户确认。

最终 AI 工作流：

```text
用户提出目标
  ↓
AI 读取数据库中的项目 / Git / 环境 / 日志
  ↓
AI 生成计划
  ↓
后端做权限和风险校验
  ↓
用户确认
  ↓
Executor 通过 SSH 执行
  ↓
结果回传数据库
  ↓
AI 继续分析结果
```

### 4.1 AI 执行必须经过人工批准

AI 可以操作本机电脑和远程服务器，但前提是：

```text
AI 只能执行被用户批准的计划版本。
```

也就是说，AI 的执行流程不是：

```text
AI 想做什么 -> 直接执行
```

而是：

```text
AI 生成建议和计划
  ↓
用户查看计划
  ↓
用户选择：
    1. 直接批准 AI 原计划
    2. 手动修改计划后批准
    3. 拒绝执行
  ↓
后端保存被批准的计划版本
  ↓
Executor 只执行这个被批准的版本
  ↓
执行全过程写入历史
```

### 4.2 用户可以修改 AI 计划

AI 生成的计划应是可编辑的。

示例：

```text
AI 原计划：
1. git fetch
2. git pull --ff-only
3. npm install
4. docker compose restart app
```

用户可以修改为：

```text
用户批准版本：
1. git fetch
2. git pull --ff-only
3. npm install

删除：
4. docker compose restart app
```

最终执行的不是 AI 原计划，而是：

```text
用户批准版本
```

系统必须保存：

- AI 原始计划；
- 用户修改后的计划；
- 修改差异；
- 批准人；
- 批准时间；
- 执行结果。

### 4.3 执行前必须生成回滚方案

任何会改变本机或服务器状态的计划，都必须在执行前生成回滚方案。

计划中每一步都要标记：

```text
是否可回滚
如何回滚
回滚风险
需要什么前置快照
```

示例：

```json
{
  "step": "git pull --ff-only",
  "risk_level": "medium",
  "rollback": {
    "available": true,
    "strategy": "reset_to_previous_commit",
    "before_commit": "abc123",
    "command": "git reset --hard abc123",
    "requires_confirmation": true
  }
}
```

注意：即使有回滚命令，也不代表可以自动回滚。高风险回滚仍然需要用户确认。

### 4.4 不是所有操作都能自动回滚

系统要明确告诉用户哪些操作可回滚，哪些操作不可完全回滚。

| 操作 | 回滚能力 |
| --- | --- |
| `git pull --ff-only` | 可回到执行前 commit，但需要确认 |
| `git commit` | 可 revert 或 reset，取决于是否已 push |
| `npm install` | 可恢复 lockfile，但 node_modules 状态不一定完全一致 |
| 修改 `.env` | 可从备份恢复 |
| Docker restart | 无真正状态回滚，只能再次 restart |
| 数据库迁移 | 必须有迁移脚本支持，否则不可自动回滚 |
| `rm -rf` | 默认禁止，因为不可安全回滚 |

### 4.5 执行历史必须完整保存

每次 AI 执行都必须形成一条完整历史链：

```text
用户目标
  ↓
AI 原始建议
  ↓
AI 原始计划
  ↓
用户修改记录
  ↓
最终批准计划
  ↓
执行前快照
  ↓
逐步执行日志
  ↓
执行后快照
  ↓
AI 结果总结
  ↓
可用回滚入口
```

这条链路用于：

- 页面展示；
- 审计；
- 问题复盘；
- 回滚；
- 训练更好的建议规则；
- 团队协作审批。

## 5. 最终核心功能

### 5.1 项目总览

每个项目有一个总览页。

展示：

- 项目名称；
- Git 仓库地址；
- 本地机器；
- 远程服务器；
- 当前分支；
- ahead / behind；
- dirty 状态；
- 最近提交；
- 最近检测时间；
- 环境健康状态；
- AI 总结。

示例：

```text
ProjectPilot

状态：需要注意
原因：dev-server 落后 main 2 个提交，Docker 正常。

机器状态：
  eddz-mac      clean
  dev-server    behind 2
  prod-server   healthy
```

### 5.2 Git 智能管理

最终 Git 能力要覆盖 Git 的完整能力面，而不是只覆盖 `pull / push / commit`。

覆盖的意思是：

```text
AI 能识别这个 Git 功能属于什么场景；
AI 能读取相关状态；
AI 能解释风险；
AI 能生成计划；
AI 能在允许的情况下预演；
AI 能在用户批准后执行；
AI 能记录历史；
AI 能在可回滚时生成回滚入口。
```

最终 Git 能力包括：

- 本地 Git 检测；
- 远程 Git 检测；
- init / clone / remote / config 管理；
- branch / upstream / remote 检测；
- ahead / behind / diverged 判断；
- 分支关系图分析；
- 分支合并可行性分析；
- merge base / changed files / conflict risk 分析；
- dirty 文件分类；
- add / restore / reset 工作区管理；
- commit plan；
- tag / release 标记管理；
- safe add；
- safe commit；
- safe pull；
- safe push；
- branch create / switch 计划；
- merge plan；
- rebase plan；
- cherry-pick plan；
- revert plan；
- stash plan；
- worktree 管理；
- submodule 管理；
- LFS 状态检测；
- reflog / recovery 辅助；
- bisect 辅助定位；
- blame / grep / show 辅助分析；
- archive / bundle 辅助导出；
- Git 操作审计；
- 冲突解释；
- 冲突解决建议；
- 分叉解释；
- PR / MR 摘要生成；
- 部署前 Git 检查。

智能 Git 的目标不是把几个 Git 命令包一层按钮，而是让 AI 参与完整 Git 生命周期：

```text
建仓 -> 克隆 -> 配置远程 -> 分支开发 -> 暂存 -> 提交 -> 同步
-> 合并 -> 解决冲突 -> 打 tag -> 发布 -> 回滚 -> 恢复
```

尤其是分支协作流程。

用户可以问：

```text
feature/login 能不能合进 main？
为什么我这个分支和远端分叉了？
这两个分支冲突大不大？
帮我生成合并计划。
帮我解释冲突文件应该怎么处理。
这个 rebase 有没有风险？
```

AI 应该输出：

```text
目标：把 feature/login 合并到 main

分析：
1. main 比本地落后 2 个提交，建议先 fetch 并更新。
2. feature/login 比 main 多 5 个提交。
3. 涉及文件：auth.py、login_view.py、tests/test_login.py。
4. auth.py 两边都修改过，存在冲突风险。
5. 该分支已经 push 到远端，不建议直接 rebase 公共历史。

建议计划：
1. git fetch
2. 检查 main 和 feature/login 的 merge-base
3. 在临时 worktree 中预演 merge
4. 如果无冲突，生成合并提交计划
5. 如果有冲突，列出冲突文件并给出人工可审查的解决建议

需要用户批准：
- 是否允许创建临时 worktree
- 是否允许执行真实 merge
- 是否允许 AI 修改冲突文件
```

#### 分支与合并能力分层

只读分析能力：

```text
git branch
git branch -vv
git merge-base
git log --graph
git diff branchA...branchB
git diff --name-status branchA...branchB
git show
git blame
```

这些能力可以自动执行，用于让 AI 理解分支关系、提交差异和冲突风险。

可审批执行能力：

```text
git switch
git switch -c
git merge --ff-only
git merge --no-commit
git cherry-pick --no-commit
```

这些操作会改变工作区或索引，必须生成计划，并在用户确认后执行。

强确认能力：

```text
git merge
git rebase 私有分支
git cherry-pick
AI 修改冲突文件
git merge --abort
git rebase --abort
```

这些操作可以被 ProjectPilot 支持，但必须展示：

- 执行前分支；
- 执行前 commit；
- 涉及文件；
- 可能冲突；
- 回滚方式；
- 是否已经 push 到远端；
- 是否影响公共历史。

默认禁止能力：

```text
git rebase 公共分支
git push --force
git reset --hard
git clean -fd
删除受保护分支
```

这些操作只能作为风险解释和人工建议，不能由 AI 默认执行。

#### Git 安全规则

允许自动执行：

```text
git status
git log
git diff
git fetch
git branch
git merge-base
git show
git blame
git grep
git reflog
```

允许在条件满足时执行：

```text
git pull --ff-only
git push
git add
git commit
git switch
git switch -c
git merge --ff-only
git stash push
git stash pop
git revert --no-commit
git tag
```

允许强确认后执行：

```text
git merge
git rebase 私有分支
git cherry-pick
AI 写入冲突解决 patch
git worktree add / remove
git submodule update
git remote set-url
```

默认禁止：

```text
git reset --hard
git clean -fd
git push --force
git rebase 公共分支
删除受保护分支
删除远程分支
重写已共享 tag
```

ProjectPilot 对复杂 Git 操作的原则是：AI 可以分析、预演、生成计划和建议解决方案，但真实改变仓库历史或写入冲突文件前，必须获得用户批准。

当前本地智能 Git 已完成的核心实现：

- `status / explain / suggest / report / diff / log / fetch`;
- `commit-plan / add-plan / doctor / audit`;
- 受控执行 `add / commit / pull --ff-only / push`;
- 受控执行 `switch / switch -c / merge --ff-only / stash push / tag`;
- 受控执行 `revert --no-commit / cherry-pick --no-commit`;
- 高风险 `reset-hard / clean / force-push / rebase` 只生成风险计划，不执行；
- 所有 `--apply` 操作写入本地 Git 审计记录。

### 5.3 远程服务器管理

最终服务器能力：

- 自动读取 SSH Host；
- 测试 SSH 连接；
- 保存服务器别名；
- 绑定服务器到项目；
- 检测服务器系统信息；
- 检测项目路径；
- 检测 Git 状态；
- 检测 Docker；
- 检测 Node / Python；
- 检测磁盘；
- 检测 GPU / CUDA；
- 生成服务器健康报告。

服务器详情页：

```text
dev-server

连接：正常
用户：ubuntu
地址：192.168.1.20:22
项目路径：/srv/projectpilot

Git:
  branch: main
  behind: 2
  dirty: no

Environment:
  OS: Linux
  Python: 3.11
  Node: 20.11
  Docker: running
  Disk: 68%
```

### 5.4 远程环境配置

最终不是简单执行命令，而是 AI 生成配置计划。

例如用户说：

```text
帮我配置 dev-server，让它能运行这个项目。
```

AI 输出：

```text
检测结果：
1. Node 已安装，版本满足要求。
2. Docker 已安装但未运行。
3. 项目目录存在。
4. 缺少 .env 文件。

建议计划：
1. 启动 Docker。
2. 拉取最新代码。
3. 检查 .env。
4. 安装依赖。
5. 运行健康检查。
```

执行前展示风险：

```text
低风险：
  docker --version
  git status

中风险：
  npm install
  git pull --ff-only

高风险：
  systemctl restart docker
```

用户确认后才执行中高风险步骤。

### 5.5 Docker 智能管理

Docker 也要覆盖完整能力面。

覆盖的意思同样不是让 AI 随便执行所有 Docker 命令，而是：

```text
AI 能识别 Docker / Compose / 镜像 / 容器 / 网络 / 卷 / registry 的状态；
AI 能解释运行失败原因；
AI 能生成修复计划；
AI 能在安全范围内执行只读检测；
AI 能在用户批准后执行变更操作；
AI 能记录容器、镜像、卷、网络的执行前后状态；
AI 能对危险操作要求强确认或禁止默认执行。
```

最终 Docker 能力包括：

- Docker daemon 状态检测；
- Docker context 检测；
- Docker version / info 检测；
- image 列表、来源、tag、大小、构建历史分析；
- container 列表、状态、退出码、健康检查分析；
- container logs 分析；
- container exec 计划；
- container restart / stop / start 计划；
- Dockerfile 分析；
- `.dockerignore` 分析；
- image build / tag / push / pull 计划；
- buildx / multi-arch 构建计划；
- registry 登录状态检测；
- Compose 文件检测；
- Compose service / network / volume 关系分析；
- compose config 校验；
- compose up / down / restart / pull / build 计划；
- network 检测与连接关系分析；
- volume 检测、备份建议和删除风险分析；
- resource usage 检测；
- port binding 冲突检测；
- env / secret 缺失检测；
- image cleanup / container cleanup 风险分析；
- 部署前 Docker 检查；
- Docker 操作审计。

用户可以问：

```text
为什么这个容器一直重启？
这个 compose 项目能不能安全重启？
这个镜像是不是太旧了？
这台服务器有哪些没用的镜像和卷？
我能不能删这些 stopped containers？
帮我生成 Docker 部署计划。
帮我检查 Dockerfile 有没有问题。
```

AI 应该输出：

```text
目标：修复 dev-server 上 app 容器反复重启

分析：
1. Docker daemon 正常运行。
2. app 容器最近 10 分钟重启 6 次。
3. 退出码为 1。
4. 日志显示缺少 DATABASE_URL。
5. compose.yaml 中 app service 依赖 postgres，但 .env 未配置数据库地址。
6. 不建议直接 docker compose down，因为可能影响正在运行的 postgres volume。

建议计划：
1. docker compose ps
2. docker compose logs --tail=200 app
3. 检查 .env 是否存在 DATABASE_URL
4. 用户补充或批准写入 .env
5. docker compose up -d app
6. 检查 app health status

需要用户批准：
- 是否允许读取容器日志
- 是否允许修改 .env
- 是否允许重启 app service
```

#### Docker 能力分层

只读分析能力：

```text
docker version
docker info
docker context ls
docker ps
docker images
docker inspect
docker logs --tail
docker stats --no-stream
docker network ls / inspect
docker volume ls / inspect
docker compose config
docker compose ps
docker compose logs --tail
```

这些能力用于让 AI 理解 Docker 运行状态、服务拓扑、日志和资源占用。

可审批执行能力：

```text
docker pull
docker build
docker tag
docker start
docker stop
docker restart
docker compose pull
docker compose build
docker compose up -d service
docker compose restart service
docker exec 低风险诊断命令
```

这些操作会改变容器或镜像状态，必须生成计划并得到用户确认。

强确认能力：

```text
docker compose down
docker rm
docker rmi
docker volume rm
docker network rm
docker system prune
docker image prune
docker builder prune
docker push
docker exec 会修改容器状态的命令
```

这些操作必须展示影响范围：

- 哪些容器会停止；
- 哪些镜像会删除；
- 哪些 volume 可能丢数据；
- 哪些端口会变化；
- 哪些服务会短暂不可用；
- 是否影响生产环境；
- 是否有备份或回滚方式。

默认禁止能力：

```text
docker system prune -a --volumes
删除未备份的数据卷
在生产容器中执行未知脚本
以 privileged 模式运行未知镜像
挂载宿主机敏感目录
覆盖生产 registry tag
```

ProjectPilot 对 Docker 的原则是：AI 可以做诊断、生成部署和修复计划，但任何可能停止服务、删除镜像/容器/卷、修改生产容器或覆盖镜像 tag 的操作，都必须经过用户批准。

#### Docker 重点管理对象

ProjectPilot 需要把 Docker 拆成可以理解、可以入库、可以审批的对象。

#### Docker Daemon 与 Context

需要理解：

- Docker daemon 是否运行；
- Docker API 版本；
- Docker root dir；
- storage driver；
- 当前 Docker context；
- context 指向本机还是远程；
- 用户是否有 Docker 权限；
- Docker Desktop / Linux Docker Engine 差异。

AI 应该能回答：

```text
Docker 为什么连不上？
为什么当前 context 不对？
为什么普通用户没有权限执行 docker？
Docker Desktop 没启动会影响哪些项目？
```

#### Container

需要理解：

- 容器状态：running / exited / restarting / paused；
- 退出码；
- healthcheck；
- restart policy；
- started_at / finished_at；
- ports；
- mounts；
- networks；
- env；
- entrypoint / command；
- logs；
- resource usage。

AI 应该能做：

- 解释容器为什么退出；
- 解释容器为什么反复重启；
- 分析 healthcheck 失败；
- 分析端口冲突；
- 判断是否可以安全 restart；
- 判断是否可以安全 stop / remove；
- 生成 container exec 诊断计划。

#### Image

需要理解：

- image id；
- repository / tag；
- digest；
- size；
- created time；
- layers；
- build source；
- dangling images；
- unused images；
- registry 来源；
- tag 是否指向生产版本。

AI 应该能做：

- 判断镜像是否过旧；
- 判断当前容器运行的是哪个 image；
- 判断本地 image 是否和 registry 一致；
- 生成 pull / build / tag / push 计划；
- 判断哪些 image 可以清理；
- 防止误删仍被容器使用的 image。

#### Dockerfile 与 Build

需要理解：

- base image；
- multi-stage build；
- build args；
- cache 使用；
- COPY / ADD 范围；
- `.dockerignore`；
- package manager；
- runtime user；
- exposed ports；
- healthcheck；
- secret 泄露风险；
- image 体积风险；
- platform / multi-arch。

AI 应该能回答：

```text
这个 Dockerfile 为什么 build 慢？
为什么镜像这么大？
为什么构建缓存没有命中？
为什么容器里缺依赖？
这个 Dockerfile 有没有安全风险？
```

#### Docker Compose

Compose 是最终产品的重点。

需要理解：

- compose 文件路径；
- compose project name；
- services；
- depends_on；
- ports；
- env_file；
- environment；
- volumes；
- networks；
- profiles；
- healthcheck；
- restart policy；
- build context；
- image；
- override 文件；
- resolved config。

ProjectPilot 必须优先使用：

```text
docker compose config
```

来读取解析后的最终配置，而不是只靠手写 YAML 解析。

AI 应该能做：

- 生成服务拓扑；
- 判断 service 之间依赖关系；
- 判断重启某个 service 的影响；
- 判断 compose up 是否会重建容器；
- 判断 compose down 是否会影响 volume；
- 判断缺少哪些 env；
- 判断宿主机端口是否冲突；
- 判断生产服务是否会中断；
- 生成 compose 部署计划。

#### Network / Volume / Registry

Network 需要理解：

- network 类型；
- connected containers；
- aliases；
- IPAM；
- service 之间是否能互通；
- 端口绑定；
- host 网络风险。

Volume 是最高风险区域之一，需要理解：

- volume 名称；
- 挂载路径；
- 是否被容器使用；
- 是否绑定数据库；
- 是否是匿名 volume；
- 是否有备份；
- 最近修改时间；
- 大小；
- 删除影响。

默认规则：

```text
未知 volume 不能自动删除。
数据库 volume 不能自动删除。
生产 volume 不能自动删除。
删除 volume 必须强确认。
```

Registry 需要理解：

- registry 登录状态；
- repository；
- tag 策略；
- digest；
- latest / prod / stable tag 风险；
- push 权限；
- image provenance；
- 是否覆盖已有 tag。

#### Docker 后端数据模型

Docker 能力不能只保存命令文本，必须保存结构化状态和执行证据。

#### DockerSnapshot

```text
DockerSnapshot
  id
  project_id
  server_id
  executor_id
  captured_at
  daemon_status
  docker_version
  compose_version
  context
  containers
  images
  networks
  volumes
  compose_projects
  resource_usage
  errors
```

#### ComposeProjectSnapshot

```text
ComposeProjectSnapshot
  id
  docker_snapshot_id
  project_name
  project_path
  compose_files
  resolved_config
  services
  networks
  volumes
  ports
  env_files
  risks
```

#### DockerPlan

```text
DockerPlan
  id
  goal
  project_id
  server_id
  target_path
  generated_by
  status
  risk
  steps
  required_approvals
  rollback_strategy
  created_at
```

每一步：

```text
DockerPlanStep
  id
  plan_id
  order
  command_template
  command_args
  risk
  reason
  expected_effect
  rollback_hint
  requires_approval
```

#### DockerOperationLog

```text
DockerOperationLog
  id
  plan_id
  step_id
  approval_id
  executor_id
  server_id
  command_template
  started_at
  finished_at
  exit_code
  stdout_summary
  stderr_summary
  before_snapshot_id
  after_snapshot_id
  status
```

#### DockerRollbackPlan

```text
DockerRollbackPlan
  id
  operation_id
  rollbackable
  rollback_level
  steps
  irreversible_warnings
  requires_approval
```

回滚等级：

```text
full       可完整回滚
partial    部分可回滚
manual     需要人工处理
none       不可回滚
```

#### Docker Executor 执行边界

Executor 执行 Docker 任务时必须校验：

```text
task.plan_id 存在
task.plan_version 是 approved
task.approval_id 存在
task.command_template 在允许列表内
task.target_path 在 allowed-root 内
task.server_id 在 Executor 权限范围内
task.risk 不超过用户批准范围
```

Executor 不能执行：

- 未批准计划；
- 临时插入命令；
- 超出 allowed-root 的 compose 文件；
- 任意 shell 字符串；
- 未模板化的 Docker 命令；
- 未经强确认的高风险 Docker 操作。

命令应该使用模板，例如：

```text
docker_compose_ps
docker_compose_logs
docker_compose_up_service
docker_compose_restart_service
docker_pull_image
docker_build_image
docker_container_restart
docker_image_prune
```

而不是直接保存：

```text
docker compose up -d app && rm -rf /
```

#### Docker 界面设计

Docker 总览：

```text
Docker

Servers:
  dev-server       running    1 warning
  prod-server      running    healthy
  gpu-server       running    image outdated

Containers:
  running          18
  unhealthy        1
  restarting       1
  exited           4

Images:
  total            42
  unused           8
  outdated         3

Volumes:
  total            12
  data-critical    4
  cleanup-risk     2
```

项目 Docker 页：

```text
Project: Blog API
Server: dev-server

Compose project: blog-api

Services:
  app          restarting     exit 1
  postgres    healthy        volume: postgres_data
  redis       healthy
  nginx       running         port 80 -> 8080

AI Summary:
  app 缺少 DATABASE_URL，导致启动失败。
  postgres_data 是持久化数据卷，禁止自动删除。
  建议修复 .env 后只重启 app service。

[查看日志] [生成修复计划] [审批执行] [生成回滚计划]
```

DockerPlan 审批页：

```text
DockerPlan #81

目标：修复 dev-server app 容器反复重启

步骤：
1. docker compose ps                         low
2. docker compose logs --tail=200 app         low
3. 检查 .env DATABASE_URL                     low
4. 写入 DATABASE_URL                          medium
5. docker compose up -d app                   medium
6. docker compose ps app                      low

风险：
- 不会执行 compose down
- 不会删除 volume
- 只重启 app service

回滚：
- 可恢复 .env 备份
- 可重新启动旧 app 容器

[批准执行] [编辑计划] [拒绝]
```

#### Docker 典型工作流

Docker Doctor：

```text
用户点击 Docker Doctor
  ↓
Executor 采集 DockerSnapshot
  ↓
后端保存快照
  ↓
AI 分析容器、镜像、Compose、volume、network、日志
  ↓
输出健康报告
```

修复 restarting 容器：

```text
发现 app restarting
  ↓
读取 exit code 和 logs
  ↓
AI 判断缺少 env
  ↓
生成 DockerPlan
  ↓
用户批准修改 .env 和重启 app
  ↓
Executor 执行
  ↓
保存 before / after DockerSnapshot
  ↓
AI 总结 app 是否恢复
```

安全更新 Compose 服务：

```text
用户要求更新 dev-server
  ↓
AI 检查 compose config
  ↓
AI 检查当前 image tag 和 registry digest
  ↓
AI 检查 volume 和依赖服务
  ↓
AI 生成更新计划
  ↓
用户批准
  ↓
Executor 执行 docker compose pull app
  ↓
Executor 执行 docker compose up -d app
  ↓
AI 检查 healthcheck 和 logs
```

删除 volume 前保护：

```text
用户尝试删除 volume
  ↓
系统检查是否被容器挂载
  ↓
系统检查是否疑似数据库 volume
  ↓
系统检查是否有备份
  ↓
如果无备份，默认 blocked
  ↓
AI 给出备份建议
```

#### Docker CLI 和 TUI

最终 CLI：

```bash
projectpilot docker doctor .
projectpilot docker status .
projectpilot docker compose-check .
projectpilot docker logs-summary .
projectpilot docker plan .
projectpilot docker approve plan_81
projectpilot docker execute plan_81 --apply
projectpilot docker audit .
```

Rust TUI 需要支持：

- Docker 总览；
- server / project 切换；
- container 列表；
- compose service 列表；
- 日志摘要；
- DockerPlan 审批；
- 执行历史；
- 回滚审批。

TUI 示例：

```text
ProjectPilot Docker
────────────────────────────────────────────────────────
Server       Compose       Service      State
dev-server   blog-api      app          restarting
dev-server   blog-api      postgres     healthy
prod-server  web           nginx        running

[Enter] Detail   [l] Logs   [p] Plan   [a] Approve   [q] Quit
```

### 5.6 AI 对话式运维

最终用户可以直接问：

```text
为什么 dev-server 不能部署？
```

AI 回答：

```text
我检查了 dev-server：

1. SSH 连接正常。
2. Git 分支 main 落后远端 2 个提交。
3. 工作区干净，可以 fast-forward pull。
4. Docker 正在运行。
5. 磁盘占用 68%，正常。

建议先执行：
git pull --ff-only

这是中风险操作，需要你确认。
```

用户点：

```text
[确认执行]
```

Executor 执行后上传结果。

AI 继续说明：

```text
已同步到最新提交。现在 dev-server 与 origin/main 一致。
```

### 5.7 审计和历史

所有操作都入库。

记录：

- 谁发起；
- AI 生成了什么计划；
- 用户是否确认；
- 哪台机器执行；
- 哪台服务器；
- 执行了什么任务；
- 命令模板；
- 风险等级；
- stdout 摘要；
- stderr 摘要；
- 执行前状态；
- 执行后状态；
- 时间。

用户可以查看：

```text
今天 14:32
eddz 确认执行 dev-server git pull --ff-only
结果：成功
提交：abc123 -> def456
```

### 5.8 AI 计划审批与回滚中心

最终产品需要一个专门的计划审批界面。

当 AI 生成计划后，前端展示：

```text
AI 执行计划：同步 dev-server 并检查运行环境

步骤：
1. git fetch                         low
2. git pull --ff-only                medium
3. npm install                       medium
4. docker compose restart app        high

回滚准备：
1. 记录当前 commit: abc123
2. 备份 package-lock.json
3. 记录当前 Docker 容器状态

[批准执行] [编辑计划] [拒绝]
```

用户点击“编辑计划”后，可以：

- 删除某一步；
- 调整顺序；
- 修改目标服务器；
- 修改项目路径；
- 将某一步改为只检测不执行；
- 添加备注；
- 要求 AI 重新生成计划。

用户批准后，系统生成：

```text
ApprovedExecutionPlan
```

Executor 只能执行这个已批准计划，不能临时扩展命令。

#### 5.8.1 执行时的保护机制

执行时必须满足：

- plan_id 存在；
- plan_version 已批准；
- approving_user 存在；
- 每一步都在白名单或风险许可范围内；
- 每一步都有执行前快照；
- 中高风险步骤有确认记录；
- Executor 执行结果逐步上传；
- 失败后停止后续高风险步骤。

#### 5.8.2 回滚入口

执行历史页要显示：

```text
本次执行可回滚：部分可回滚

可回滚步骤：
1. git pull --ff-only -> 回到 abc123
2. package-lock.json -> 恢复备份

不可完全回滚：
1. docker compose restart app
```

回滚也必须走审批：

```text
AI 生成回滚计划
  ↓
用户确认
  ↓
Executor 执行回滚
  ↓
保存回滚历史
```

## 6. 最终界面设计

### 6.1 Web 前端

页面：

```text
Dashboard
Projects
Servers
Executors
AI Assistant
Operations
Settings
```

#### Dashboard

展示全局状态：

- 项目总数；
- 在线 Executor；
- 服务器健康；
- Git 异常；
- 环境异常；
- 最近操作；
- AI 风险提醒。

#### Projects

展示项目列表：

```text
ProjectPilot     attention
Blog API         healthy
GPU Lab          blocked
```

#### Project Detail

展示：

- 本地状态；
- 远程服务器状态；
- Git 对比；
- 环境对比；
- AI 建议；
- 可执行操作；
- 待审批计划；
- 最近回滚入口。

#### Servers

展示：

- SSH Host；
- 连接状态；
- 绑定项目；
- 最近检测时间；
- 环境状态。

#### AI Assistant

对话式入口：

```text
帮我检查 ProjectPilot 是否可以部署。
为什么 prod-server 状态 blocked？
生成 dev-server 的环境修复计划。
```

#### Plans

展示 AI 计划和用户批准状态：

```text
Plan #42  dev-server 环境修复

状态：等待批准
风险：medium + high
生成者：AI
审批人：未审批

[查看计划] [编辑计划] [批准执行] [拒绝]
```

#### Rollbacks

展示可回滚历史：

```text
Execution #18

状态：成功
可回滚：部分可回滚
执行人：AI via eddz approval

[查看历史] [生成回滚计划]
```

### 6.2 桌面 GUI 主应用

桌面 GUI 主应用是 ProjectPilot 的本机图形化入口，不等于 Executor 本身。

它面向：

- 不想每次打开浏览器的个人用户；
- 需要本机原生窗口、菜单、通知和托盘状态的用户；
- 需要同时管理本机项目和远程服务器的开发者；
- 希望把 Executor 配置、项目控制台和审批中心放在一个桌面应用里的用户。

桌面 GUI 主应用负责：

- 登录主机后端；
- 展示项目总览；
- 展示 Git / Docker / 环境状态；
- 展示 AI 对话；
- 展示计划审批中心；
- 展示执行历史和回滚入口；
- 管理 Executor 的启动、停止和状态；
- 管理 SSH Host 扫描和连接测试；
- 通过系统通知提醒高风险审批；
- 在本机安全地打开项目目录、终端或日志文件。

最终桌面 GUI 主应用窗口：

```text
ProjectPilot Desktop

Sidebar:
  Dashboard
  Projects
  Servers
  Git
  Docker
  Plans
  History
  Settings

Main:
  ProjectPilot              attention
  dev-server                Docker healthy / Git behind 2
  prod-server               healthy

Executor:
  Mode                      Central Executor
  Executor                  host-executor running
  SSH Hosts                 3 connected

[Ask AI] [Detect All] [Review Plans] [Open Executor Settings]
```

桌面 GUI App 和 Web 前端展示同一套业务数据，但体验不同：

```text
Web 前端：适合团队共享、远程访问、浏览器打开。
桌面 GUI App：适合个人日常使用、本机通知、Executor 管理。
```

桌面 GUI App 可以管理 Central Executor 或 Local Executor，但不能绕过后端审批和审计。

### 6.3 Executor 执行器层

Executor 执行器层不是主要业务前端，而是 AI 和服务器之间的“手”。

它负责：

- 保存或读取 SSH config；
- 管理多台 SSH Host；
- 支持免密登录；
- 测试连接；
- 复用 SSH 连接；
- 执行已批准的 Git / Docker / 环境命令；
- 采集执行前后快照；
- 上传 stdout / stderr / exit code；
- 阻止未批准或越权命令；
- 显示 Executor 运行状态；
- 显示最近任务；
- 必要时弹出确认窗口。

Executor 有两种形态：

```text
Central Executor
  部署在主机后端所在机器。
  读取主机的 ~/.ssh/config 或后端托管的 SSH Host 配置。
  适合主机可以直连所有服务器的场景。

Local Executor
  部署在用户本机或内网机器。
  读取本机 ~/.ssh/config、ssh-agent、Keychain。
  适合私钥不出本机、主机不能直连内网服务器的场景。
```

最终 Executor 设置窗口：

```text
ProjectPilot Executor

主机连接：Connected
Mode：Central Executor
Executor ID：host-executor-01
Allowed Root：/srv /opt /home/deploy

SSH Servers:
  dev-server      connected
  prod-server     connected
  gpu-lab         failed

Recent Tasks:
  detect_git dev-server        success
  detect_environment prod      success
  apply_remote_git_operation   waiting confirmation

[Start Executor] [Stop Executor] [Scan SSH Config] [Test All] [Open Web]
```

### 6.4 Rust TUI 终端端

终端端不是简单 CLI，而是完整的交互式 TUI。

它面向：

- 长期在终端工作的开发者；
- 不方便打开 GUI 的服务器环境；
- 需要键盘快速审批计划的高级用户；
- 希望在 SSH session 里管理项目状态的用户。

入口：

```bash
projectpilot-tui
```

或：

```bash
projectpilot tui
```

TUI 负责：

- 查看项目状态；
- 查看服务器状态；
- 查看 AI 计划；
- 编辑 AI 计划；
- 批准 / 拒绝计划；
- 执行已批准计划；
- 查看执行历史；
- 生成回滚计划；
- 批准回滚。

终端主界面：

```text
ProjectPilot
────────────────────────────────────────────────────────
Projects           Servers            Plans

ProjectPilot       dev-server         Plan #42 waiting
Blog API           prod-server        healthy
GPU Lab            gpu-lab            blocked

[Enter] View   [a] Approve   [e] Edit   [r] Rollback   [q] Quit
```

AI 计划审批界面：

```text
AI Plan #42: Sync dev-server
────────────────────────────────────────────────────────
1. git fetch                         low
2. git pull --ff-only                medium
3. npm install                       medium
4. docker compose restart app        high

Rollback preparation:
- before_commit: abc123
- backup package-lock.json
- capture docker state

[a] Approve   [e] Edit   [d] Delete Step   [m] Modify   [q] Back
```

TUI 与桌面 GUI App 的关系：

```text
桌面 GUI App 适合看全局、配置 Executor、接收本机通知。
TUI 适合终端里快速处理计划、审批、执行、回滚。
CLI 适合脚本和 CI。
```

三者必须复用同一套后端 API、计划模型、权限模型和审计模型，不能各自实现一套执行逻辑。

## 7. 最终权限模型

权限分四层。

### 7.1 用户权限

控制用户能否：

- 查看项目；
- 查看服务器；
- 创建检测任务；
- 确认执行任务；
- 修改 AI 计划；
- 批准 AI 计划；
- 批准回滚计划；
- 管理 Executor；
- 查看审计。

### 7.2 Executor 权限

控制 Executor 能否：

- 执行本地检测；
- 读取 SSH config；
- 连接哪些服务器；
- 执行哪些任务类型；
- 访问哪些路径。

Executor 权限还要区分模式：

```text
Central Executor
  适合集中管理服务器。
  权限由后端管理员配置。
  可以统一维护 SSH Host、密钥路径、服务器标签和允许命令。

Local Executor
  适合本机和内网环境。
  权限由本机用户授权。
  默认复用本机 ~/.ssh/config、ssh-agent 和 allowed-root。
```

### 7.3 命令权限

控制命令风险：

```text
low      自动允许
medium   用户确认
high     强确认 / 管理员确认
blocked  禁止
```

### 7.4 计划权限

控制 AI 计划生命周期：

```text
draft       AI 已生成，未批准
edited      用户修改过，未批准
approved    用户批准，可执行
running     正在执行
succeeded   执行成功
failed      执行失败
rolled_back 已执行回滚
rejected    用户拒绝
```

只有 `approved` 状态的计划可以进入执行队列。

Executor 接到任务时必须校验：

```text
task.plan_id 存在
task.plan_version 是已批准版本
task.approval_id 存在
task.command 与批准计划一致
task.executor_id 在允许范围内
task.server_id 在允许范围内
task.path 在 allowed-root 内
```

当前 Executor 已落地的 Git 执行任务：

```text
apply_git_operation
apply_remote_git_operation
```

执行规则：

- 必须包含 `approved: true`；
- 本地任务必须落在 `allowed-root` 内；
- 远程任务必须使用 SSH Host 和绝对 `project_path`；
- 不接受 raw shell 命令；
- 后端可以传 `expected_command`，Executor 会将它与本地生成的白名单命令逐字匹配；
- 本地执行复用智能 Git planner；
- 远程执行使用白名单 Git operation + params 生成 SSH 命令；
- 执行结果必须包含 stdout、stderr、exit code 和执行前后 Git 快照。

## 8. 最终数据流

### 8.1 检测全部项目

```text
用户点击检测全部
  ↓
后端创建多个检测任务
  ↓
Executor 获取任务
  ↓
Executor 本地/SSH 执行检测
  ↓
Executor 上传结果
  ↓
后端保存 GitStatus / EnvironmentSnapshot
  ↓
AI 生成总结
  ↓
前端更新页面
```

### 8.2 执行安全 Git Pull

```text
用户点击同步 dev-server
  ↓
AI 生成 apply_remote_git_operation 任务
  ↓
后端校验：
    working tree clean
    ahead = 0
    behind > 0
    upstream exists
  ↓
用户确认
  ↓
Executor SSH 执行 git pull --ff-only
  ↓
上传结果
  ↓
后端保存 OperationLog
  ↓
重新检测 Git 状态
  ↓
AI 总结结果
```

### 8.3 AI 计划批准后执行

```text
用户提出目标
  ↓
AI 生成 ExecutionPlan 草稿
  ↓
后端标记每一步风险和回滚策略
  ↓
前端展示计划
  ↓
用户选择：
    直接批准 / 修改后批准 / 拒绝
  ↓
后端保存 ApprovedExecutionPlan
  ↓
Executor 获取已批准任务
  ↓
Executor 执行前生成快照
  ↓
Executor 逐步执行
  ↓
每一步结果上传后端
  ↓
后端更新 OperationLog
  ↓
AI 生成执行总结
```

### 8.4 执行失败后回滚

```text
执行失败
  ↓
系统停止后续危险步骤
  ↓
AI 根据执行前快照生成回滚计划
  ↓
用户查看并批准回滚计划
  ↓
Executor 执行回滚
  ↓
后端保存 RollbackLog
  ↓
AI 总结恢复结果
```

### 8.5 遇到分叉

```text
检测到 ahead > 0 且 behind > 0
  ↓
系统标记 blocked
  ↓
禁止自动 push / pull
  ↓
AI 解释分叉原因
  ↓
AI 生成分叉处理方案：
  1. merge 方案
  2. rebase 私有分支方案
  3. cherry-pick 方案
  4. 放弃某部分改动方案
  ↓
用户选择一个方案并审批
  ↓
Executor 在本机或临时 worktree 中预演
  ↓
如果无冲突，生成真实执行计划
  ↓
如果有冲突，AI 解释冲突并给出可审查 patch
  ↓
用户批准后才写入冲突解决结果
```

### 8.6 AI 辅助分支合并

```text
用户选择 source 分支和 target 分支
  ↓
AI 读取分支关系、merge-base、提交列表、文件差异
  ↓
AI 判断：
    是否 fast-forward
    是否会产生 merge commit
    是否涉及公共历史
    是否可能冲突
    是否影响部署文件
  ↓
AI 生成 MergePlan
  ↓
后端标记风险等级
  ↓
用户批准预演
  ↓
Executor 创建临时 worktree 或干净检查点
  ↓
执行 merge / rebase / cherry-pick 预演
  ↓
上传冲突文件和结果
  ↓
AI 生成解释和解决建议
  ↓
用户批准真实执行或放弃
```

### 8.7 AI 辅助 Docker 运维

```text
用户提出 Docker 目标：
  修复容器
  更新镜像
  重启服务
  清理资源
  检查 Compose 部署
  ↓
AI 读取 DockerSnapshot / ComposeConfig / OperationLog
  ↓
AI 判断：
    daemon 是否正常
    容器是否 unhealthy / restarting / exited
    镜像是否过旧
    日志是否有明确错误
    volume 是否可能包含持久化数据
    network / port 是否冲突
    操作是否影响生产服务
  ↓
AI 生成 DockerPlan
  ↓
后端标记风险等级
  ↓
用户批准只读诊断或变更执行
  ↓
Executor 通过本机或 SSH 执行 Docker / Compose 命令
  ↓
执行前后保存 DockerSnapshot
  ↓
AI 总结结果，并在可回滚时生成回滚计划
```

### 8.8 Central Executor 执行链路

```text
用户在 Web / Desktop / TUI / CLI 发起目标
  ↓
后端调用 AI Planner 生成结构化计划
  ↓
用户批准计划
  ↓
后端写入 ApprovedPlan 和 ExecutorTask
  ↓
Central Executor 从队列获取任务
  ↓
Central Executor 复用 SSH config / 连接池
  ↓
Central Executor 在多台服务器上执行 Git / Docker / 环境命令
  ↓
Executor 上传快照、日志、退出码和状态
  ↓
数据库保存历史
  ↓
AI 可选调用一次生成总结
```

这个链路里只有一个 AI。Executor 不是 AI，它只是 SSH 连接管理器、命令执行器、快照采集器和审计记录器。

## 9. 最终技术选型

### 9.1 后端

推荐：

```text
FastAPI / Django / Spring Boot 均可
PostgreSQL
Redis 队列
WebSocket / SSE 用于实时状态
```

后端核心模块：

- 项目模块；
- 服务器模块；
- Executor 模块；
- 任务模块；
- AI 计划模块；
- 审批模块；
- 回滚模块；
- GitStatus 模块；
- GitPlan 模块；
- DockerStatus 模块；
- DockerPlan 模块；
- EnvironmentSnapshot 模块；
- OperationLog 模块；
- AI 分析模块；
- 权限模块。

### 9.2 桌面 GUI 主应用

推荐：

```text
macOS: SwiftUI 原生 App
Windows: Tauri / .NET / Electron
Linux: Tauri / AppImage / Flatpak
```

第一版可以先做 macOS SwiftUI，因为当前用户环境在 macOS，且需要原生窗口、系统通知、菜单栏和 Executor 管理。

桌面 GUI 主应用通过后端 API 获取数据，不直接操作远程服务器。真实执行仍然由后端创建任务，Executor 获取任务并执行。

桌面 GUI 主应用需要包含：

- 登录和后端连接；
- 项目总览；
- Git 全功能控制台；
- Docker 全功能控制台；
- AI 对话；
- 计划审批；
- 执行历史；
- 回滚入口；
- Executor 状态；
- SSH Host 管理；
- 设置页。

### 9.3 Executor 执行器

推荐：

```text
Central Executor: 后端同机进程 / Worker / systemd service
Local Executor: macOS LaunchAgent / Windows Service / Linux systemd user service
SSH: OpenSSH + ControlMaster / ControlPersist
任务队列: Redis / PostgreSQL queue / Celery / RQ
```

Executor 内部模块：

```text
SSHConfigStore
SSHConnectionPool
CommandTemplateRegistry
GitExecutor
DockerExecutor
EnvironmentExecutor
SnapshotCollector
AuditUploader
RollbackPreparer
```

Central Executor 部署在主机后端侧，是服务器集中管理的主模式。

Local Executor 部署在用户本机或内网机器，是私钥不出本机、主机不能直连内网时的补充模式。

桌面 GUI 主应用可以启动和管理 Local Executor；后端管理界面可以启动和管理 Central Executor。

### 9.4 Rust TUI

终端交互端使用 Rust 实现。

推荐技术栈：

```text
Rust
ratatui
crossterm
reqwest
serde
tokio
```

选择 Rust 的原因：

- 单文件二进制，方便分发；
- 终端 UI 性能稳定；
- 适合长时间运行；
- 键盘交互体验好；
- 跨平台能力强；
- 与服务器环境兼容度高；
- 可以和桌面 GUI App / 后端共享同一套 HTTP 协议。

TUI 不直接绕过后端执行命令。

TUI 应该调用：

```text
GET /projects
GET /servers
GET /plans
POST /plans/{plan_id}/approve
POST /plans/{plan_id}/reject
PATCH /plans/{plan_id}
POST /executions/{execution_id}/rollback-plan
```

执行仍然走：

```text
后端审批记录
  ↓
Executor 获取任务
  ↓
SSH 执行器
  ↓
审计日志
```

### 9.5 CLI

CLI 仍然需要保留，但定位不同。

CLI 适合：

- 脚本化；
- CI；
- 快速查询；
- 非交互命令；
- 自动化接入。

示例：

```bash
projectpilot git doctor .
projectpilot executor status
projectpilot plan approve plan_42
projectpilot execution rollback exec_18
```

### 9.6 SSH 执行

推荐：

```text
第一版：调用系统 ssh 命令
第二版：封装 SSH 执行器
第三版：支持 ControlMaster / ControlPersist 连接复用
```

不推荐第一版直接引入复杂 SSH 库。

## 10. 最终版本路线

路线按“先看清 -> 再执行 -> 再复杂协作 -> 再团队化 -> 再平台化”推进。

| 版本 | 目标 | 必做范围 | 暂不做 |
| --- | --- | --- | --- |
| V1 个人可用 | 一个人能看清本机和远程项目状态 | 桌面 GUI、Central Executor、Local Executor、SSH 扫描、连接测试、本地/远程 Git 检测、远程环境检测、基础 Web 展示、AI 总结 | 自动修改代码、自动部署、复杂 Git 操作 |
| V2 安全执行 | 用户批准后执行低风险操作 | `git fetch`、`pull --ff-only`、安全 `push`、Docker 只读检测、AI 计划审批、用户编辑计划、执行前后快照、审计、基础回滚建议、TUI 审批 | `merge/rebase/cherry-pick` 自动执行、容器重启、镜像构建、Compose 变更 |
| V3 复杂运维 | AI 能处理复杂 Git、Docker、环境问题 | merge/rebase/cherry-pick 计划、worktree 预演、冲突解释、Dockerfile/Compose 分析、logs 分析、build/pull/restart 计划、环境修复计划、中风险确认执行 | 无审批高风险操作、生产变更自动执行 |
| V4 团队协作 | 团队共同管理项目和服务器 | 多用户、多角色、项目权限、服务器权限、团队审批、PR/MR 摘要、受保护分支策略、生产容器审批、registry 权限 | 跨组织平台化、自动巡检闭环 |
| V5 生产平台 | 成为团队级 AI DevOps 控制台 | CI/CD、GitHub/GitLab、监控告警、自动健康巡检、部署前检查、多平台 Executor、多平台桌面 App、Web/GUI/CLI/TUI 一致 | 无边界自动运维 |

最短落地顺序：

```text
V1 只读看清楚
V2 低风险可执行
V3 复杂操作先计划后执行
V4 团队审批
V5 生产平台化
```

## 11. 最终产品边界

ProjectPilot 应该做：

- 帮用户看清项目状态；
- 帮用户理解 Git、Docker 和服务器环境问题；
- 帮用户生成安全操作计划；
- 帮用户执行被允许、被确认的计划版本；
- 支持用户修改 AI 计划后再执行；
- 提供 Web / GUI / CLI / TUI 多入口，且共享同一套后端权限和审计；
- 覆盖 Git 和 Docker 的完整能力面，但按风险分层执行；
- 保存执行前后快照；
- 为可回滚操作提供回滚入口；
- 帮团队追踪所有历史。

ProjectPilot 不应该做：

- 绕过用户确认；
- 私自上传 SSH 私钥；
- 默认执行危险命令；
- 执行未批准或已被用户修改但未重新批准的计划；
- 临时添加批准计划之外的命令；
- 声称所有操作都能完整回滚；
- 未经批准替用户自动解决复杂冲突；
- 未经批准改写公共 Git 历史；
- 未经批准停止、删除或重建 Docker 生产容器；
- 未经批准删除 Docker volume 或执行 prune；
- 让 AI 无限制运行 shell；
- 删除或覆盖用户代码。

## 12. 最终结论

最终 ProjectPilot 应该做成：

```text
一个同时提供 Web 控制台、桌面 GUI App、Rust TUI、CLI 和 Executor 执行层的 AI 项目控制台。
```

用户感受到的是：

```text
我打开 ProjectPilot，就能知道所有项目和服务器是否正常。
AI 会告诉我哪里有问题、为什么有问题、下一步怎么做。
AI 生成的计划我可以直接批准，也可以修改后再批准。
批准后的计划可以由 AI 自动执行，但每一步都有历史记录。
可回滚的操作会提供回滚入口，不可回滚的操作会提前说明。
安全操作可以一键批准，危险操作必须强确认。
```

系统内部是：

```text
Web 前端负责展示
桌面 GUI App 负责本机图形化使用、通知和 Executor 管理
Rust TUI 负责终端交互、计划审批和回滚入口
CLI 负责脚本化自动化
AI Planner 负责分析、决策、计划和回滚建议
后端负责 API、调度、权限、审批和状态流转
数据库负责历史记录、审计证据和快照
Executor 负责 SSH 连接、Git/Docker/环境命令执行和结果采集
远程服务器只接受受控任务
```

一句话终局：

```text
ProjectPilot = AI 决策大脑 + 后端神经系统 + 数据库历史记录 + Web 控制台 + 桌面 GUI App + Rust TUI + CLI + Executor 执行器 + Git/Docker/环境安全控制台。
```
