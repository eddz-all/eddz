# Deck Outline

- File: /home/huancheng/AutoEnv/ProjectPilot/ppt/ProjectPilot_Report.pptx
- Slides: 15

## Slide 1: (No title)

Body:
- POLICY BRIEF
- ProjectPilot
- 面向多服务器项目环境管理的中央控制平台

## Slide 2: (No title)

Body:
- 为什么需要 ProjectPilot
- 多人协作项目在多台机器上运行时，状态很容易分散
- 项目代码、运行环境和 Git 状态分布在不同服务器上。
- Python、Node、Docker 等版本差异会导致运行结果不一致。
- 依赖人工 SSH 排查成本高，操作过程也难以追踪。
- AI 可以辅助分析，但直接自动执行存在风险。
- FOCUS
- 看不清：多台服务器状态分散。
- 改不稳：环境差异和 Git 风险难判断。
- 追不回：执行过程缺少统一日志。
- 2/15

## Slide 3: (No title)

Body:
- 项目目标
- 统一查看、分析、调度与执行
- 统一管理
- 管理项目、服务器、绑定路径和多环境状态。
- 统一检测
- 检测 Git 状态、运行环境、Docker 状态和执行结果。
- 受控执行
- AI 生成计划，人工确认后由 Executor 执行并回传。
- 3/15
- ProjectPilot 的目标是把项目状态、AI 建议和执行过程串成闭环。

## Slide 4: (No title)

Body:
- 总体架构
- 中央控制 + 分布式执行
- 1
- 前端控制台
- 用户查看项目状态，发起检测、AI 分析和执行确认。
- 2
- 总后端
- 统一提供 API，负责调度、聚合、AI 编排和日志记录。
- 3
- 数据库
- 保存项目、服务器、快照、任务和操作日志。
- 4
- Executor
- 运行在目标服务器，主动轮询任务、执行并回传结果。
- 4/15
- 前端和 Executor 都只访问总后端，后端是系统的统一事实来源。

## Slide 5: (No title)

Body:
- 前端成果展示
- 此页等待前端同学补充实际截图
- 项目总览仪表盘：待补充截图。
- 服务器状态列表：待补充截图。
- Git 与环境矩阵：待补充截图。
- AI Insight 与 Recent Activity：待补充截图。
- Executor 任务队列状态展示：待补充截图。
- 5/15
- 前端承担中央控制台角色，将后端聚合结果展示给用户。

## Slide 6: (No title)

Body:
- 后端设计
- FastAPI 后端是调度中心和数据中心
- 01
- Routers
- 提供项目、服务器、检测、AI、执行和日志接口。
- 02
- Services
- 封装检测、执行、AI 计划和 Executor 任务编排。
- 03
- Models
- 定义 Project、Server、GitStatus、EnvironmentSnapshot、ExecutorTask 等模型。
- 04
- Database
- 使用 SQLite + SQLAlchemy 保存系统事实和执行历史。
- 6/15

## Slide 7: (No title)

Body:
- 核心数据模型
- 围绕项目、服务器、快照、任务和日志建立状态闭环
- 同一项目可以绑定多台服务器；同一服务器也可以承载多个项目。
- 7/15

## Slide 8: (No title)

Body:
- Executor 模式
- 服务器主动拉任务，而不是后端大量 SSH 登录
- QUEUED
- 任务入队
- 前端发起操作，后端创建 ExecutorTask。
- POLL
- 主动轮询
- 目标服务器上的 Executor 请求 /executor/poll。
- RUN
- 本机执行
- Executor 在 allowed-root 范围内检测或执行脚本。
- RESULT
- 结果回传
- Executor 调用 /executor/tasks/{task_id}/result。
- 8/15
- 任务状态从 queued 到 running，再到 completed 或 failed，全程可追踪。

## Slide 9: (No title)

Body:
- Git 与环境检测
- 看清项目在每台服务器上的真实状态
- Git 检测
- 分支、remote、ahead/behind、未提交改动、最近提交，以及是否为 Git 仓库。
- 环境检测
- OS、CPU 架构、Python、Node.js、Docker、CUDA、磁盘占用等运行条件。
- 9/15
- 最新检测失败时，前端显示检测任务状态，而不是继续展示旧快照。

## Slide 10: (No title)

Body:
- AI 能力
- 从分析建议到主动生成执行计划
- 环境分析：比较多台服务器环境差异并给出风险。
- Git 分析：接入 eddz smart_git，分析仓库状态和下一步建议。
- 配置计划：根据源/目标服务器环境生成配置步骤。
- 主动计划：用户输入自然语言需求，AI 生成结构化计划。
- FOCUS
- AI 只生成计划。
- 后端做安全检查。
- 用户确认后再入队执行。
- 10/15

## Slide 11: (No title)

Body:
- 安全执行机制
- 避免 AI 直接越权执行
- 风险来源
- AI 可能生成不合适命令。
- 远程机器路径和权限不同。
- 多服务器执行需要可追溯。
- 控制方式
- 执行前需要 confirmed=true。
- 后端拦截高危命令。
- Executor 限制 allowed-root。
- 任务和结果写入 OperationLog。
- ProjectPilot 的执行策略是“先计划、再确认、后执行、全留痕”。
- 11/15

## Slide 12: (No title)

Body:
- 演示闭环
- 一次完整操作从前端到 Executor 再回到前端
- 前端
- 发起需求
- 点击检测，或输入 AI 主动需求。
- 后端
- 生成任务
- 创建 detect_git、detect_environment 或 run_local_script。
- EXECUTOR
- 执行任务
- 目标服务器本机执行并回传 stdout、stderr 和状态。
- 前端
- 展示结果
- 刷新状态、任务队列和 Recent Activity。
- 12/15
- 演示重点是状态变化：queued -> running -> completed / failed。

## Slide 13: (No title)

Body:
- 项目创新点
- 把项目管理、AI 分析和分布式执行组合成平台能力
- 中央控制
- 一个控制台查看多服务器项目状态和执行历史。
- 分布式执行
- Executor 主动拉任务，减少对集中 SSH 管理的依赖。
- AI 计划闭环
- AI 从分析走向可审查、可入队、可追踪的执行计划。
- 13/15
- 亮点不是单个接口，而是“看、分析、调度、执行、追踪”的完整链路。

## Slide 14: (No title)

Body:
- 当前不足与后续优化
- 核心链路已经跑通，后续重点是工程化和体验增强
- 继续统一前后端字段口径，减少展示歧义。
- 补充 Executor 在线心跳和任务超时机制。
- 增加任务取消、重试、优先级和权限分级。
- 增强 AI Planner 的需求分类和多步骤工作流能力。
- FOCUS
- 更强的在线状态面板。
- 更完整的任务生命周期。
- 更清晰的前端可视化。
- 14/15

## Slide 15: (No title)

Body:
- 总结
- 一个能看、能分析、能调度、能执行的项目管理平台
- 1
- 中央控制台
- N
- 多服务器 Executor
- 4
- AI 与检测能力
- 全程
- 日志追踪
- 15/15
- ProjectPilot 将多服务器项目管理从人工排查推进到可视化、可审计、可执行的协作平台。
