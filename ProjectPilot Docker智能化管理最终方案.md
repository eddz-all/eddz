# ProjectPilot Docker 智能化管理最终方案

## 1. 产品定位

ProjectPilot 的 Docker 能力不是一个 Docker 命令面板。

最终产品应该做成：

```text
一个能理解 Docker 运行状态、Compose 服务关系、镜像构建、容器日志、网络、卷、registry 和部署风险的 AI Docker 控制台。
```

用户不需要先记住复杂命令，而是可以直接问：

```text
为什么 app 容器一直重启？
这个 compose 项目能不能安全更新？
哪些镜像可以清理？
这个 volume 能不能删？
prod-server 能不能部署新版本？
帮我检查 Dockerfile 有没有问题。
帮我生成 Docker 修复计划。
```

AI 的职责是：

- 读取 Docker 状态；
- 理解服务关系；
- 解释异常原因；
- 生成操作计划；
- 判断风险等级；
- 给出可回滚程度；
- 在用户批准后交给 Agent 执行；
- 保存执行前后历史。

Agent 的职责是：

- 在本机或远程服务器上执行被批准的 Docker / Compose 命令；
- 上传执行结果；
- 上传执行前后快照；
- 严格遵守 allowed-root、任务白名单、审批版本和权限边界。

用户的职责是：

- 审核 AI 计划；
- 修改计划；
- 批准执行；
- 拒绝危险操作；
- 批准回滚。

## 2. 最终产品形态

Docker 智能化管理在四个入口中都存在。

```text
Web 控制台
  团队共享 Docker 状态、审批、历史、生产风险。

桌面 GUI App
  个人日常 Docker 管理、本机通知、Agent 管理。

Rust TUI
  终端里查看 Docker 状态、审批计划、查看日志、执行回滚。

CLI
  脚本化检测、CI 接入、快速 doctor。
```

背后统一走：

```text
后端数据库 + AI + 权限
  ↓
Approved DockerPlan
  ↓
本机 Agent
  ↓
本机 Docker 或 SSH 远程 Docker
  ↓
DockerSnapshot / OperationLog / RollbackPlan
```

所有入口共用同一套数据模型、权限模型、审批模型和审计模型。

## 3. Docker 全能力覆盖范围

ProjectPilot 最终要覆盖 Docker 的完整能力面。

覆盖不是默认自动执行所有命令，而是：

```text
能识别；
能读取状态；
能解释；
能生成计划；
能预演或评估影响；
能审批后执行；
能记录历史；
能在可行时生成回滚计划。
```

### 3.1 Docker Daemon 与 Context

需要理解：

- Docker daemon 是否运行；
- Docker API 版本；
- Docker root dir；
- cgroup / storage driver；
- 当前 Docker context；
- context 指向本机还是远程；
- 用户是否有 Docker 权限；
- Docker Desktop / Linux Docker Engine 差异。

典型问题：

```text
Docker 为什么连不上？
为什么当前 context 不对？
为什么普通用户没有权限执行 docker？
Docker Desktop 没启动会影响哪些项目？
```

### 3.2 Container 管理

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

典型能力：

- 解释容器为什么退出；
- 解释容器为什么反复重启；
- 分析 healthcheck 失败；
- 分析端口冲突；
- 判断是否可以安全 restart；
- 判断是否可以安全 stop / remove；
- 生成 container exec 诊断计划。

### 3.3 Image 管理

需要理解：

- image id；
- repository / tag；
- digest；
- size；
- created time；
- parent / layers；
- build source；
- dangling images；
- unused images；
- registry 来源；
- tag 是否指向生产版本。

典型能力：

- 判断镜像是否过旧；
- 判断当前容器运行的是哪个 image；
- 判断本地 image 是否和 registry 一致；
- 生成 pull / build / tag / push 计划；
- 判断哪些 image 可以清理；
- 防止误删仍被容器使用的 image。

### 3.4 Dockerfile 与 Build

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

典型能力：

```text
这个 Dockerfile 为什么 build 慢？
为什么镜像这么大？
为什么构建缓存没有命中？
为什么容器里缺依赖？
这个 Dockerfile 有没有安全风险？
```

### 3.5 Docker Compose

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

典型能力：

