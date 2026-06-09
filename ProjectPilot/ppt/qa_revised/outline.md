# Deck Outline

- File: /home/huancheng/AutoEnv/ProjectPilot/ppt/ProjectPilot_revised.pptx
- Slides: 12

## Slide 1: (No title)

Body:
- POLICY BRIEF
- ProjectPilot
- 多服务器项目环境管理中央控制平台
- 小组成员：封皓宇、韩振友、林炜涵

## Slide 2: (No title)

Body:
- 项目背景：多服务器协作成为常态
- 先讲客观场景：同一个项目往往运行在多台机器上
- 多人协作时，同一个项目可能部署在多台服务器上。
- 不同服务器承担开发、测试、部署、实验等不同角色。
- 项目路径、依赖环境、Git 分支状态经常不一致。
- 团队成员很难快速判断哪台机器上的项目是最新、可运行、安全的。
- FOCUS
- server-a：开发环境，branch=dev，Python 3.10
- server-b：测试环境，branch=main，Python 3.8
- server-c：实验环境，branch=old，Docker 未运行

## Slide 3: (No title)

Body:
- 核心痛点：状态不可见，执行不可控
- 问题从“分散”进一步变成“风险”
- 看不清
- Git 分支、提交、未提交改动难以统一确认。
- Python、Node、Docker、CUDA 版本容易不一致。
- 服务器信息分散，无法形成统一状态视图。
- 管不住，追不回
- 人工逐台 SSH 检查效率低，且容易遗漏。
- 批量 SSH 执行命令存在安全风险。
- 操作过程缺少统一日志，出错后难以定位责任和原因。
- 因此我们需要一个系统，把状态检测、风险分析、任务执行和日志追踪统一起来。

## Slide 4: (No title)

Body:
- 项目目标：统一查看、分析、调度与执行
- ProjectPilot 的定位是中央控制台
- 统一管理
- 管理项目、服务器及项目在各服务器上的真实路径。
- 统一检测
- 检测 Git 状态和运行环境，并聚合多服务器差异。
- 统一执行
- AI 生成计划，用户确认后交由 Executor 受控执行。

## Slide 5: (No title)

Body:
- 总体架构：中央控制 + 分布式执行
- 前端、后端、数据库、Executor 各司其职
- 前端
- 控制台
- 用户查看项目状态，发起检测、AI 分析和执行确认。
- 后端
- 调度与记录
- 统一创建任务、调用 AI、聚合状态、写入日志。
- 数据库
- 系统事实
- 保存项目、服务器、快照、任务和操作日志。
- EXECUTOR
- 本机执行
- 运行在目标服务器，主动轮询任务并回传结果。
- 前端和 Executor 都只访问总后端；总后端是唯一调度中心。

## Slide 6: (No title)

Body:
- 后端：调度中心 + 数据中心
- FastAPI 后端负责统一业务编排
- 01
- Routers
- 提供项目、服务器、检测、AI、执行和日志接口。
- 02
- Services
- 封装检测、执行、AI 计划和 Executor 任务编排。
- 03
- Models
- Project、Server、GitStatus、EnvironmentSnapshot、ExecutorTask 等模型。
- 04
- Database
- SQLite + SQLAlchemy 保存系统状态和执行历史。

## Slide 7: (No title)

Body:
- Executor：服务器主动拉取任务
- 任务状态从 queued 到 running，再到 completed 或 failed
- 1
- 前端发起
- 用户点击检测或确认 AI 计划执行。
- 2
- 后端入队
- 后端创建 ExecutorTask，状态为 queued。
- 3
- 轮询领取
- Executor 调用 POST /executor/poll 获取任务。
- 4
- 执行回传
- Executor 本机执行，再回传 result，后端写库。

## Slide 8: (No title)

Body:
- AI：从分析建议到主动计划
- AI 只生成计划，执行仍由后端约束
- 环境分析：比较多台服务器环境差异并给出风险。
- Git 分析：接入 eddz smart_git，生成 doctor、map、sync plan、commit plan。
- 配置计划：根据源服务器与目标服务器生成配置步骤。
- 主动任务规划：自然语言需求生成结构化计划。
- FOCUS
- POST /projects/{project_id}/ai/plan-action
- 安全检查
- 人工确认
- Executor 队列

## Slide 9: (No title)

Body:
- 安全执行与日志追踪
- AI 生成，人工确认，后端拦截
- 执行前控制
- 执行前必须由用户确认。
- 后端对命令做安全检查。
- 危险命令会被阻断。
- 前端不直接操作服务器。
- 执行后追踪
- Executor 只执行分配给自己的任务。
- Executor 限制 allowed-root。
- 任务状态包括 queued、running、completed、failed。
- 任务输入、结果和错误信息写入 OperationLog。
- ProjectPilot 强调受控自动化：计划可解释，执行可拦截，结果可追踪。

## Slide 10: (No title)

Body:
- 前端展示：TUI 与 APP 软件
- 此页保留展示位，后续替换为实际页面截图
- TUI 展示
- 展示命令行交互、任务状态、Executor 连接和本地检测结果。后续放置 TUI 截图。
- APP 软件展示
- 展示仪表盘、服务器状态、Git 与环境矩阵、AI Insight 和 Recent Activity。后续放置 APP 截图。
- 前端部分重点体现：统一查看、状态对比、任务追踪和 AI 辅助决策。

## Slide 11: (No title)

Body:
- 当前不足与后续优化
- 核心闭环已经跑通，后续重点是稳定性和工程化
- 前后端接口字段仍需继续保持同步。
- Executor 在线状态和心跳展示还可增强。
- 任务取消、重试、优先级仍可扩展。
- AI Planner 仍是初版，需求分类和多步骤工作流可增强。
- CORS 与部署目前通过代理 / Tunnel 解决。
- FOCUS
- 在线状态面板
- 任务超时与重试
- 权限分级
- 工程化部署

## Slide 12: (No title)

Body:
- 问题与改进：为什么 Executor 不再依赖 SSH
- 从后端主动连接，改为目标服务器主动访问总后端
- 传统 SSH 方案的问题
- 后端需要保存多台服务器的登录能力。
- 大量服务器需要开放 SSH 入口。
- 网络、防火墙、密钥管理成本高。
- 批量远程执行命令的安全边界不清晰。
- HTTP Executor 的改进
- Executor 主动通过 HTTPS 轮询总后端。
- 服务器不需要向后端暴露 SSH。
- 任务按 executor_id 分配，执行结果统一回传。
- 状态和日志统一落库，便于审计和追踪。
- Executor 模式更适合多服务器协作：中心调度，分布式执行，安全边界更清楚。
