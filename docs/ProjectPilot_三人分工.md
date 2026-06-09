# ProjectPilot 三人分工文档

## 一、项目分工原则

ProjectPilot 是一个面向个人与团队的 AI 项目环境管理平台，核心功能包括本地项目检测、多服务器状态检测、Git 状态管理、环境差异对比、AI 分析建议、团队共享记忆和操作审计。

三人分工按照“平台后端与数据管理”“服务器环境与 Git 检测”“前端界面与项目展示”三个方向展开。每个人既有明确职责，也需要在统一接口规范下协作，保证最终系统能够形成完整闭环。

整体协作目标是：

```text
添加项目
↓
添加服务器
↓
检测本地/远程 Git 状态
↓
检测本地/远程环境状态
↓
生成差异报告
↓
AI 给出分析建议
↓
记录团队共享记忆与操作日志
```

---

# 二、成员 A：后端架构与数据管理负责人

## 1. 主要职责

成员 A 负责系统后端主体架构、数据库设计、核心 API、AI 分析模块和报告生成模块，是整个平台的数据与逻辑中心。

主要负责内容包括：

1. 搭建后端服务框架；
2. 设计数据库表结构；
3. 管理项目、服务器、环境快照、Git 状态、团队记忆和操作日志；
4. 提供前端调用的 REST API；
5. 接入大模型 API，用于解释检测结果、生成同步建议和风险提示；
6. 生成 Markdown 项目状态报告和环境差异报告。

---

## 2. 具体任务

### 2.1 后端框架搭建

推荐使用：

```text
Python FastAPI + SQLite + Pydantic
```

需要完成：

- 创建后端项目结构；
- 配置 FastAPI 服务；
- 配置数据库连接；
- 设计统一 API 返回格式；
- 编写基础启动脚本。

建议后端目录结构：

```text
backend/
├── main.py
├── models/
│   ├── project.py
│   ├── server.py
│   ├── git_status.py
│   ├── env_snapshot.py
│   ├── team_memory.py
│   └── operation_log.py
├── routers/
│   ├── projects.py
│   ├── servers.py
│   ├── snapshots.py
│   ├── ai.py
│   └── reports.py
├── services/
│   ├── ai_service.py
│   ├── report_service.py
│   └── memory_service.py
└── database.py
```

---

### 2.2 数据库设计

至少需要设计以下数据表：

```text
Project：项目信息
Server：服务器信息
ProjectServerMapping：项目与服务器映射
GitStatus：Git 状态记录
EnvironmentSnapshot：环境快照
TeamMemory：团队共享记忆
OperationLog：操作日志
```

每张表需要包含基础字段，例如：

```text
id
created_at
updated_at
关联 project_id
关联 server_id
状态内容
备注信息
```

---

### 2.3 核心 API 设计

需要提供以下 API：

```text
POST   /projects              添加项目
GET    /projects              获取项目列表
GET    /projects/{id}         获取项目详情
DELETE /projects/{id}         删除项目

POST   /servers               添加服务器
GET    /servers               获取服务器列表
GET    /servers/{id}          获取服务器详情

POST   /projects/{id}/bind-server      绑定项目和服务器
GET    /projects/{id}/status           获取项目整体状态
GET    /projects/{id}/snapshots        获取环境快照
GET    /projects/{id}/git-status       获取 Git 状态

POST   /ai/analyze-diff       AI 分析环境差异
POST   /ai/git-suggestion     AI 生成 Git 操作建议
POST   /reports/project       生成项目报告
POST   /memory                添加团队记忆
GET    /memory                查询团队记忆
```

---

### 2.4 AI 分析模块

AI 不直接执行高风险操作，只负责分析、解释和建议。

AI 模块输入：

```text
项目基本信息
Git 状态检测结果
环境快照
服务器差异
团队历史记忆
用户问题
```

AI 模块输出：

```text
状态解释
风险提示
同步建议
Git 操作建议
环境修复建议
报告总结
```

