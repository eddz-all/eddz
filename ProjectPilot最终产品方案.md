# ProjectPilot 最终产品方案

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

ProjectPilot 最终由四个部分组成：

```text
1. Web 前端
2. 主机后端 + 数据库 + AI
3. macOS / Windows / Linux 本机 Agent App
4. 远程服务器 SSH 执行层
```

整体结构：

```text
┌──────────────────────────────┐
│           Web 前端            │
│ 项目面板 / 服务器面板 / AI 对话 │
└───────────────┬──────────────┘
                │
                ▼
┌──────────────────────────────┐
│     主机后端 / 数据库 / AI      │
│ 任务调度 / 权限 / 审计 / 分析    │
└───────────────┬──────────────┘
                │ 轮询任务 / 上传结果
                ▼
┌──────────────────────────────┐
│       本机 ProjectPilot App    │
│ SSH 配置 / 私钥 / Agent 执行器  │
└───────────────┬──────────────┘
                │ SSH
                ▼
┌──────────────────────────────┐
│          远程服务器集群         │
│ Git / Docker / 环境 / 项目进程  │
└──────────────────────────────┘
```

## 3. 用户最终怎么使用

### 3.1 第一次使用

用户安装 ProjectPilot App。

打开后看到原生桌面窗口：

```text
ProjectPilot Agent

Backend URL:  http://主机后端地址
Token:        ********
Machine ID:   eddz-mac
Allowed Root: /Users/eddz/work

[连接主机] [扫描 SSH 配置] [测试连接]
```

用户只需要做三件事：

1. 填后端地址；
2. 填后端生成的 Agent token；
3. 选择本机项目根目录。

然后点击：

```text
连接主机
```

### 3.2 添加远程服务器

App 自动扫描：

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

ProjectPilot 使用本机 SSH 配置测试，不上传私钥。

### 3.3 绑定项目

在 Web 前端或 App 中绑定：

```text
项目：ProjectPilot
本地路径：/Users/eddz/work/engine
远程 dev-server 路径：/srv/projectpilot
远程 prod-server 路径：/opt/projectpilot
Git remote：git@example.com:team/projectpilot.git
```

### 3.4 日常使用

用户打开 Web 前端看到：

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
Agent 通过 SSH 执行
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
Agent 只执行这个被批准的版本
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

## 5.1 项目总览

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

## 5.2 Git 智能管理

最终 Git 能力包括：

- 本地 Git 检测；
- 远程 Git 检测；
- branch / upstream / remote 检测；
- ahead / behind / diverged 判断；
- dirty 文件分类；
- commit plan；
- safe add；
- safe commit；
- safe pull；
- safe push；
- Git 操作审计；
- 冲突解释；
- 分叉解释；
- 部署前 Git 检查。

### Git 安全规则

允许自动执行：

```text
git status
git log
git diff
git fetch
```

允许在条件满足时执行：

```text
git pull --ff-only
git push
git add
git commit
```

默认禁止：

```text
git reset --hard
git clean -fd
git push --force
git rebase
git merge
```

这些高风险命令只能作为 AI 建议，不自动执行。

## 5.3 远程服务器管理

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

## 5.4 远程环境配置

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

## 5.5 AI 对话式运维

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

Agent 执行后上传结果。

AI 继续说明：

```text
已同步到最新提交。现在 dev-server 与 origin/main 一致。
```

## 5.6 审计和历史

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

## 5.7 AI 计划审批与回滚中心

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

Agent 只能执行这个已批准计划，不能临时扩展命令。

### 5.7.1 执行时的保护机制

执行时必须满足：

- plan_id 存在；
- plan_version 已批准；
- approving_user 存在；
- 每一步都在白名单或风险许可范围内；
- 每一步都有执行前快照；
- 中高风险步骤有确认记录；
- Agent 执行结果逐步上传；
- 失败后停止后续高风险步骤。

### 5.7.2 回滚入口

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
Agent 执行回滚
  ↓
保存回滚历史
```

## 6. 最终界面设计

## 6.1 Web 前端

页面：

```text
Dashboard
Projects
Servers
Agents
AI Assistant
Operations
Settings
```

### Dashboard

展示全局状态：

- 项目总数；
- 在线 Agent；
- 服务器健康；
- Git 异常；
- 环境异常；
- 最近操作；
- AI 风险提醒。

### Projects

展示项目列表：

```text
ProjectPilot     attention
Blog API         healthy
GPU Lab          blocked
```

### Project Detail

展示：

- 本地状态；
- 远程服务器状态；
- Git 对比；
- 环境对比；
- AI 建议；
- 可执行操作；
- 待审批计划；
- 最近回滚入口。

### Servers

展示：

- SSH Host；
- 连接状态；
- 绑定项目；
- 最近检测时间；
- 环境状态。

### AI Assistant

对话式入口：

```text
帮我检查 ProjectPilot 是否可以部署。
为什么 prod-server 状态 blocked？
生成 dev-server 的环境修复计划。
```

### Plans

展示 AI 计划和用户批准状态：

```text
Plan #42  dev-server 环境修复

状态：等待批准
风险：medium + high
生成者：AI
审批人：未审批

[查看计划] [编辑计划] [批准执行] [拒绝]
```

### Rollbacks

展示可回滚历史：

```text
Execution #18

状态：成功
可回滚：部分可回滚
执行人：AI via eddz approval