- 生成服务拓扑；
- 判断 service 之间依赖关系；
- 判断重启某个 service 的影响；
- 判断 compose up 是否会重建容器；
- 判断 compose down 是否会影响 volume；
- 判断缺少哪些 env；
- 判断宿主机端口是否冲突；
- 判断生产服务是否会中断；
- 生成 compose 部署计划。

### 3.6 Network 管理

需要理解：

- network 类型；
- connected containers；
- aliases；
- IPAM；
- service 之间是否能互通；
- 端口绑定；
- host 网络风险。

典型能力：

```text
为什么 app 连不上 postgres？
为什么 nginx 访问不到 backend？
这个端口是不是被占用了？
这个容器暴露到了公网吗？
```

### 3.7 Volume 管理

Volume 是最高风险区域之一。

需要理解：

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

典型能力：

- 识别数据卷；
- 判断哪些 volume 可疑；
- 生成备份建议；
- 生成清理计划；
- 阻止危险 prune。

### 3.8 Registry 与镜像发布

需要理解：

- registry 登录状态；
- repository；
- tag 策略；
- digest；
- latest / prod / stable tag 风险；
- push 权限；
- image provenance；
- 是否覆盖已有 tag。

典型能力：

- 生成安全 tag；
- 阻止覆盖生产 tag；
- push 前检查镜像来源；
- push 后记录 digest；
- 生成发布说明。

### 3.9 日志与健康分析

需要理解：

- container logs；
- compose logs；
- healthcheck 输出；
- 重启次数；
- OOM killed；
- exit code；
- application error；
- missing env；
- connection refused；
- permission denied；
- migration error。

AI 应该把日志总结成：

```text
现象
证据
可能原因
建议检查
建议修复计划
风险
```

## 4. 风险分级

### 4.1 低风险

低风险操作只读为主，可以自动执行或弱确认。

```text
docker version
docker info
docker context ls
docker ps
docker images
docker inspect
docker logs --tail
docker stats --no-stream
docker network ls
docker network inspect
docker volume ls
docker volume inspect
docker compose config
docker compose ps
docker compose logs --tail
```

### 4.2 中风险

中风险操作会改变容器、镜像或服务状态，需要用户确认。

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

### 4.3 高风险

高风险操作需要强确认，必要时要求管理员权限。

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

强确认必须展示：

- 目标机器；
- 目标项目；
- 影响的容器；
- 影响的镜像；
- 影响的 volume；
- 影响的端口；
- 是否生产环境；
- 是否有备份；
- 是否可回滚；
- 执行前快照。

### 4.4 默认禁止

以下操作默认禁止自动执行，只能作为人工建议或管理员特别审批能力。

```text
docker system prune -a --volumes
删除未备份 volume
生产环境 docker compose down
覆盖 prod / stable / latest tag
privileged 运行未知镜像
挂载宿主机敏感目录
在生产容器里执行未知脚本
删除数据库容器关联 volume
```

## 5. 后端数据模型

### 5.1 DockerSnapshot

记录某台机器某个时间点的 Docker 状态。

```text
DockerSnapshot
  id
  project_id
  server_id
  machine_id
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

### 5.2 ComposeProjectSnapshot

记录一个 Compose 项目的解析结果。

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

### 5.3 DockerPlan

AI 生成的 Docker 操作计划。

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

### 5.4 DockerOperationLog

记录执行历史。

```text
DockerOperationLog
  id
  plan_id
  step_id
  approval_id
  machine_id
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

### 5.5 DockerRollbackPlan

记录回滚建议。

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

## 6. Agent 执行边界

Agent 执行 Docker 任务时必须校验：

```text
task.plan_id 存在
task.plan_version 是 approved
task.approval_id 存在
task.command_template 在允许列表内
task.target_path 在 allowed-root 内
task.server_id 在 Agent 权限范围内
task.risk 不超过用户批准范围
```

Agent 不能执行：

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

## 7. 界面设计

### 7.1 Docker 总览

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

### 7.2 项目 Docker 页

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

### 7.3 DockerPlan 审批页

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

## 8. 典型工作流

### 8.1 Docker Doctor