示例：

```text
输入：server-a 与 server-b 的环境差异
输出：server-b 的 Python 版本较低，Docker 未启动，建议先创建 Python 3.10 虚拟环境，再启动 Docker 服务。
```

---

## 3. 输入与输出

### 输入

来自成员 B 的检测结果：

```text
本地 Git 状态
远程服务器 Git 状态
本地环境检测结果
远程服务器环境检测结果
服务器连接状态
```

来自成员 C 的前端请求：

```text
添加项目
添加服务器
请求检测
请求 AI 分析
请求生成报告
```

### 输出

提供给成员 C 的接口数据：

```text
项目列表
服务器列表
Git 状态结果
环境快照结果
AI 分析建议
团队记忆记录
操作日志
Markdown 报告
```

---

## 4. 阶段交付成果

第一阶段：

```text
完成 FastAPI 后端框架
完成数据库初版设计
完成项目和服务器基础 API
```

第二阶段：

```text
接入成员 B 的检测模块
保存 Git 状态和环境快照
提供项目状态查询接口
```

第三阶段：

```text
接入 AI API
完成环境差异分析
完成 Git 建议生成
完成 Markdown 报告生成
```

第四阶段：

```text
完成团队共享记忆
完成操作日志
配合前端完成最终展示
```

---

# 三、成员 B：服务器连接、环境检测与 Git 管理负责人

## 1. 主要职责

成员 B 负责项目最核心的检测能力，包括本地项目检测、远程服务器连接、Git 状态检测、环境状态检测和风险操作判断。

主要负责内容包括：

1. 本地项目 Git 状态检测；
2. 远程服务器 SSH 连接；
3. 远程项目 Git 状态检测；
4. 本地和远程环境检测；
5. 多服务器环境差异数据整理；
6. Git 操作风险识别；
7. 为后端提供结构化检测结果。

---

## 2. 具体任务

### 2.1 本地项目检测

需要检测：

```text
项目路径是否存在
是否为 Git 仓库
当前 Git 分支
远程仓库地址
是否有未提交修改
本地领先远程几个 commit
本地落后远程几个 commit
最近一次 commit 信息
```

可使用命令：

```bash
git status --porcelain
git branch --show-current
git remote -v
git rev-list --left-right --count HEAD...@{u}
git log -1 --oneline
```

输出格式示例：

```json
{
  "branch": "main",
  "remote_url": "git@github.com:team/project.git",
  "ahead": 1,
  "behind": 0,
  "has_uncommitted_changes": true,
  "last_commit": "a1b2c3d update config"
}
```

---

### 2.2 本地环境检测

需要检测：

```text
操作系统
CPU 架构
Python 版本
Node.js 版本
Docker 是否安装
Docker 是否运行
CUDA 版本，若存在
磁盘占用
常见项目文件是否存在
```

常见检测命令：

```bash
python --version
node --version
docker --version
docker ps
nvidia-smi
uname -a
df -h
```

输出格式示例：

```json
{
  "os": "Linux",
  "python_version": "3.10.12",
  "node_version": "20.11.0",
  "docker_installed": true,
  "docker_running": true,
  "cuda_version": "12.1",
  "disk_usage": "72%"
}
```

---

### 2.3 远程服务器连接

推荐使用：

```text
Paramiko 或 AsyncSSH
```

需要实现：

```text
测试服务器是否可连接
执行远程只读命令
进入指定项目路径
检测远程 Git 状态
检测远程环境状态
返回结构化结果
```

注意事项：

```text
不要在未确认的情况下执行删除、reset、push 等高风险操作
远程命令需要设置超时时间
连接失败需要返回明确错误原因
```

---

### 2.4 多服务器 Git 状态检测

对于一个项目绑定的多台服务器，需要统一检测：

```text
项目路径是否存在
当前分支
远程仓库
本地是否领先远程
本地是否落后远程
是否有未提交修改
是否有潜在冲突风险
```