[查看历史] [生成回滚计划]
```

## 6.2 桌面 Agent App

桌面 App 不是主要业务前端，而是本机执行控制器。

它负责：

- 登录主机；
- 保存 token；
- 读取 SSH 配置；
- 管理本机 allowed-root；
- 显示 Agent 运行状态；
- 显示最近任务；
- 必要时弹出确认窗口。

最终 App 窗口：

```text
ProjectPilot Agent

主机连接：Connected
Machine ID：eddz-mac
Allowed Root：/Users/eddz/work

SSH Servers:
  dev-server      connected
  prod-server     connected
  gpu-lab         failed

Recent Tasks:
  detect_git dev-server        success
  detect_environment prod      success
  git_pull_ff_only dev-server  waiting confirmation

[Start Agent] [Stop Agent] [Scan SSH Config] [Open Web]
```

## 7. 最终权限模型

权限分三层。

### 7.1 用户权限

控制用户能否：

- 查看项目；
- 查看服务器；
- 创建检测任务；
- 确认执行任务；
- 修改 AI 计划；
- 批准 AI 计划；
- 批准回滚计划；
- 管理 Agent；
- 查看审计。

### 7.2 Agent 权限

控制 Agent 能否：

- 执行本地检测；
- 读取 SSH config；
- 连接哪些服务器；
- 执行哪些任务类型；
- 访问哪些路径。

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

Agent 接到任务时必须校验：

```text
task.plan_id 存在
task.plan_version 是已批准版本
task.approval_id 存在
task.command 与批准计划一致
```

## 8. 最终数据流

### 8.1 检测全部项目

```text
用户点击检测全部
  ↓
后端创建多个检测任务
  ↓
Agent 轮询任务
  ↓
Agent 本地/SSH 执行检测
  ↓
Agent 上传结果
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
AI 生成 git_pull_ff_only 任务
  ↓
后端校验：
    working tree clean
    ahead = 0
    behind > 0
    upstream exists
  ↓
用户确认
  ↓
Agent SSH 执行 git pull --ff-only
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
Agent 拉取已批准任务
  ↓
Agent 执行前生成快照
  ↓
Agent 逐步执行
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
Agent 执行回滚
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
给出人工处理建议
```

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
- Agent 模块；
- 任务模块；
- AI 计划模块；
- 审批模块；
- 回滚模块；
- GitStatus 模块；
- EnvironmentSnapshot 模块；
- OperationLog 模块；
- AI 分析模块；
- 权限模块。

### 9.2 Agent App

推荐：

```text
macOS: SwiftUI 原生 App
Windows: 后续可做 Tauri / .NET / Electron
Linux: 后续可做 Tauri / AppImage
```

当前 macOS 版本：

```text
SwiftUI 窗口
调用本地 Python Agent
读取 ~/.projectpilot/agent.json
使用系统 ssh
```

### 9.3 SSH 执行

推荐：

```text
第一版：调用系统 ssh 命令
第二版：封装 SSH 执行器
第三版：支持 ControlMaster / ControlPersist 连接复用
```

不推荐第一版直接引入复杂 SSH 库。

## 10. 最终版本路线

## V1：个人可用版

目标：

```text
一个人可以用 ProjectPilot 管理自己的本机项目和远程服务器。
```

能力：

- macOS App；
- 后端连接；
- SSH Host 扫描；
- 连接测试；
- 本地 Git 检测；
- 远程 Git 检测；
- 远程环境检测；
- Web 状态展示；
- AI 总结。

## V2：安全执行版

目标：

```text
允许用户确认后执行安全 Git 操作。
```

能力：

- git fetch；
- git pull --ff-only；
- git push safe；
- AI 计划审批；
- 用户编辑计划；
- 远程操作审计；
- 执行前后快照；
- 基础回滚计划；
- 风险分级；
- 用户确认；
- 操作前后状态对比。

## V3：环境配置版

目标：

```text
AI 能生成远程环境修复计划，并执行低/中风险步骤。
```

能力：

- Node / Python / Docker 检测；
- 依赖安装建议；
- Docker Compose 检查；
- 配置文件缺失检查；
- 环境修复计划；
- 中风险步骤确认执行；
- 高风险步骤强确认；
- 失败后生成回滚建议。

## V4：团队协作版

目标：

```text
一个团队可以共同管理多个项目和服务器。
```

能力：

- 多用户；
- 多角色；
- 项目权限；
- 服务器权限；
- 操作审批；
- 审计日志；
- 团队 AI 报告。

## V5：生产平台版

目标：

```text
成为团队级 AI DevOps 控制台。
```

能力：

- CI/CD 集成；
- GitHub / GitLab 集成；
- 监控集成；
- 告警；
- 自动健康巡检；
- 部署前检查；
- 回滚建议；
- 多平台 Agent。

## 11. 最终产品边界

ProjectPilot 应该做：

- 帮用户看清项目状态；
- 帮用户理解 Git 和服务器环境问题；
- 帮用户生成安全操作计划；
- 帮用户执行被允许、被确认的计划版本；
- 支持用户修改 AI 计划后再执行；
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
- 替用户自动解决复杂冲突；
- 让 AI 无限制运行 shell；
- 删除或覆盖用户代码。

## 12. 最终结论

最终 ProjectPilot 应该做成：

```text
一个带桌面 Agent 的 AI 项目控制台。
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
后端负责调度、存储、权限、AI
桌面 Agent 负责本机权限和 SSH 执行
远程服务器只接受受控任务
```

一句话终局：

```text
ProjectPilot = AI 大脑 + 项目数据库 + 桌面 Agent + SSH 执行器 + Git/环境安全控制台。
```