```text
用户点击 Docker Doctor
  ↓
Agent 采集 DockerSnapshot
  ↓
后端保存快照
  ↓
AI 分析容器、镜像、Compose、volume、network、日志
  ↓
输出健康报告
```

### 8.2 修复 restarting 容器

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
Agent 执行
  ↓
保存 before / after DockerSnapshot
  ↓
AI 总结 app 是否恢复
```

### 8.3 安全更新 Compose 服务

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
Agent 执行 docker compose pull app
  ↓
Agent 执行 docker compose up -d app
  ↓
AI 检查 healthcheck 和 logs
```

### 8.4 清理镜像和容器

```text
用户问哪些 Docker 资源可以清理
  ↓
AI 标记 unused images / exited containers / dangling images
  ↓
AI 排除正在运行容器使用的 image
  ↓
AI 排除未知 volume
  ↓
生成 CleanupPlan
  ↓
用户逐项批准
  ↓
Agent 执行清理
```

### 8.5 删除 volume 前保护

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

## 9. CLI 和 TUI

### 9.1 CLI

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

CLI 适合：

- CI；
- 快速检测；
- 脚本化；
- 调试 Agent；
- 输出 JSON 给后端。

### 9.2 Rust TUI

TUI 应该支持：

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

## 10. 版本路线

### V1：Docker 只读智能检测

目标：

```text
让 ProjectPilot 看懂 Docker 状态。
```

能力：

- docker daemon 检测；
- docker ps / images / inspect；
- docker compose ps / config；
- logs tail 摘要；
- container health 分析；
- Compose 项目识别；
- DockerSnapshot 入库；
- AI 生成 Docker 健康报告。

### V2：DockerPlan 与审批

目标：

```text
让 AI 能生成 Docker 修复和部署计划，但默认不执行危险操作。
```

能力：

- DockerPlan；
- 风险分级；
- 审批流；
- before / after snapshot；
- DockerOperationLog；
- TUI / Web / GUI 审批；
- 中风险操作执行。

### V3：Compose 运维闭环

目标：

```text
安全管理真实项目中的 Compose 服务。
```

能力：

- compose service 拓扑；
- compose up / restart service；
- compose pull / build；
- healthcheck 检查；
- env 缺失检测；
- volume 风险检测；
- rollback plan；
- 失败后自动停止后续高风险步骤。

### V4：团队和生产治理

目标：

```text
让团队安全管理生产 Docker 环境。
```

能力：

- 角色权限；
- 生产环境强确认；
- registry 权限；
- 镜像 tag 策略；
- volume 删除审批；
- 操作审计；
- 生产变更窗口；
- 团队 Docker 报告。

### V5：AI Docker 控制台

目标：

```text
成为 Git + Docker + 环境 + 部署一体化 AI 控制台。
```

能力：

- Docker 全功能覆盖；
- Git 状态和 image 版本关联；
- CI/CD 集成；
- registry digest 追踪；
- 部署前检查；
- 自动健康巡检；
- 事故恢复建议；
- 多服务器 Docker 状态对比。

## 11. 最终边界

ProjectPilot 应该做：

- 帮用户理解 Docker 状态；
- 帮用户解释容器异常；
- 帮用户识别 Compose 风险；
- 帮用户生成安全 Docker 计划；
- 帮用户审批后执行 Docker 操作；
- 帮用户保存 Docker 操作历史；
- 帮用户生成回滚建议；
- 帮团队治理生产 Docker 操作。

ProjectPilot 不应该做：

- 未经批准停止生产容器；
- 未经批准删除 volume；
- 未经批准执行 prune；
- 未经批准覆盖 registry tag；
- 未经批准运行 privileged 未知镜像；
- 在容器中执行任意未知脚本；
- 声称 Docker 操作都能完整回滚；
- 绕过后端审批和审计。

## 12. 一句话终局

```text
ProjectPilot Docker = Docker Doctor + Docker Planner + Docker Executor + Docker Audit + Docker Rollback。
```

最终用户感受到的是：

```text
我不需要先知道该敲哪条 Docker 命令。
ProjectPilot 会告诉我 Docker 出了什么问题、证据是什么、风险在哪里、下一步怎么做。
如果要执行，它会先给我计划。
我批准后，它才会通过 Agent 执行，并记录历史。
```