输出给后端的数据需要包含 server_id，便于后端保存和前端展示。

---

### 2.5 环境差异数据整理

成员 B 不需要写 AI 分析，但需要整理出可对比的数据。

例如：

```json
{
  "server-a": {
    "python": "3.10",
    "docker": "running",
    "branch": "main"
  },
  "server-b": {
    "python": "3.8",
    "docker": "stopped",
    "branch": "dev"
  }
}
```

这些数据交给成员 A 的 AI 模块分析。

---

### 2.6 Git 操作风险识别

需要对常见 Git 操作进行风险分级。

低风险：

```text
git status
git log
git branch
git remote -v
```

中风险：

```text
git pull
git commit
git push 普通分支
```

高风险：

```text
git reset --hard
git clean -fd
git push --force
git checkout 覆盖未提交修改
git rebase
```

成员 B 需要提供风险识别函数，供成员 A 和成员 C 使用。

---

## 3. 输入与输出

### 输入

来自成员 A 的任务请求：

```text
检测某个本地项目
检测某台服务器
检测某台服务器上的某个项目路径
执行低风险 Git 状态查询
```

来自成员 C 的用户操作：

```text
用户点击检测项目
用户点击检测服务器
用户请求查看 Git 状态
用户请求查看环境状态
```

### 输出

输出给成员 A：

```text
Git 状态 JSON
环境状态 JSON
服务器连接状态 JSON
项目路径检测结果
风险等级判断结果
错误信息
```

输出给成员 C：

```text
可展示的检测状态
服务器连接成功/失败
检测进度
错误提示
```

---

## 4. 阶段交付成果

第一阶段：

```text
完成本地 Git 状态检测
完成本地环境检测
```

第二阶段：

```text
完成 SSH 连接测试
完成远程命令执行
完成远程项目 Git 状态检测
```

第三阶段：

```text
完成多服务器状态检测
完成环境差异数据整理
```

第四阶段：

```text
完成 Git 操作风险分级
配合后端和前端完成团队模式展示
```

---

# 四、成员 C：前端界面、交互展示与测试负责人

## 1. 主要职责

成员 C 负责用户界面、交互流程、状态可视化、报告展示和系统测试，是项目最终展示效果的主要负责人。

主要负责内容包括：

1. 设计 Web 管理界面；
2. 展示单人模式项目状态；
3. 展示团队模式多服务器状态；
4. 展示 Git 状态对比；
5. 展示环境差异报告；
6. 展示 AI 分析建议；
7. 展示团队共享记忆和操作日志；
8. 负责最终演示流程、截图和测试文档。

---

## 2. 具体任务

### 2.1 前端框架搭建

推荐使用：

```text
React / Vue + UI 组件库
```

可选组件库：

```text
Ant Design
Naive UI
Element Plus
```

建议前端目录结构：

```text
frontend/
├── src/
│   ├── pages/
│   │   ├── ProjectList.vue
│   │   ├── ProjectDetail.vue
│   │   ├── ServerList.vue
│   │   ├── GitStatus.vue
│   │   ├── EnvDiff.vue
│   │   ├── TeamMemory.vue
│   │   └── OperationLog.vue
│   ├── components/
│   ├── api/
│   └── router/
└── package.json
```

---

### 2.2 单人模式界面

需要实现以下页面：

```text
项目列表页
添加项目页
项目详情页
本地 Git 状态页
本地环境检测页
项目状态报告页
清理建议页
```

项目详情页应展示：

```text
项目名称
项目路径
项目类型
Git 分支
未提交修改
Python / Node / Docker 状态
依赖文件检测结果
配置文件检测结果
AI 分析建议
```

---

### 2.3 团队模式界面

需要实现以下页面：

```text
团队项目总览页
服务器列表页
项目—服务器绑定页
多服务器状态总览页
多服务器 Git 对比页
多服务器环境差异页
同步建议页
```

多服务器 Git 对比页面建议用表格展示：

```text
服务器名称 | 分支 | ahead | behind | 未提交修改 | 最近提交 | 风险
```

环境差异页面建议用表格展示：

```text
服务器名称 | Python | Node | Docker | CUDA | 磁盘占用 | 状态
```

---

### 2.4 AI 建议展示

AI 建议需要清晰展示，不要只显示一大段文字。

建议拆成：

```text
当前问题
原因分析
建议操作
风险提示
是否需要用户确认
```

示例：

```text
问题：server-b 与标准环境不一致
原因：Python 版本为 3.8，项目建议使用 3.10
建议：创建 Python 3.10 虚拟环境
风险：低，不会影响系统全局环境
```

---

### 2.5 团队共享记忆页面

需要支持：

```text
查看历史记忆
按服务器筛选
按项目筛选
按标签筛选
新增一条记忆
查看 AI 引用过的历史记忆
```

记忆内容示例：

```text
server-a 的 /data/model-cache 是共享模型目录，不要删除。
server-b 曾经因为 Docker 没启动导致项目运行失败。
```

---

### 2.6 操作日志页面

需要展示：

```text
操作时间
操作人员
项目名称
服务器名称
操作类型
风险等级
操作结果
简要输出
```

对于高风险操作，应使用明显标记。

---

### 2.7 测试与演示材料

成员 C 负责整理最终展示材料，包括：

```text
功能截图
演示流程
测试用例
项目 README 中的使用说明
答辩展示页面
```

建议准备两个演示场景：

单人模式：

```text
添加本地项目 → 检测 Git 状态 → 检测环境 → 生成报告
```

团队模式：

```text
添加两个服务器 → 绑定同一个项目 → 检测 Git 状态 → 对比环境差异 → AI 生成同步建议 → 记录团队记忆
```

---

## 3. 输入与输出

### 输入

来自成员 A 的后端 API：

```text
项目数据
服务器数据
Git 状态数据
环境快照数据
AI 建议结果
团队记忆数据
操作日志数据
```

来自成员 B 的检测状态：

```text
检测中
检测成功
检测失败
错误信息
```

### 输出

提供给用户：

```text
项目管理界面
服务器管理界面
Git 对比表格
环境差异表格
AI 建议卡片
团队记忆列表
操作日志页面
Markdown 报告下载入口
```

提供给团队：

```text
演示截图
测试报告
README 使用说明
答辩展示流程
```

---

## 4. 阶段交付成果

第一阶段：

```text
完成前端框架搭建
完成项目列表和项目详情页面
```

第二阶段：

```text
完成服务器列表页面
完成 Git 状态展示页面
完成环境状态展示页面
```

第三阶段：

```text
完成多服务器对比页面
完成 AI 建议展示页面
完成团队记忆页面
```

第四阶段：

```text
完成操作日志页面
完成报告展示和下载
完成最终测试和演示材料
```

---

# 五、三人接口协作关系

## 1. 成员 A 与成员 B 的接口

成员 B 提供检测函数，成员 A 负责调用并保存结果。

接口数据包括：

```text
GitStatusResult
EnvironmentSnapshotResult
ServerConnectionResult
RiskLevelResult
```

协作方式：

```text
B 负责检测逻辑
A 负责数据库保存和 API 封装
```

---

## 2. 成员 A 与成员 C 的接口

成员 A 提供后端 API，成员 C 调用 API 展示数据。

接口数据包括：

```text
Project
Server
GitStatus
EnvironmentSnapshot
AIAnalysis
TeamMemory
OperationLog
```

协作方式：

```text
A 负责接口和数据
C 负责页面和交互
```

---

## 3. 成员 B 与成员 C 的接口

成员 B 的检测结果最终通过后端传给前端，但两人需要确认展示字段。

协作重点：

```text
Git 状态哪些字段要展示
环境状态哪些字段要展示
错误信息如何展示
风险等级如何展示
```

---

# 六、推荐开发顺序

## 第 1 周：基础设计与框架搭建

成员 A：

```text
搭建后端框架
设计数据库
设计 API 规范
```

成员 B：

```text
实现本地 Git 检测
实现本地环境检测
```

成员 C：

```text
搭建前端框架
设计页面原型
```

---

## 第 2 周：单人模式闭环

成员 A：

```text
完成项目管理 API
接入本地检测结果
生成项目状态报告
```

成员 B：

```text
完善本地项目检测
输出标准 JSON 结果
```

成员 C：

```text
完成项目列表页
完成项目详情页
完成本地 Git 和环境状态展示
```

阶段目标：

```text
实现添加本地项目 → 检测 Git 和环境 → 展示状态 → 生成报告
```

---

## 第 3 周：团队模式基础闭环

成员 A：

```text
完成服务器管理 API
完成项目—服务器绑定 API
保存远程检测结果
```

成员 B：

```text
实现 SSH 连接
实现远程 Git 检测
实现远程环境检测
```

成员 C：

```text
完成服务器列表页
完成项目—服务器绑定页
完成多服务器状态总览页
```

阶段目标：

```text
实现添加服务器 → 绑定项目路径 → 检测远程项目状态 → 展示多服务器状态
```

---

## 第 4 周：差异对比与 AI 建议

成员 A：

```text
接入大模型 API
完成环境差异分析
完成 Git 操作建议
```

成员 B：

```text
整理多服务器对比数据
提供风险等级判断
```

成员 C：

```text
完成 Git 对比页面
完成环境差异页面
完成 AI 建议展示页面
```

阶段目标：

```text
实现多服务器 Git/环境差异对比 → AI 生成同步建议
```

---

## 第 5 周：共享记忆与操作审计

成员 A：

```text
完成团队记忆 API
完成操作日志 API
```

成员 B：

```text
接入操作结果记录
完善错误信息输出
```

成员 C：

```text
完成团队记忆页面
完成操作日志页面
```

阶段目标：

```text
实现团队历史经验记录和关键操作追踪
```

---

## 第 6 周：测试、优化与展示

成员 A：

```text
修复后端接口问题
完善报告生成
整理后端 README
```

成员 B：

```text
测试本地和远程检测稳定性
完善异常处理
```

成员 C：

```text
整理最终演示流程
准备截图
完善前端体验
编写使用说明
```

阶段目标：

```text
形成可演示、可提交、可开源的完整项目版本
```

---

# 七、最终成果分配

## 成员 A 最终负责交付

```text
后端服务
数据库设计
API 文档
AI 分析模块
报告生成模块
```

## 成员 B 最终负责交付

```text
本地检测模块
远程服务器检测模块
Git 状态检测模块
环境状态检测模块
风险分级模块
```

## 成员 C 最终负责交付

```text
前端管理界面
多服务器状态看板
AI 建议展示页面
团队记忆页面
操作日志页面
项目演示材料
```

---

# 八、总结

本项目三人分工按照“后端与数据中心、检测与执行能力、前端与展示交互”进行划分。

成员 A 负责平台核心后端和数据管理，保证系统能够保存和组织项目、服务器、Git、环境和团队记忆等数据。

成员 B 负责项目检测能力，保证系统能够准确获取本地与远程服务器上的 Git 状态和环境状态。

成员 C 负责用户界面和最终展示，保证系统功能能够清晰、直观地呈现给用户。

三人协作完成后，ProjectPilot 将形成一个完整闭环：

```text
项目管理 → 服务器管理 → Git 状态检测 → 环境检测 → 差异分析 → AI 建议 → 团队记忆 → 操作审计
```

该闭环能够体现项目的核心特色：不是单纯管理代码，也不是简单让 AI 执行命令，而是面向个人和团队的项目环境状态管理。
