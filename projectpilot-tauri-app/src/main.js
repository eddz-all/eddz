const API_BASE_KEY = "projectpilot.apiBase";
const API_BASE_VERSION_KEY = "projectpilot.apiBaseVersion";
const API_BASE_VERSION = "20260610-cloudflare-functioning-element";
const DEFAULT_API_BASE = "https://functioning-element-pushing-whenever.trycloudflare.com";
const LOCAL_API_PROXY_BASE = "/api";
const SESSION_KEY = "projectpilot.session";
const LOCAL_DEMO_KEY = "projectpilot.localDemo.v1";
const MISSING_VALUE = "未返回";
const REQUEST_TIMEOUT_MS = 8000;

const apiContract = [
  ["GET", "/projects", "已接入", "项目列表"],
  ["POST", "/projects", "已接入", "创建项目"],
  ["GET", "/servers", "已接入", "服务器列表"],
  ["POST", "/servers", "已接入", "创建服务器"],
  ["GET", "/servers/{id}/status", "已接入", "服务器综合状态"],
  ["GET", "/projects/{id}/status", "已接入", "项目综合状态"],
  ["POST", "/projects/{id}/ai/analyze-env", "已接入", "AI 环境分析"],
  ["POST", "/projects/{id}/ai/config-plan", "已接入", "AI 配置计划"],
  ["POST", "/projects/{id}/ai/analyze-git", "已接入", "AI Git 分析"],
  ["POST", "/projects/{id}/bind-server", "已接入", "绑定项目服务器"],
  ["DELETE", "/projects/{id}/servers/{server_id}", "已接入", "解除项目服务器绑定"],
  ["POST", "/reports/project", "已接入", "Markdown 报告"],
  ["POST", "/servers/{id}/check-connection", "已接入", "服务器连接检测"],
  ["GET", "/projects/{id}/servers", "已接入", "项目绑定服务器"],
  ["POST", "/projects/{id}/servers/{server_id}/detect", "已接入", "单服务器检测"],
  ["POST", "/projects/{id}/servers/{server_id}/execute-config-plan", "已接入", "执行配置计划"],
  ["GET", "/operation-logs", "已接入", "操作日志"],
  ["GET", "/executor/tasks", "已接入", "Executor 任务流"],
  ["GET", "/executor/tasks/{task_id}", "已接入", "Executor 单任务"],
  ["GET", "/ai/settings", "已接入", "AI 配置状态"],
  ["POST", "/projects/{id}/ai/plan-action", "已接入", "AI 主动执行计划"]
];

const initialApiBase = readApiBase();

const state = {
  route: "dashboard",
  user: readSession(),
  apiBase: initialApiBase,
  backendMode: "checking",
  backendIssue: "",
  localDemoActive: false,
  isLoading: false,
  toast: "",
  pendingActions: new Set(),
  drafts: {
    login: {
      email: "admin@projectpilot.local",
      password: "projectpilot"
    },
    project: {
      name: "",
      path: "",
      description: ""
    },
    server: {
      name: "",
      host: "",
      port: "",
      username: "",
      connection_mode: "executor",
      description: ""
    },
    binding: {
      server_id: "",
      project_path: ""
    },
    actionPlan: {
      goal: "",
      source_server_id: "",
      target_server_id: "",
      allow_command_generation: true,
      auto_execute: false,
      confirmed: false
    },
    settings: {
      apiBase: initialApiBase
    }
  },
  projects: [],
  servers: [],
  bindings: [],
  dataLoaded: {
    projects: false,
    servers: false,
    status: false,
    bindings: false
  },
  contextProjectId: null,
  selectedProjectId: 1,
  selectedServerId: null,
  status: null,
  serverDetail: null,
  aiSettings: null,
  analysis: null,
  gitAnalysis: null,
  plan: null,
  actionPlan: null,
  executionResult: null,
  activities: [],
  executorTasks: [],
  executorTaskDetail: null,
  report: "",
  lastSync: null
};

function readSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

function normalizeApiBase(value) {
  return String(value || "").trim().replace(/\/$/, "");
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return MISSING_VALUE;
  }
  return value;
}

function isActionPending(actionKey) {
  return state.pendingActions.has(actionKey);
}

function actionAttrs(actionKey) {
  return isActionPending(actionKey) ? 'disabled aria-busy="true"' : "";
}

function actionText(actionKey, idleText, busyText = "处理中...") {
  return isActionPending(actionKey) ? busyText : idleText;
}

async function runAction(actionKey, busyMessage, handler) {
  if (isActionPending(actionKey)) {
    return;
  }

  state.pendingActions.add(actionKey);
  if (busyMessage) {
    setToast(busyMessage);
  }
  render();
  try {
    await handler();
  } finally {
    state.pendingActions.delete(actionKey);
    render();
  }
}

function confirmAction(message) {
  return window.confirm(message);
}

function shouldProxyApiBase(apiBase) {
  if (!window.location || !["127.0.0.1", "localhost"].includes(window.location.hostname)) {
    return false;
  }

  try {
    const parsedApiBase = new URL(apiBase);
    return parsedApiBase.origin !== window.location.origin;
  } catch {
    return false;
  }
}

function tauriInvoke() {
  return window.__TAURI__?.core?.invoke;
}

function readApiBase() {
  const saved = normalizeApiBase(localStorage.getItem(API_BASE_KEY));
  const version = localStorage.getItem(API_BASE_VERSION_KEY);

  if (!saved || version !== API_BASE_VERSION) {
    localStorage.setItem(API_BASE_KEY, DEFAULT_API_BASE);
    localStorage.setItem(API_BASE_VERSION_KEY, API_BASE_VERSION);
    return DEFAULT_API_BASE;
  }

  return saved;
}

function saveSession(user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

function localTimestamp(minutesAgo = 0) {
  return new Date(Date.now() - minutesAgo * 60 * 1000).toISOString();
}

function defaultLocalDemoData() {
  const createdAt = localTimestamp(42);
  const scannedAt = localTimestamp(7);
  return {
    nextProjectId: 2,
    nextServerId: 3,
    nextBindingId: 2,
    nextGitStatusId: 2,
    nextEnvironmentSnapshotId: 2,
    nextOperationLogId: 3,
    nextTaskId: 3,
    projects: [
      {
        id: 1,
        name: "ProjectPilot Workspace",
        path: "/Users/eddz/work/engine",
        description: "Local desktop demo workspace",
        created_at: createdAt
      }
    ],
    servers: [
      {
        id: 1,
        name: "Local Executor",
        host: "127.0.0.1",
        port: 22,
        username: "eddz",
        connection_mode: "local",
        connection_status: "online",
        description: "Local machine used for desktop workflow validation",
        created_at: createdAt
      },
      {
        id: 2,
        name: "server-b",
        host: "192.168.0.20",
        port: 22,
        username: "hzy",
        connection_mode: "executor",
        connection_status: "ready",
        description: "Headless executor profile placeholder",
        created_at: localTimestamp(35)
      }
    ],
    bindings: [
      {
        id: 1,
        project_id: 1,
        server_id: 1,
        project_path: "/Users/eddz/work/engine",
        created_at: localTimestamp(38)
      }
    ],
    gitStatuses: [
      {
        id: 1,
        project_id: 1,
        server_id: 1,
        branch: "main",
        remote_url: "local-demo",
        ahead: 3,
        behind: 0,
        has_uncommitted_changes: false,
        last_commit: "b049d2c Add ProjectPilot Tauri desktop app",
        created_at: scannedAt
      }
    ],
    environmentSnapshots: [
      {
        id: 1,
        project_id: 1,
        server_id: 1,
        os: "macOS",
        architecture: "arm64",
        python_version: "Python 3",
        node_version: "Node.js",
        docker_installed: true,
        docker_running: false,
        cuda_version: null,
        disk_usage: "62%",
        raw_data: {
          source: "local-demo"
        },
        created_at: scannedAt
      }
    ],
    operationLogs: [
      {
        id: 1,
        project_id: 1,
        server_id: 1,
        operation_type: "detect_project_server",
        risk_level: "medium",
        status: "completed",
        summary: "Local demo detection completed",
        detail: "Backend was unavailable, so ProjectPilot used the local demo store.",
        created_at: scannedAt
      },
      {
        id: 2,
        project_id: 1,
        server_id: null,
        operation_type: "desktop_bootstrap",
        risk_level: "low",
        status: "completed",
        summary: "Desktop local workflow is ready",
        detail: "Project, server, binding, detection and task stream are available without a remote backend.",
        created_at: localTimestamp(10)
      }
    ],
    executorTasks: [
      {
        id: "local-1",
        project_id: 1,
        server_id: 1,
        task_type: "detect_git",
        status: "completed",
        executor_id: "local-demo",
        message: "Git status captured in local demo mode",
        result: {
          success: true,
          branch: "main",
          remote_url: "local-demo",
          ahead: 3,
          behind: 0,
          has_uncommitted_changes: false,
          last_commit: "b049d2c Add ProjectPilot Tauri desktop app",
          created_at: scannedAt
        },
        created_at: scannedAt,
        claimed_at: scannedAt,
        completed_at: scannedAt
      },
      {
        id: "local-2",
        project_id: 1,
        server_id: 1,
        task_type: "detect_environment",
        status: "completed",
        executor_id: "local-demo",
        message: "Environment snapshot captured in local demo mode",
        result: {
          success: true,
          os: "macOS",
          architecture: "arm64",
          python_version: "Python 3",
          node_version: "Node.js",
          docker_installed: true,
          docker_running: false,
          disk_usage: "62%",
          created_at: scannedAt
        },
        created_at: scannedAt,
        claimed_at: scannedAt,
        completed_at: scannedAt
      }
    ]
  };
}

function ensureLocalDemoData(value) {
  const fallback = defaultLocalDemoData();
  const data = value && typeof value === "object" ? { ...fallback, ...value } : fallback;
  const arrayKeys = [
    "projects",
    "servers",
    "bindings",
    "gitStatuses",
    "environmentSnapshots",
    "operationLogs",
    "executorTasks"
  ];
  arrayKeys.forEach((key) => {
    if (!Array.isArray(data[key])) {
      data[key] = fallback[key];
    }
  });

  const nextId = (items, key = "id") =>
    Math.max(0, ...items.map((item) => Number(item[key])).filter(Number.isFinite)) + 1;

  data.nextProjectId = Math.max(Number(data.nextProjectId) || 1, nextId(data.projects));
  data.nextServerId = Math.max(Number(data.nextServerId) || 1, nextId(data.servers));
  data.nextBindingId = Math.max(Number(data.nextBindingId) || 1, nextId(data.bindings));
  data.nextGitStatusId = Math.max(Number(data.nextGitStatusId) || 1, nextId(data.gitStatuses));
  data.nextEnvironmentSnapshotId = Math.max(
    Number(data.nextEnvironmentSnapshotId) || 1,
    nextId(data.environmentSnapshots)
  );
  data.nextOperationLogId = Math.max(Number(data.nextOperationLogId) || 1, nextId(data.operationLogs));
  data.nextTaskId = Math.max(
    Number(data.nextTaskId) || 1,
    Math.max(
      0,
      ...data.executorTasks
        .map((task) => Number(String(task.id).replace(/^local-/, "")))
        .filter(Number.isFinite)
    ) + 1
  );

  return data;
}

function readLocalDemoData() {
  try {
    return ensureLocalDemoData(JSON.parse(localStorage.getItem(LOCAL_DEMO_KEY) || "null"));
  } catch {
    return defaultLocalDemoData();
  }
}

function writeLocalDemoData(data) {
  localStorage.setItem(LOCAL_DEMO_KEY, JSON.stringify(data));
}

function localFormatServer(server) {
  return {
    id: server.id,
    name: server.name,
    host: server.host,
    port: server.port,
    username: server.username,
    connection_mode: server.connection_mode,
    connection_status: server.connection_status,
    description: server.description,
    created_at: server.created_at
  };
}

function localLatestByServer(items, projectId, serverId) {
  return items
    .filter((item) => Number(item.project_id) === Number(projectId) && Number(item.server_id) === Number(serverId))
    .sort((left, right) => parseTimestamp(right.created_at) - parseTimestamp(left.created_at))[0] || null;
}

function localBindingRows(data, projectId) {
  return data.bindings
    .filter((binding) => Number(binding.project_id) === Number(projectId))
    .map((binding) => {
      const server = data.servers.find((item) => Number(item.id) === Number(binding.server_id)) || {};
      return {
        binding_id: binding.id,
        project_id: binding.project_id,
        server_id: binding.server_id,
        server_name: server.name,
        host: server.host,
        port: server.port,
        username: server.username,
        connection_mode: server.connection_mode,
        connection_status: server.connection_status,
        project_path: binding.project_path,
        created_at: binding.created_at
      };
    });
}

function localStatusServer(data, binding) {
  const server = data.servers.find((item) => Number(item.id) === Number(binding.server_id)) || {};
  return {
    server_id: binding.server_id,
    server_name: server.name,
    host: server.host,
    port: server.port,
    username: server.username,
    connection_mode: server.connection_mode,
    connection_status: server.connection_status,
    project_path: binding.project_path,
    latest_git_status: localLatestByServer(data.gitStatuses, binding.project_id, binding.server_id),
    latest_environment_snapshot: localLatestByServer(
      data.environmentSnapshots,
      binding.project_id,
      binding.server_id
    )
  };
}

function localProjectStatus(data, projectId) {
  const project = data.projects.find((item) => Number(item.id) === Number(projectId)) || null;
  return {
    project,
    servers: data.bindings
      .filter((binding) => Number(binding.project_id) === Number(projectId))
      .map((binding) => localStatusServer(data, binding))
  };
}

function localAddOperationLog(data, payload) {
  const log = {
    id: data.nextOperationLogId,
    project_id: payload.project_id ?? null,
    server_id: payload.server_id ?? null,
    operation_type: payload.operation_type,
    risk_level: payload.risk_level || "low",
    status: payload.status || "completed",
    summary: payload.summary,
    detail: payload.detail || null,
    created_at: localTimestamp()
  };
  data.nextOperationLogId += 1;
  data.operationLogs.unshift(log);
  return log;
}

function localAddTask(data, payload) {
  const now = localTimestamp();
  const task = {
    id: `local-${data.nextTaskId}`,
    project_id: payload.project_id,
    server_id: payload.server_id,
    task_type: payload.task_type,
    status: payload.status || "completed",
    executor_id: payload.executor_id || "local-demo",
    message: payload.message,
    result: payload.result || null,
    created_at: payload.created_at || now,
    claimed_at: payload.claimed_at || now,
    completed_at: payload.completed_at || now
  };
  data.nextTaskId += 1;
  data.executorTasks.unshift(task);
  return task;
}

function localCreateDetection(data, projectId, serverId) {
  const project = data.projects.find((item) => Number(item.id) === Number(projectId));
  const server = data.servers.find((item) => Number(item.id) === Number(serverId));
  const binding = data.bindings.find(
    (item) => Number(item.project_id) === Number(projectId) && Number(item.server_id) === Number(serverId)
  );
  if (!project || !server || !binding) {
    return null;
  }

  const now = localTimestamp();
  const gitStatus = {
    id: data.nextGitStatusId,
    project_id: project.id,
    server_id: server.id,
    branch: "main",
    remote_url: "local-demo",
    ahead: state.backendMode === "local" ? 3 : 0,
    behind: 0,
    has_uncommitted_changes: false,
    last_commit: "local-demo detection",
    created_at: now
  };
  data.nextGitStatusId += 1;
  data.gitStatuses.push(gitStatus);

  const environmentSnapshot = {
    id: data.nextEnvironmentSnapshotId,
    project_id: project.id,
    server_id: server.id,
    os: navigator.platform || "local",
    architecture: navigator.userAgent.includes("Mac") ? "arm64" : "local",
    python_version: "Python 3",
    node_version: "Node.js",
    docker_installed: true,
    docker_running: server.connection_mode === "executor",
    cuda_version: null,
    disk_usage: server.connection_mode === "executor" ? "55%" : "62%",
    raw_data: {
      source: "local-demo",
      project_path: binding.project_path
    },
    created_at: now
  };
  data.nextEnvironmentSnapshotId += 1;
  data.environmentSnapshots.push(environmentSnapshot);

  const gitTask = localAddTask(data, {
    project_id: project.id,
    server_id: server.id,
    task_type: "detect_git",
    message: `Git detection completed for ${project.name}`,
    result: {
      success: true,
      branch: gitStatus.branch,
      remote_url: gitStatus.remote_url,
      ahead: gitStatus.ahead,
      behind: gitStatus.behind,
      has_uncommitted_changes: gitStatus.has_uncommitted_changes,
      last_commit: gitStatus.last_commit,
      created_at: gitStatus.created_at
    }
  });
  const environmentTask = localAddTask(data, {
    project_id: project.id,
    server_id: server.id,
    task_type: "detect_environment",
    message: `Environment detection completed for ${server.name}`,
    result: {
      success: true,
      os: environmentSnapshot.os,
      architecture: environmentSnapshot.architecture,
      python_version: environmentSnapshot.python_version,
      node_version: environmentSnapshot.node_version,
      docker_installed: environmentSnapshot.docker_installed,
      docker_running: environmentSnapshot.docker_running,
      disk_usage: environmentSnapshot.disk_usage,
      created_at: environmentSnapshot.created_at
    }
  });

  localAddOperationLog(data, {
    project_id: project.id,
    server_id: server.id,
    operation_type: "detect_project_server",
    risk_level: environmentSnapshot.docker_running ? "low" : "medium",
    status: "completed",
    summary: `Detected ${project.name} on ${server.name}`,
    detail: "Generated by local demo mode."
  });

  return {
    project_id: project.id,
    project_name: project.name,
    server_id: server.id,
    server_name: server.name,
    project_path: binding.project_path,
    connection_mode: server.connection_mode,
    status: "completed",
    message: "Local detection completed",
    git_status: gitStatus,
    environment_snapshot: environmentSnapshot,
    tasks: [gitTask, environmentTask]
  };
}

function localAnalysis(data, projectId) {
  const status = localProjectStatus(data, projectId);
  const serverCount = status.servers.length;
  const dockerIssues = status.servers.filter((server) => !server.latest_environment_snapshot?.docker_running).length;
  return {
    project_id: projectId,
    status: "completed",
    risk_level: dockerIssues ? "medium" : "low",
    issues: [
      serverCount ? `${serverCount} 个绑定服务器已进入本地状态矩阵` : "当前项目还没有绑定服务器",
      dockerIssues ? `${dockerIssues} 个环境的 Docker 未运行` : "本地环境快照没有发现阻塞项",
      state.localDemoActive ? "当前使用 Local Demo 数据源" : "当前使用后端数据源"
    ],
    recommendations: [
      "优先验证项目、服务器、绑定、检测、任务流闭环",
      "后端公网域名稳定后再切回远端 API"
    ]
  };
}

function localPlan(data, projectId, body = {}) {
  const targetServer = data.servers.find((server) => Number(server.id) === Number(body.target_server_id));
  return {
    project_id: projectId,
    target_server_id: targetServer?.id || body.target_server_id,
    target_server_name: targetServer?.name,
    goal: body.goal || "Validate ProjectPilot local workflow",
    status: "ready",
    summary: "Local demo plan is ready for executor handoff.",
    steps: [
      {
        order: 1,
        title: "Verify project binding",
        description: "Confirm the selected project path is bound to the target server.",
        risk_level: "low"
      },
      {
        order: 2,
        title: "Run environment detection",
        description: "Collect Git and runtime signals before any execution.",
        risk_level: "low"
      },
      {
        order: 3,
        title: "Queue executor-safe action",
        description: "Keep executor work headless and report results back to the control plane.",
        risk_level: "medium"
      }
    ]
  };
}

function localMarkdownReport(data, projectId) {
  const project = data.projects.find((item) => Number(item.id) === Number(projectId));
  const status = localProjectStatus(data, projectId);
  const tasks = data.executorTasks.filter((task) => Number(task.project_id) === Number(projectId));
  return `# ${project?.name || "ProjectPilot"} Local Report

| Area | Current State |
| --- | --- |
| Data source | Local Demo |
| Bound servers | ${status.servers.length} |
| Executor tasks | ${tasks.length} |

## Main Flow

1. Project registry is available locally.
2. Server records can be created and selected.
3. Project-server bindings are persisted in localStorage.
4. Detection creates completed executor task records without launching an executor GUI.
`;
}

function localRequest(path, options = {}) {
  const method = options.method || "GET";
  const url = new URL(path, window.location.origin);
  const parts = url.pathname.split("/").filter(Boolean);
  const data = readLocalDemoData();
  const body = options.body || {};
  const commit = (response) => {
    writeLocalDemoData(data);
    return response;
  };

  if (method === "GET" && parts.length === 1 && parts[0] === "projects") {
    return data.projects;
  }
  if (method === "POST" && parts.length === 1 && parts[0] === "projects") {
    const project = {
      id: data.nextProjectId,
      name: body.name,
      path: body.path,
      description: body.description || "",
      created_at: localTimestamp()
    };
    data.nextProjectId += 1;
    data.projects.unshift(project);
    localAddOperationLog(data, {
      project_id: project.id,
      operation_type: "create_project",
      summary: `Created project ${project.name}`,
      detail: project.path
    });
    return commit(project);
  }
  if (method === "GET" && parts.length === 1 && parts[0] === "servers") {
    return data.servers.map(localFormatServer);
  }
  if (method === "POST" && parts.length === 1 && parts[0] === "servers") {
    const server = {
      id: data.nextServerId,
      name: body.name,
      host: body.host,
      port: body.port,
      username: body.username,
      connection_mode: body.connection_mode || "executor",
      connection_status: body.connection_mode === "local" ? "online" : "ready",
      description: body.description || "",
      created_at: localTimestamp()
    };
    data.nextServerId += 1;
    data.servers.unshift(server);
    localAddOperationLog(data, {
      server_id: server.id,
      operation_type: "create_server",
      summary: `Created server ${server.name}`,
      detail: `${server.host}:${server.port}`
    });
    return commit(localFormatServer(server));
  }
  if (method === "POST" && parts.length === 3 && parts[0] === "servers" && parts[2] === "check-connection") {
    const serverId = Number(parts[1]);
    const server = data.servers.find((item) => Number(item.id) === serverId);
    if (!server) return null;
    server.connection_status = server.connection_mode === "local" ? "online" : "ready";
    localAddOperationLog(data, {
      server_id: server.id,
      operation_type: "check_connection",
      summary: `Checked connection for ${server.name}`,
      detail: "Local demo connection check completed."
    });
    return commit({
      server_id: server.id,
      server_name: server.name,
      connection_mode: server.connection_mode,
      connected: true,
      message: "Local demo connection is available",
      latency_ms: 8
    });
  }
  if (method === "GET" && parts.length === 3 && parts[0] === "servers" && parts[2] === "status") {
    const serverId = Number(parts[1]);
    const server = data.servers.find((item) => Number(item.id) === serverId);
    if (!server) return null;
    const projects = data.bindings
      .filter((binding) => Number(binding.server_id) === serverId)
      .map((binding) => {
        const project = data.projects.find((item) => Number(item.id) === Number(binding.project_id)) || {};
        return {
          binding_id: binding.id,
          server_id: serverId,
          project_id: project.id,
          project_name: project.name,
          project_path: binding.project_path,
          latest_git_status: localLatestByServer(data.gitStatuses, project.id, serverId),
          latest_environment_snapshot: localLatestByServer(data.environmentSnapshots, project.id, serverId)
        };
      });
    return {
      server: localFormatServer(server),
      projects
    };
  }
  if (method === "GET" && parts.length === 3 && parts[0] === "projects" && parts[2] === "status") {
    return localProjectStatus(data, Number(parts[1]));
  }
  if (method === "GET" && parts.length === 3 && parts[0] === "projects" && parts[2] === "servers") {
    return localBindingRows(data, Number(parts[1]));
  }
  if (method === "POST" && parts.length === 3 && parts[0] === "projects" && parts[2] === "bind-server") {
    const projectId = Number(parts[1]);
    const serverId = Number(body.server_id);
    const existing = data.bindings.find(
      (binding) => Number(binding.project_id) === projectId && Number(binding.server_id) === serverId
    );
    if (existing) {
      existing.project_path = body.project_path;
      return commit({
        id: existing.id,
        project_id: existing.project_id,
        server_id: existing.server_id,
        project_path: existing.project_path,
        created_at: existing.created_at
      });
    }
    const binding = {
      id: data.nextBindingId,
      project_id: projectId,
      server_id: serverId,
      project_path: body.project_path,
      created_at: localTimestamp()
    };
    data.nextBindingId += 1;
    data.bindings.unshift(binding);
    localAddOperationLog(data, {
      project_id: projectId,
      server_id: serverId,
      operation_type: "bind_server",
      summary: "Bound project to server",
      detail: body.project_path
    });
    return commit(binding);
  }
  if (method === "DELETE" && parts.length === 4 && parts[0] === "projects" && parts[2] === "servers") {
    const projectId = Number(parts[1]);
    const serverId = Number(parts[3]);
    data.bindings = data.bindings.filter(
      (binding) => !(Number(binding.project_id) === projectId && Number(binding.server_id) === serverId)
    );
    localAddOperationLog(data, {
      project_id: projectId,
      server_id: serverId,
      operation_type: "unbind_server",
      summary: "Removed project-server binding"
    });
    return commit({ message: "Local project-server binding deleted" });
  }
  if (method === "POST" && parts.length === 5 && parts[0] === "projects" && parts[2] === "servers" && parts[4] === "detect") {
    const result = localCreateDetection(data, Number(parts[1]), Number(parts[3]));
    return result ? commit(result) : null;
  }
  if (method === "GET" && parts.length === 2 && parts[0] === "executor" && parts[1] === "tasks") {
    const projectIdParam = url.searchParams.get("project_id");
    const projectId = projectIdParam ? Number(projectIdParam) : null;
    const tasks = Number.isFinite(projectId)
      ? data.executorTasks.filter((task) => Number(task.project_id) === projectId)
      : data.executorTasks;
    return tasks.sort((left, right) => executorTaskTimestamp(right) - executorTaskTimestamp(left));
  }
  if (method === "GET" && parts.length === 3 && parts[0] === "executor" && parts[1] === "tasks") {
    return data.executorTasks.find((task) => String(task.id) === decodeURIComponent(parts[2])) || null;
  }
  if (method === "GET" && parts.length === 1 && parts[0] === "operation-logs") {
    return data.operationLogs.sort((left, right) => parseTimestamp(right.created_at) - parseTimestamp(left.created_at));
  }
  if (method === "GET" && parts.length === 2 && parts[0] === "ai" && parts[1] === "settings") {
    return {
      provider: "local-demo",
      model: "offline",
      api_key_configured: false,
      status: "local"
    };
  }
  if (method === "POST" && parts.length === 4 && parts[0] === "projects" && parts[2] === "ai" && parts[3] === "analyze-env") {
    return localAnalysis(data, Number(parts[1]));
  }
  if (method === "POST" && parts.length === 4 && parts[0] === "projects" && parts[2] === "ai" && parts[3] === "analyze-git") {
    return {
      project_id: Number(parts[1]),
      status: "completed",
      summary: "Local Git analysis completed",
      findings: [
        "Main branch is visible in local demo data.",
        "Executor stays headless; task records are reported through the GUI."
      ]
    };
  }
  if (method === "POST" && parts.length === 4 && parts[0] === "projects" && parts[2] === "ai" && parts[3] === "config-plan") {
    return localPlan(data, Number(parts[1]), body);
  }
  if (method === "POST" && parts.length === 4 && parts[0] === "projects" && parts[2] === "ai" && parts[3] === "plan-action") {
    const plan = localPlan(data, Number(parts[1]), body);
    const response = {
      project_id: Number(parts[1]),
      goal: body.goal,
      status: body.auto_execute ? "queued" : "ready",
      message: body.auto_execute ? "Local executor task queued" : "Local action plan ready",
      target_server: data.servers.find((server) => Number(server.id) === Number(body.target_server_id)),
      plan,
      safety_report: plan.steps.map((step) => ({ step: step.title, level: step.risk_level }))
    };
    if (body.auto_execute) {
      response.tasks = [
        localAddTask(data, {
          project_id: Number(parts[1]),
          server_id: Number(body.target_server_id),
          task_type: "execute_config_plan",
          status: "completed",
          message: "Local action plan executed",
          result: {
            success: true,
            steps: plan.steps.length
          }
        })
      ];
      localAddOperationLog(data, {
        project_id: Number(parts[1]),
        server_id: Number(body.target_server_id),
        operation_type: "plan_action",
        risk_level: "medium",
        summary: "Queued local executor-safe action"
      });
    }
    return commit(response);
  }
  if (method === "POST" && parts.length === 2 && parts[0] === "reports" && parts[1] === "project") {
    return {
      content: localMarkdownReport(data, Number(body.project_id))
    };
  }
  if (
    method === "POST" &&
    parts.length === 5 &&
    parts[0] === "projects" &&
    parts[2] === "servers" &&
    parts[4] === "execute-config-plan"
  ) {
    const task = localAddTask(data, {
      project_id: Number(parts[1]),
      server_id: Number(parts[3]),
      task_type: "execute_config_plan",
      status: "completed",
      message: "Local config plan execution completed",
      result: {
        success: true,
        steps: Array.isArray(body.steps) ? body.steps.length : 0
      }
    });
    localAddOperationLog(data, {
      project_id: Number(parts[1]),
      server_id: Number(parts[3]),
      operation_type: "execute_config_plan",
      risk_level: "medium",
      summary: "Executed local config plan"
    });
    return commit({
      status: "completed",
      message: "Local config plan execution completed",
      tasks: [task],
      safety_report: (body.steps || []).map((step) => ({ step: step.title || step.command, level: step.risk_level || "low" })),
      results: [{ status: "completed", message: "Simulated locally" }]
    });
  }

  return null;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  const codeSpans = [];
  let html = escapeHtml(value).replace(/`([^`]+)`/g, (_, code) => {
    const marker = `@@CODE_SPAN_${codeSpans.length}@@`;
    codeSpans.push(`<code>${code}</code>`);
    return marker;
  });

  html = html
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');

  return html.replace(/@@CODE_SPAN_(\d+)@@/g, (_, index) => codeSpans[Number(index)] || "");
}

function splitMarkdownTableRow(line) {
  const trimmed = line.trim();
  const withoutLeadingPipe = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const withoutOuterPipes = withoutLeadingPipe.endsWith("|")
    ? withoutLeadingPipe.slice(0, -1)
    : withoutLeadingPipe;
  return withoutOuterPipes.split("|").map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line) {
  const cells = splitMarkdownTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function renderMarkdownTable(headerLine, bodyLines) {
  const headerCells = splitMarkdownTableRow(headerLine);
  const bodyRows = bodyLines.map(splitMarkdownTableRow);

  return `
    <div class="markdown-table-wrap">
      <table>
        <thead>
          <tr>${headerCells.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${bodyRows
            .map(
              (row) => `
                <tr>
                  ${headerCells
                    .map((_, index) => `<td>${renderInlineMarkdown(row[index] || "")}</td>`)
                    .join("")}
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderMarkdown(markdown) {
  if (!markdown) {
    return `<p class="muted-copy">后端未返回报告内容</p>`;
  }

  const lines = String(markdown).replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let inCodeBlock = false;
  let codeLines = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listType || !listItems.length) return;
    blocks.push(`<${listType}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${listType}>`);
    listType = null;
    listItems = [];
  };

  const flushCodeBlock = () => {
    blocks.push(`<pre class="markdown-code"><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    inCodeBlock = false;
    codeLines = [];
  };

  const pushListItem = (type, item) => {
    flushParagraph();
    if (listType && listType !== type) {
      flushList();
    }
    listType = type;
    listItems.push(item);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (inCodeBlock) {
      if (trimmed.startsWith("```")) {
        flushCodeBlock();
      } else {
        codeLines.push(line);
      }
      continue;
    }

    if (trimmed.startsWith("```")) {
      flushParagraph();
      flushList();
      inCodeBlock = true;
      codeLines = [];
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (trimmed.includes("|") && isMarkdownTableSeparator(lines[index + 1] || "")) {
      flushParagraph();
      flushList();
      const tableRows = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        tableRows.push(lines[index]);
        index += 1;
      }
      index -= 1;
      blocks.push(renderMarkdownTable(trimmed, tableRows));
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      pushListItem("ul", trimmed.replace(/^[-*]\s+/, ""));
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      pushListItem("ol", trimmed.replace(/^\d+\.\s+/, ""));
      continue;
    }

    if (/^>\s?/.test(trimmed)) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${renderInlineMarkdown(trimmed.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      flushList();
      blocks.push("<hr />");
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  flushList();
  if (inCodeBlock) {
    flushCodeBlock();
  }

  return blocks.join("\n");
}

function formatTime(value) {
  if (!value) return MISSING_VALUE;
  try {
    return new Date(value).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return value;
  }
}

function compactTime(value) {
  if (!value) return MISSING_VALUE;
  try {
    return new Date(value).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  } catch {
    return value;
  }
}

function selectedProject() {
  return state.projects.find((project) => project.id === Number(state.selectedProjectId)) || state.projects[0] || null;
}

function selectedTargetServer() {
  const servers = currentStatusServers();
  return servers[1] || servers[0] || null;
}

async function request(path, options = {}, fallback) {
  if (state.localDemoActive && !options.forceRemote) {
    const localResult = localRequest(path, options);
    return localResult === null ? fallback : localResult;
  }

  const shouldUseProxy = shouldProxyApiBase(state.apiBase);
  const invoke = shouldUseProxy ? null : tauriInvoke();
  const url = shouldUseProxy ? `${LOCAL_API_PROXY_BASE}${path}` : `${state.apiBase}${path}`;
  const headers = {
    ...(options.headers || {})
  };

  if (options.body) {
    headers["Content-Type"] = "application/json";
  }
  if (shouldUseProxy) {
    headers["X-ProjectPilot-Upstream"] = state.apiBase;
  }

  const init = {
    method: options.method || "GET",
    headers
  };
  let timeoutHandle = null;
  if (typeof AbortController !== "undefined" && !invoke) {
    const controller = new AbortController();
    init.signal = controller.signal;
    timeoutHandle = window.setTimeout(() => controller.abort(), options.timeoutMs || REQUEST_TIMEOUT_MS);
  }

  if (options.body) {
    init.body = JSON.stringify(options.body);
  }

  try {
    if (invoke) {
      const result = await invoke("api_request", {
        method: init.method,
        url,
        body: options.body || null
      });
      state.backendMode = "connected";
      state.backendIssue = "";
      state.localDemoActive = false;
      return result;
    }

    const response = await fetch(url, init);
    if (!response.ok) {
      const error = new Error(`${response.status} ${response.statusText}`);
      error.httpStatus = response.status;
      throw error;
    }
    state.backendMode = "connected";
    state.backendIssue = "";
    state.localDemoActive = false;
    const text = await response.text();
    if (timeoutHandle) {
      window.clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }
    if (!text) {
      return { ok: true };
    }
    try {
      return JSON.parse(text);
    } catch {
      return { content: text };
    }
  } catch (error) {
    if (timeoutHandle) {
      window.clearTimeout(timeoutHandle);
    }
    if (error?.name === "AbortError") {
      error = new Error(`Request timed out after ${(options.timeoutMs || REQUEST_TIMEOUT_MS) / 1000}s`);
    }
    const canUseLocalDemo = !error?.httpStatus || error.httpStatus >= 500;
    if (canUseLocalDemo) {
      const localResult = localRequest(path, options);
      if (localResult !== null) {
        state.backendMode = "local";
        state.backendIssue = error?.message || "Remote backend is unavailable";
        state.localDemoActive = true;
        return localResult;
      }
    }
    if (!options.optional) {
      state.backendMode = "error";
      state.backendIssue = error?.message || "Request failed";
    }
    if (typeof fallback === "function") return fallback(error);
    return fallback;
  }
}

function normalizeTaskList(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.tasks)) return value.tasks;
  if (Array.isArray(value?.items)) return value.items;
  return [];
}

async function loadData({ silent = false } = {}) {
  if (!state.user) return;
  state.isLoading = true;
  if (!silent) render();

  const [projectsResponse, serversResponse] = await Promise.all([
    request("/projects", {}, null),
    request("/servers", {}, null)
  ]);
  state.dataLoaded.projects = Array.isArray(projectsResponse);
  state.projects = state.dataLoaded.projects ? projectsResponse : [];
  state.dataLoaded.servers = Array.isArray(serversResponse);
  state.servers = state.dataLoaded.servers ? serversResponse : [];

  if (
    state.projects[0] &&
    (!state.selectedProjectId || !state.projects.some((project) => Number(project.id) === Number(state.selectedProjectId)))
  ) {
    state.selectedProjectId = state.projects[0].id;
  }

  const project = selectedProject();
  const projectId = project?.id;
  if (state.contextProjectId !== projectId) {
    state.contextProjectId = projectId || null;
    state.analysis = null;
    state.gitAnalysis = null;
    state.plan = null;
    state.actionPlan = null;
    state.executionResult = null;
    state.executorTaskDetail = null;
    state.serverDetail = null;
    state.selectedServerId = null;
    state.report = "";
  }
  const [statusResponse, bindingsResponse, tasksResponse, aiSettingsResponse, activitiesResponse] = await Promise.all([
    projectId ? request(`/projects/${projectId}/status`, {}, null) : null,
    projectId ? request(`/projects/${projectId}/servers`, {}, null) : null,
    request(projectId ? `/executor/tasks?project_id=${projectId}` : "/executor/tasks", { optional: true }, []),
    request("/ai/settings", { optional: true }, null),
    request("/operation-logs", {}, [])
  ]);
  state.dataLoaded.status = Boolean(statusResponse);
  state.status = statusResponse || { project: project || null, servers: [] };
  state.dataLoaded.bindings = Array.isArray(bindingsResponse);
  state.bindings = state.dataLoaded.bindings ? bindingsResponse : [];
  state.executorTasks = normalizeTaskList(tasksResponse);
  state.aiSettings = aiSettingsResponse;
  state.activities = Array.isArray(activitiesResponse) ? activitiesResponse : [];
  state.lastSync = new Date().toISOString();
  state.isLoading = false;
  render();
}

function parseTimestamp(value) {
  const time = Date.parse(value || "");
  return Number.isFinite(time) ? time : 0;
}

function executorTaskTimestamp(task) {
  if (!task) return 0;
  return Math.max(
    parseTimestamp(task.completed_at),
    parseTimestamp(task.claimed_at),
    parseTimestamp(task.created_at)
  );
}

function latestExecutorTask(serverId, taskType) {
  const projectId = Number(state.selectedProjectId || state.status?.project?.id || selectedProject()?.id);
  if (!Number.isFinite(projectId)) {
    return null;
  }
  return (state.executorTasks || [])
    .filter(
      (task) =>
        Number(task.server_id) === Number(serverId) &&
        task.task_type === taskType &&
        (!task.project_id || Number(task.project_id) === projectId)
    )
    .sort((left, right) => executorTaskTimestamp(right) - executorTaskTimestamp(left))[0] || null;
}

function latestDetectionRecord(taskStreamRecord, statusRecord) {
  if (!taskStreamRecord) return statusRecord || null;
  if (!statusRecord) return taskStreamRecord || null;
  return executorTaskTimestamp(taskStreamRecord) >= executorTaskTimestamp(statusRecord)
    ? taskStreamRecord
    : statusRecord;
}

function isTaskNewerThanRecord(task, record) {
  if (!task) return false;
  if (!record?.created_at) return true;
  return executorTaskTimestamp(task) > parseTimestamp(record.created_at);
}

function executorTaskMessage(task) {
  return (
    task?.message ||
    task?.result?.message ||
    task?.error_type ||
    task?.result?.error_type ||
    task?.status ||
    MISSING_VALUE
  );
}

function currentStatusServers() {
  const serverById = new Map((state.servers || []).map((server) => [Number(server.id), server]));
  const statusByServerId = new Map((state.status?.servers || []).map((server) => [Number(server.server_id), server]));
  const bindingByServerId = new Map((state.bindings || []).map((binding) => [Number(binding.server_id), binding]));
  const ids = [
    ...new Set([
      ...Array.from(statusByServerId.keys()),
      ...Array.from(bindingByServerId.keys())
    ])
  ];

  return ids.map((serverId) => {
    const statusServer = statusByServerId.get(serverId) || {};
    const binding = bindingByServerId.get(serverId) || {};
    const serverRecord = serverById.get(serverId);
    const server = {
      ...binding,
      ...statusServer,
      server_id: serverId,
      server_name: statusServer.server_name || binding.server_name || serverRecord?.name,
      project_path: statusServer.project_path || binding.project_path
    };
    return {
      ...server,
      server_name: displayValue(server.server_name),
      host: displayValue(server.host || serverRecord?.host),
      port: displayValue(server.port || serverRecord?.port),
      username: displayValue(server.username || serverRecord?.username),
      connection_mode: displayValue(server.connection_mode || serverRecord?.connection_mode),
      connection_status: displayValue(server.connection_status || serverRecord?.connection_status),
      latest_executor_git_task: latestDetectionRecord(
        latestExecutorTask(server.server_id, "detect_git"),
        server.latest_git_detection
      ),
      latest_executor_environment_task: latestDetectionRecord(
        latestExecutorTask(server.server_id, "detect_environment"),
        server.latest_environment_detection
      )
    };
  });
}

function gitDisplay(server) {
  const git = server.latest_git_status;
  const task = server.latest_executor_git_task;

  if (task && isTaskNewerThanRecord(task, git)) {
    const result = task.result || {};
    const taskTime = task.completed_at || task.claimed_at || task.created_at;
    if (task.status === "completed" && result.success !== false) {
      const branch = displayValue(result.branch);
      return {
        branch,
        commit: displayValue(result.last_commit),
        timestamp: taskTime,
        className: branch === "main" ? "" : "warn-text",
        isRisk:
          branch !== "main" ||
          Number(result.ahead || 0) > 0 ||
          Number(result.behind || 0) > 0 ||
          Boolean(result.has_uncommitted_changes)
      };
    }

    if (isPendingTaskStatus(task.status)) {
      return {
        branch: task.status,
        commit: "waiting executor",
        timestamp: taskTime,
        className: "warn-text",
        isRisk: true
      };
    }

    return {
      branch: "detect failed",
      commit: executorTaskMessage(task),
      timestamp: taskTime,
      className: "warn-text",
      isRisk: true
    };
  }

  const branch = displayValue(git?.branch);
  return {
    branch,
    commit: displayValue(git?.last_commit),
    timestamp: git?.created_at,
    className: branch === "main" ? "" : "warn-text",
    isRisk:
      !git ||
      branch !== "main" ||
      Number(git.ahead || 0) > 0 ||
      Number(git.behind || 0) > 0 ||
      Boolean(git.has_uncommitted_changes)
  };
}

function environmentDisplay(server) {
  const env = server.latest_environment_snapshot;
  const task = server.latest_executor_environment_task;

  if (task && isTaskNewerThanRecord(task, env) && !(task.status === "completed" && task.result?.success !== false)) {
    const taskTime = task.completed_at || task.claimed_at || task.created_at;
    if (isPendingTaskStatus(task.status)) {
      return {
        python: task.status,
        node: MISSING_VALUE,
        docker: "waiting executor",
        dockerClass: "warn-text",
        timestamp: taskTime,
        isIssue: true
      };
    }

    return {
      python: "detect failed",
      node: MISSING_VALUE,
      docker: executorTaskMessage(task),
      dockerClass: "warn-text",
      timestamp: taskTime,
      isIssue: true
    };
  }

  const source = task && isTaskNewerThanRecord(task, env) && task.result?.success !== false ? task.result : env;
  const diskUsage = Number(String(source?.disk_usage || "").replace("%", ""));
  const hasDockerState = typeof source?.docker_running === "boolean";
  return {
    python: displayValue(source?.python_version),
    node: displayValue(source?.node_version),
    docker: hasDockerState ? (source.docker_running ? "running" : "stopped") : MISSING_VALUE,
    dockerClass: hasDockerState && source.docker_running ? "ok-text" : "warn-text",
    timestamp: source?.created_at || task?.completed_at || task?.claimed_at || task?.created_at,
    isIssue: !source || !hasDockerState || !source.docker_running || diskUsage > 80
  };
}

function latestServerScanTime(server) {
  const git = gitDisplay(server);
  const env = environmentDisplay(server);
  return parseTimestamp(env.timestamp) >= parseTimestamp(git.timestamp) ? env.timestamp : git.timestamp;
}

function bindingPathSummary(servers) {
  const paths = [...new Set(servers.map((server) => server.project_path).filter(Boolean))];
  if (paths.length === 0) return MISSING_VALUE;
  if (paths.length === 1) return paths[0];
  return `${paths.length} binding paths`;
}

function serverLabel(server) {
  return `${displayValue(server.name || server.server_name)} (${displayValue(server.host)}:${displayValue(server.port)})`;
}

function renderServerOptions(selectedValue, { allowBlank = true } = {}) {
  const options = state.servers
    .map(
      (server) => `
        <option value="${server.id}" ${String(selectedValue) === String(server.id) ? "selected" : ""}>
          ${escapeHtml(serverLabel(server))}
        </option>
      `
    )
    .join("");
  return `${allowBlank ? `<option value="">${MISSING_VALUE}</option>` : ""}${options}`;
}

function taskServerName(task) {
  const server = state.servers.find((item) => Number(item.id) === Number(task.server_id));
  return displayValue(server?.name || task.server_name || task.executor_id);
}

function taskMessage(task) {
  return displayValue(task.message || task.error_type || task.result?.message || task.result?.error_type);
}

function planSteps(planLike) {
  if (Array.isArray(planLike?.steps)) return planLike.steps;
  if (Array.isArray(planLike?.plan?.steps)) return planLike.plan.steps;
  return [];
}

function taskStatusTone(status) {
  if (status === "completed" || status === "success") return "healthy";
  if (status === "failed" || status === "blocked" || status === "error") return "danger";
  if (status === "queued" || status === "running" || status === "claimed") return "warning";
  return "muted";
}

function isPendingTaskStatus(status) {
  return ["queued", "running", "claimed"].includes(status);
}

function booleanDisplay(value) {
  if (typeof value !== "boolean") return displayValue(value);
  return value ? "true" : "false";
}

function renderEmptyRow(colspan, message = MISSING_VALUE) {
  return `
    <tr>
      <td colspan="${colspan}"><span class="empty-state">${escapeHtml(message)}</span></td>
    </tr>
  `;
}

function renderJsonBlock(value) {
  if (!value) return MISSING_VALUE;
  return JSON.stringify(value, null, 2);
}

function projectIdForActions() {
  return state.selectedProjectId || selectedProject()?.id || state.status?.project?.id;
}

function planTargetServerId() {
  return state.plan?.target_server_id || state.actionPlan?.target_server?.id || selectedTargetServer()?.server_id;
}

function computeDashboard() {
  const servers = currentStatusServers();
  let gitRisks = 0;
  let envIssues = 0;

  servers.forEach((server) => {
    if (gitDisplay(server).isRisk) {
      gitRisks += 1;
    }
    if (environmentDisplay(server).isIssue) {
      envIssues += 1;
    }
  });

  const healthScore = servers.length ? Math.max(35, 100 - gitRisks * 9 - envIssues * 12) : MISSING_VALUE;
  return { servers, gitRisks, envIssues, healthScore };
}

function statusTone(server) {
  const git = gitDisplay(server);
  const env = environmentDisplay(server);
  if (git.branch === MISSING_VALUE || env.python === MISSING_VALUE) return "muted";
  if (git.isRisk || env.isIssue) return "warning";
  return "healthy";
}

function riskTone(risk) {
  if (risk === "high") return "danger";
  if (risk === "medium") return "warning";
  if (risk === "low") return "healthy";
  return "muted";
}

function setToast(message) {
  state.toast = message;
  updateToast();
  window.clearTimeout(setToast.timer);
  setToast.timer = window.setTimeout(() => {
    state.toast = "";
    updateToast();
  }, 2800);
}

function captureEditingState() {
  const element = document.activeElement;
  if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement)) {
    return null;
  }

  const form = element.closest("[data-draft-form]");
  if (!form || !element.name) {
    return null;
  }

  return {
    draftKey: form.dataset.draftForm,
    fieldName: element.name,
    selectionStart: element instanceof HTMLSelectElement ? null : element.selectionStart,
    selectionEnd: element instanceof HTMLSelectElement ? null : element.selectionEnd,
  };
}

function restoreEditingState(editingState) {
  if (!editingState) {
    return;
  }

  window.requestAnimationFrame(() => {
    const selector = `[data-draft-form="${editingState.draftKey}"] [name="${editingState.fieldName}"]`;
    const element = document.querySelector(selector);
    if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement)) {
      return;
    }

    element.focus();
    if (
      !(element instanceof HTMLSelectElement) &&
      editingState.selectionStart !== null &&
      editingState.selectionEnd !== null
    ) {
      element.setSelectionRange(editingState.selectionStart, editingState.selectionEnd);
    }
  });
}

function renderToast() {
  return state.toast ? `<div class="toast" role="status">${escapeHtml(state.toast)}</div>` : "";
}

function updateToast() {
  const existingToast = document.querySelector(".toast");
  if (!state.toast) {
    existingToast?.remove();
    return;
  }

  if (existingToast) {
    existingToast.textContent = state.toast;
    return;
  }

  const app = document.querySelector("#app");
  app?.insertAdjacentHTML("beforeend", renderToast());
}

function render() {
  const editingState = captureEditingState();
  const app = document.querySelector("#app");
  if (!state.user) {
    app.innerHTML = renderLogin();
    bindLogin();
    restoreEditingState(editingState);
    return;
  }

  app.innerHTML = `
    <div class="app-shell">
      ${renderSidebar()}
      <main class="main-surface">
        ${renderTopbar()}
        <section class="workspace" data-route="${state.route}">
          ${renderConnectionBanner()}
          ${renderRoute()}
        </section>
      </main>
      ${renderToast()}
    </div>
  `;

  bindShell();
  restoreEditingState(editingState);
}

function renderLogin() {
  return `
    <main class="login-screen">
      <section class="login-brand">
        <img class="brand-mark" src="./src/assets/projectpilot-icon.png" alt="ProjectPilot" />
        <h1>ProjectPilot</h1>
        <p>AI 项目环境健康监控桌面端</p>
        <div class="login-preview">
          <span></span>
          <strong>API</strong>
          <small>Remote or Local</small>
        </div>
      </section>
      <form class="login-panel" data-login-form data-draft-form="login">
        <h2>登录管理台</h2>
        <p>使用本地登录入口进入，远端不可用时自动切到 Local Demo。</p>
        <label>
          <span>邮箱</span>
          <input name="email" type="email" value="${escapeHtml(state.drafts.login.email)}" autocomplete="email" />
        </label>
        <label>
          <span>密码</span>
          <input name="password" type="password" value="${escapeHtml(state.drafts.login.password)}" autocomplete="current-password" />
        </label>
        <button type="submit">进入 ProjectPilot</button>
      </form>
    </main>
  `;
}

function renderSidebar() {
  const items = [
    ["dashboard", "Dashboard", "▦"],
    ["projects", "Projects", "□"],
    ["servers", "Servers", "▤"],
    ["bindings", "Bindings", "⇄"],
    ["reports", "AI Ops", "✦"],
    ["tasks", "Tasks", "≡"],
    ["api", "API Map", "⌁"],
    ["settings", "Settings", "⚙"]
  ];

  return `
    <aside class="sidebar">
      <div class="brand">
        <img class="brand-mark small" src="./src/assets/projectpilot-icon.png" alt="" aria-hidden="true" />
        <div>
          <strong>ProjectPilot</strong>
          <span>AI Project Health Monitor</span>
        </div>
      </div>
      <nav class="nav-list" aria-label="ProjectPilot navigation">
        ${items
          .map(
            ([route, label, icon]) => `
              <button class="nav-item ${state.route === route ? "active" : ""}" data-route="${route}" type="button">
                <span>${icon}</span>
                ${label}
              </button>
            `
          )
          .join("")}
      </nav>
      <div class="side-version">
        <strong>Desktop Preview</strong>
        <span>v0.1.0</span>
      </div>
    </aside>
  `;
}

function backendModeMeta() {
  if (state.backendMode === "connected") {
    return {
      className: "online",
      label: "Backend online",
      summary: "Remote API",
      detail: state.apiBase
    };
  }
  if (state.backendMode === "local") {
    return {
      className: "local",
      label: "Local demo",
      summary: "Local Demo Store",
      detail: state.backendIssue || "Remote backend is unavailable."
    };
  }
  if (state.backendMode === "error") {
    return {
      className: "error",
      label: "Backend error",
      summary: "Remote API unavailable",
      detail: state.backendIssue || "Request failed."
    };
  }
  return {
    className: "checking",
    label: "Checking API",
    summary: "Connecting",
    detail: state.apiBase
  };
}

function renderTopbar() {
  const mode = backendModeMeta();
  const projectOptions = state.projects
    .map(
      (project) => `
        <option value="${project.id}" ${project.id === Number(state.selectedProjectId) ? "selected" : ""}>
          ${escapeHtml(project.name)}
        </option>
      `
    )
    .join("");

  return `
    <header class="topbar">
      <div>
        <p class="eyebrow">Last Sync ${compactTime(state.lastSync)}</p>
        <h2>${pageTitle()}</h2>
      </div>
      <div class="top-actions">
        <select data-project-select aria-label="选择项目">${projectOptions}</select>
        <span class="connection ${mode.className}">${mode.label}</span>
        <button class="icon-button" type="button" data-refresh title="刷新数据" ${actionAttrs("refresh-data")}>${actionText("refresh-data", "↻", "…")}</button>
        <button class="user-pill" type="button" data-route="settings">
          <span>${escapeHtml(state.user.initials)}</span>
          ${escapeHtml(state.user.name)}
        </button>
      </div>
    </header>
  `;
}

function renderConnectionBanner() {
  const mode = backendModeMeta();
  if (state.backendMode === "connected") {
    return "";
  }

  return `
    <section class="mode-banner ${mode.className}" aria-live="polite">
      <div>
        <strong>${escapeHtml(mode.summary)}</strong>
        <span>${escapeHtml(mode.detail)}</span>
      </div>
      <div class="row-actions">
        <button type="button" data-use-local-demo ${actionAttrs("use-local-demo")}>${actionText("use-local-demo", "Use Local Demo")}</button>
        <button type="button" data-retry-backend ${actionAttrs("retry-backend")}>${actionText("retry-backend", "Retry Backend", "Retrying...")}</button>
      </div>
    </section>
  `;
}

function pageTitle() {
  return {
    dashboard: "Dashboard",
    projects: "Projects",
    servers: "Servers",
    serverDetail: "Server Detail",
    bindings: "Bindings",
    reports: "AI Ops",
    tasks: "Executor Tasks",
    api: "API Map",
    settings: "Settings"
  }[state.route];
}

function renderRoute() {
  if (state.isLoading) {
    return `<div class="loading-band"><span></span>正在加载 ProjectPilot 数据...</div>`;
  }
  if (state.route === "projects") return renderProjects();
  if (state.route === "servers") return renderServers();
  if (state.route === "serverDetail") return renderServerDetail();
  if (state.route === "bindings") return renderBindings();
  if (state.route === "reports") return renderReports();
  if (state.route === "tasks") return renderTasks();
  if (state.route === "api") return renderApiMap();
  if (state.route === "settings") return renderSettings();
  return renderDashboard();
}

function renderDashboard() {
  const { servers, gitRisks, envIssues, healthScore } = computeDashboard();
  const project = state.status?.project || selectedProject();
  const mainIssue = state.analysis?.issues?.[0] || MISSING_VALUE;
  const pathSummary = bindingPathSummary(servers);
  const projectCount = state.dataLoaded.projects ? state.projects.length : MISSING_VALUE;
  const serverCount = state.dataLoaded.servers ? state.servers.length : MISSING_VALUE;
  const gitRiskCount = state.dataLoaded.status ? gitRisks : MISSING_VALUE;
  const envIssueCount = state.dataLoaded.status ? envIssues : MISSING_VALUE;
  const projectName = displayValue(project?.name);
  const riskLevel = displayValue(state.analysis?.risk_level);

  return `
    <div class="dashboard-grid">
      <section class="metric-card health">
        <span>Health Score</span>
        <strong>${escapeHtml(healthScore)}</strong>
        <small>${healthScore === MISSING_VALUE ? MISSING_VALUE : "/ 100"}</small>
        <div class="sparkline"><i></i></div>
      </section>
      ${renderMetric("Total Projects", projectCount, "Active projects", "folder")}
      ${renderMetric("Total Servers", serverCount, "Monitored servers", "server")}
      ${renderMetric("Git Risks", gitRiskCount, "Repositories at risk", "risk")}
      ${renderMetric("Environment Issues", envIssueCount, "Servers with issues", "issue")}
    </div>

    ${renderWorkflowRail()}

    <div class="content-grid">
      <section class="panel wide">
        <div class="panel-header">
          <h3>Server Health Overview</h3>
          <button type="button" data-detect-project ${actionAttrs("detect-project")}>${actionText("detect-project", "Run Detection", "Queuing...")}</button>
        </div>
        <div class="table-wrap dashboard-table-wrap">
          <table class="dashboard-table health-table">
            <thead>
              <tr>
                <th>Server</th>
                <th>Status</th>
                <th>Branch</th>
                <th>Python</th>
                <th>Docker</th>
                <th>Last Scan</th>
              </tr>
            </thead>
            <tbody>
              ${servers.length ? servers.map(renderServerRow).join("") : renderEmptyRow(6, "没有返回绑定服务器")}
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel ai-panel">
        <div class="panel-header">
          <h3>AI Insight</h3>
          <button type="button" data-generate-ai ${actionAttrs("refresh-ai")}>${actionText("refresh-ai", "Refresh AI", "Running...")}</button>
        </div>
        <div class="insight-box">
          <strong>${escapeHtml(projectName)} 当前风险</strong>
          <p>${escapeHtml(mainIssue)}</p>
          <ul>
            ${(state.analysis?.issues || []).slice(0, 3).map((issue) => `<li>${escapeHtml(issue)}</li>`).join("")}
          </ul>
          <span class="risk ${riskTone(state.analysis?.risk_level)}">Risk Level: ${escapeHtml(riskLevel)}</span>
        </div>
      </section>

      <section class="panel wide">
        <div class="panel-header">
          <h3>Git & Environment Matrix</h3>
          <span>${escapeHtml(pathSummary)}</span>
        </div>
        <div class="table-wrap dashboard-table-wrap">
          <table class="dashboard-table matrix-table">
            <thead>
              <tr>
                <th>Environment</th>
                <th>Project Path</th>
                <th>Branch</th>
                <th>Commit</th>
                <th>Python</th>
                <th>Node</th>
                <th>Docker</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${servers.length ? servers.map(renderMatrixRow).join("") : renderEmptyRow(8, "没有返回状态矩阵")}
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3>Recent Activity</h3>
          <button type="button" data-route="api">View API</button>
        </div>
        <div class="activity-list">
          ${(state.activities || []).length ? (state.activities || []).map(renderActivity).join("") : `<p class="muted-copy">${MISSING_VALUE}</p>`}
        </div>
      </section>
    </div>

    <section class="panel recommendation">
      <div class="panel-header">
        <h3>AI Recommendation</h3>
        <button type="button" data-route="reports">Open Report</button>
      </div>
      <div class="steps">
        ${planSteps(state.plan).length ? planSteps(state.plan).map(renderStep).join("") : `<p class="muted-copy">${MISSING_VALUE}</p>`}
      </div>
    </section>
  `;
}

function renderWorkflowRail() {
  const project = selectedProject();
  const binding = (state.bindings || [])[0] || null;
  const server = binding ? bindingServerRecord(binding) : null;
  const servers = currentStatusServers();
  const detectionServer = servers.find((item) => Number(item.server_id) === Number(binding?.server_id)) || servers[0] || null;
  const latestTask = (state.executorTasks || [])[0] || null;
  const git = detectionServer ? gitDisplay(detectionServer) : null;
  const env = detectionServer ? environmentDisplay(detectionServer) : null;
  const steps = [
    {
      label: "Project",
      value: displayValue(project?.name),
      done: Boolean(project)
    },
    {
      label: "Server",
      value: displayValue(server?.name || binding?.server_name),
      done: Boolean(server || binding?.server_id)
    },
    {
      label: "Binding",
      value: displayValue(binding?.project_path),
      done: Boolean(binding?.project_path)
    },
    {
      label: "Detection",
      value: git || env ? compactTime(latestServerScanTime(detectionServer)) : MISSING_VALUE,
      done: Boolean(git || env)
    },
    {
      label: "Task Result",
      value: displayValue(latestTask?.status),
      done: Boolean(latestTask)
    }
  ];

  return `
    <section class="workflow-rail" aria-label="ProjectPilot main workflow">
      ${steps
        .map(
          (step, index) => `
            <article class="${step.done ? "complete" : ""}">
              <span>${index + 1}</span>
              <div>
                <strong>${escapeHtml(step.label)}</strong>
                <small>${escapeHtml(step.value)}</small>
              </div>
            </article>
          `
        )
        .join("")}
    </section>
  `;
}

function renderMetric(title, value, helper, tone) {
  return `
    <section class="metric-card ${tone}">
      <span>${title}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${helper}</small>
    </section>
  `;
}

function renderServerRow(server) {
  const tone = statusTone(server);
  const git = gitDisplay(server);
  const env = environmentDisplay(server);
  return `
    <tr>
      <td>
        <strong>${escapeHtml(server.server_name)}</strong>
        <span>${escapeHtml(server.host)}:${escapeHtml(server.port)} · ${escapeHtml(server.connection_mode)}</span>
      </td>
      <td><span class="badge ${tone}">${tone === "healthy" ? "Healthy" : tone === "warning" ? "Warning" : "Unknown"}</span></td>
      <td class="${git.className}">${escapeHtml(git.branch)}</td>
      <td>${escapeHtml(env.python)}</td>
      <td class="${env.dockerClass}">${escapeHtml(env.docker)}</td>
      <td>${compactTime(latestServerScanTime(server))}</td>
    </tr>
  `;
}

function renderMatrixRow(server) {
  const tone = statusTone(server);
  const git = gitDisplay(server);
  const env = environmentDisplay(server);
  return `
    <tr>
      <td>${escapeHtml(server.server_name)}</td>
      <td>${escapeHtml(displayValue(server.project_path))}</td>
      <td class="${git.className}">${escapeHtml(git.branch)}</td>
      <td>${escapeHtml(git.commit)}</td>
      <td>${escapeHtml(env.python)}</td>
      <td>${escapeHtml(env.node)}</td>
      <td class="${env.dockerClass}">${escapeHtml(env.docker)}</td>
      <td><span class="badge ${tone}">${tone === "healthy" ? "Healthy" : tone === "warning" ? "Warning" : "Unknown"}</span></td>
    </tr>
  `;
}

function renderActivity(item) {
  return `
    <article class="activity-item">
      <span class="dot ${riskTone(item.risk_level)}"></span>
      <div>
        <strong>${escapeHtml(displayValue(item.summary))}</strong>
        <small>${escapeHtml(displayValue(item.operation_type))} · ${escapeHtml(displayValue(item.status))}</small>
      </div>
      <time>${compactTime(item.created_at)}</time>
    </article>
  `;
}

function renderStep(step) {
  const order = displayValue(step.order);
  const title = displayValue(step.title);
  const description = displayValue(step.description || step.command);
  const risk = displayValue(step.risk_level);
  return `
    <article class="step-card">
      <span>${escapeHtml(order)}</span>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <small>${escapeHtml(description)}</small>
        ${step.command ? `<code class="step-command">${escapeHtml(step.command)}</code>` : ""}
      </div>
      <em class="${riskTone(step.risk_level)}">${escapeHtml(risk)}</em>
    </article>
  `;
}

function renderProjects() {
  return `
    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3>Project Registry</h3>
          <span>${state.projects.length} projects</span>
        </div>
        <div class="list-stack">
          ${state.projects.length
            ? state.projects
                .map(
                  (project) => `
                <button class="list-item ${project.id === Number(state.selectedProjectId) ? "active" : ""}" data-select-project="${project.id}" type="button">
                  <strong>${escapeHtml(displayValue(project.name))}</strong>
                  <span>${escapeHtml(displayValue(project.path))}</span>
                  <small>${escapeHtml(displayValue(project.description))}</small>
                </button>
              `
                )
                .join("")
            : `<p class="muted-copy">${MISSING_VALUE}</p>`}
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h3>Add Project</h3>
          <span>POST /projects</span>
        </div>
        <form class="stack-form" data-project-form data-draft-form="project">
          <label>
            <span>项目名称</span>
            <input name="name" type="text" value="${escapeHtml(state.drafts.project.name)}" autocomplete="off" />
          </label>
          <label>
            <span>项目路径</span>
            <input name="path" type="text" value="${escapeHtml(state.drafts.project.path)}" autocomplete="off" />
          </label>
          <label>
            <span>说明</span>
            <textarea name="description">${escapeHtml(state.drafts.project.description)}</textarea>
          </label>
          <button type="submit" ${actionAttrs("create-project")}>${actionText("create-project", "创建项目", "创建中...")}</button>
        </form>
      </section>
    </div>
  `;
}

function renderServers() {
  return `
    <div class="two-column">
      <section class="panel wide-list">
        <div class="panel-header">
          <h3>Server Fleet</h3>
          <span>${state.servers.length} servers</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Host</th>
                <th>User</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${state.servers
                .map(
                  (server) => {
                    const statusTone = server.connection_status === "online" ? "healthy" : server.connection_status ? "warning" : "muted";
                    return `
                      <tr>
                        <td><strong>${escapeHtml(displayValue(server.name))}</strong><span>${escapeHtml(displayValue(server.description))}</span></td>
                        <td>${escapeHtml(displayValue(server.host))}:${escapeHtml(displayValue(server.port))}</td>
                        <td>${escapeHtml(displayValue(server.username))}</td>
                        <td><span class="badge muted">${escapeHtml(displayValue(server.connection_mode))}</span></td>
                        <td><span class="badge ${statusTone}">${escapeHtml(displayValue(server.connection_status))}</span></td>
                        <td>
                          <div class="row-actions">
                            <button type="button" data-check-server="${server.id}" ${actionAttrs(`check-server-${server.id}`)}>${actionText(`check-server-${server.id}`, "Check", "Checking...")}</button>
                            <button type="button" data-server-detail="${server.id}" ${actionAttrs(`server-detail-${server.id}`)}>${actionText(`server-detail-${server.id}`, "Details", "Loading...")}</button>
                          </div>
                        </td>
                      </tr>
                    `;
                  }
                )
                .join("") || renderEmptyRow(6, "没有返回服务器")}
            </tbody>
          </table>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h3>Add Server</h3>
          <span>POST /servers</span>
        </div>
        <form class="stack-form" data-server-form data-draft-form="server">
          <label>
            <span>服务器名</span>
            <input name="name" type="text" value="${escapeHtml(state.drafts.server.name)}" autocomplete="off" />
          </label>
          <label>
            <span>Host</span>
            <input name="host" type="text" value="${escapeHtml(state.drafts.server.host)}" autocomplete="off" />
          </label>
          <label>
            <span>Port</span>
            <input name="port" type="number" value="${escapeHtml(state.drafts.server.port)}" inputmode="numeric" min="1" max="65535" />
          </label>
          <label>
            <span>Username</span>
            <input name="username" type="text" value="${escapeHtml(state.drafts.server.username)}" autocomplete="off" />
          </label>
          <label>
            <span>连接模式</span>
            <select name="connection_mode">
              <option value="executor" ${state.drafts.server.connection_mode === "executor" ? "selected" : ""}>executor</option>
              <option value="local" ${state.drafts.server.connection_mode === "local" ? "selected" : ""}>local</option>
            </select>
          </label>
          <label>
            <span>说明</span>
            <textarea name="description">${escapeHtml(state.drafts.server.description)}</textarea>
          </label>
          <button type="submit" ${actionAttrs("create-server")}>${actionText("create-server", "创建服务器", "创建中...")}</button>
        </form>
      </section>
    </div>
  `;
}

function serverDetailProjectRecord(project) {
  const server = state.serverDetail?.server || {};
  return {
    server_id: server.id || state.selectedServerId,
    server_name: server.name,
    project_path: project.project_path,
    latest_git_status: project.latest_git_status,
    latest_environment_snapshot: project.latest_environment_snapshot,
    latest_executor_git_task: project.latest_git_detection,
    latest_executor_environment_task: project.latest_environment_detection
  };
}

function renderServerDetailProjectRow(project) {
  const record = serverDetailProjectRecord(project);
  const git = gitDisplay(record);
  const env = environmentDisplay(record);
  const tone = git.isRisk || env.isIssue ? "warning" : "healthy";

  return `
    <tr>
      <td>
        <strong>${escapeHtml(displayValue(project.project_name))}</strong>
        <span>ID ${escapeHtml(displayValue(project.project_id))}</span>
      </td>
      <td><code>${escapeHtml(displayValue(project.project_path))}</code></td>
      <td class="${git.className}">${escapeHtml(git.branch)}</td>
      <td>${escapeHtml(git.commit)}</td>
      <td>${escapeHtml(env.python)}</td>
      <td>${escapeHtml(env.node)}</td>
      <td class="${env.dockerClass}">${escapeHtml(env.docker)}</td>
      <td><span class="badge ${tone}">${escapeHtml(tone)}</span></td>
    </tr>
  `;
}

function renderServerDetail() {
  const detail = state.serverDetail;
  const server = detail?.server || state.servers.find((item) => Number(item.id) === Number(state.selectedServerId)) || {};
  const projects = detail?.projects || [];

  return `
    <div class="report-layout">
      <section class="panel">
        <div class="panel-header">
          <h3>Server Status</h3>
          <span>GET /servers/${escapeHtml(displayValue(server.id || state.selectedServerId))}/status</span>
        </div>
        <div class="key-value-list">
          <span>Name</span><strong>${escapeHtml(displayValue(server.name))}</strong>
          <span>Host</span><strong>${escapeHtml(displayValue(server.host))}:${escapeHtml(displayValue(server.port))}</strong>
          <span>User</span><strong>${escapeHtml(displayValue(server.username))}</strong>
          <span>Mode</span><strong>${escapeHtml(displayValue(server.connection_mode))}</strong>
          <span>Description</span><strong>${escapeHtml(displayValue(server.description))}</strong>
        </div>
        <button class="full-button" type="button" data-route="servers">Back to Servers</button>
      </section>
      <section class="panel wide-list">
        <div class="panel-header">
          <h3>Bound Projects</h3>
          <span>${projects.length} projects</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Project</th>
                <th>Project Path</th>
                <th>Git</th>
                <th>Message</th>
                <th>Python</th>
                <th>Node</th>
                <th>Docker</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${projects.length ? projects.map(renderServerDetailProjectRow).join("") : renderEmptyRow(8, "没有返回绑定项目")}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `;
}

function bindingServerRecord(binding) {
  return state.servers.find((server) => Number(server.id) === Number(binding.server_id)) || {};
}

function renderBindingRow(binding) {
  const server = bindingServerRecord(binding);
  const serverId = displayValue(binding.server_id);
  const serverName = displayValue(binding.server_name || server.name);
  const host = displayValue(binding.host || server.host);
  const port = displayValue(binding.port || server.port);
  const username = displayValue(binding.username || server.username);
  const mode = displayValue(binding.connection_mode || server.connection_mode);
  const path = displayValue(binding.project_path);

  return `
    <tr>
      <td>
        <strong>${escapeHtml(serverName)}</strong>
        <span>ID ${escapeHtml(serverId)}</span>
      </td>
      <td>${escapeHtml(host)}:${escapeHtml(port)}</td>
      <td>${escapeHtml(username)}</td>
      <td><span class="badge muted">${escapeHtml(mode)}</span></td>
      <td><code>${escapeHtml(path)}</code></td>
      <td>${formatTime(binding.created_at)}</td>
      <td>
        <div class="row-actions">
          <button type="button" data-detect-server="${escapeHtml(binding.server_id)}" ${actionAttrs(`detect-server-${binding.server_id}`)}>${actionText(`detect-server-${binding.server_id}`, "Detect", "Queuing...")}</button>
          <button class="danger-button" type="button" data-unbind-server="${escapeHtml(binding.server_id)}" ${actionAttrs(`unbind-server-${binding.server_id}`)}>${actionText(`unbind-server-${binding.server_id}`, "Unbind", "Unbinding...")}</button>
        </div>
      </td>
    </tr>
  `;
}

function renderBindings() {
  const project = selectedProject();
  const projectId = projectIdForActions();
  const rows = (state.bindings || []).length
    ? state.bindings.map(renderBindingRow).join("")
    : renderEmptyRow(7, "没有返回项目服务器绑定");

  return `
    <div class="two-column">
      <section class="panel wide-list">
        <div class="panel-header">
          <h3>Project Server Bindings</h3>
          <span>${escapeHtml(displayValue(project?.name))}</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Server</th>
                <th>Host</th>
                <th>User</th>
                <th>Mode</th>
                <th>Project Path</th>
                <th>Bound At</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h3>Bind Server</h3>
          <span>POST /projects/${escapeHtml(displayValue(projectId))}/bind-server</span>
        </div>
        <form class="stack-form" data-binding-form data-draft-form="binding">
          <label>
            <span>服务器</span>
            <select name="server_id">
              ${renderServerOptions(state.drafts.binding.server_id)}
            </select>
          </label>
          <label>
            <span>项目在该服务器上的路径</span>
            <input name="project_path" type="text" value="${escapeHtml(state.drafts.binding.project_path)}" autocomplete="off" />
          </label>
          <button type="submit" ${!projectId ? "disabled" : actionAttrs("bind-server")}>${actionText("bind-server", "绑定服务器", "绑定中...")}</button>
        </form>
      </section>
    </div>
  `;
}

function renderTaskRow(task) {
  const status = displayValue(task.status);
  const tone = taskStatusTone(task.status);
  const taskId = displayValue(task.id);

  return `
    <tr>
      <td><code>${escapeHtml(taskId)}</code></td>
      <td>${escapeHtml(displayValue(task.task_type))}</td>
      <td><span class="badge ${tone}">${escapeHtml(status)}</span></td>
      <td>${escapeHtml(taskServerName(task))}</td>
      <td>${escapeHtml(taskMessage(task))}</td>
      <td>${formatTime(task.created_at)}</td>
      <td>${formatTime(task.completed_at || task.claimed_at)}</td>
      <td><button type="button" data-task-detail="${escapeHtml(task.id)}" ${actionAttrs(`task-detail-${task.id}`)}>${actionText(`task-detail-${task.id}`, "Details", "Loading...")}</button></td>
    </tr>
  `;
}

function renderTasks() {
  const tasks = state.executorTasks || [];
  const completed = tasks.filter((task) => task.status === "completed").length;
  const queued = tasks.filter((task) => task.status === "queued").length;
  const running = tasks.filter((task) => task.status === "running" || task.status === "claimed").length;
  const failed = tasks.filter((task) => ["failed", "blocked", "error"].includes(task.status)).length;
  const rows = tasks.length ? tasks.map(renderTaskRow).join("") : renderEmptyRow(8, "没有返回 executor tasks");

  return `
    <div class="report-layout">
      <section class="panel wide-list">
        <div class="panel-header">
          <h3>Executor Task Stream</h3>
          <button type="button" data-refresh-tasks ${actionAttrs("refresh-tasks")}>${actionText("refresh-tasks", "Refresh Tasks", "Refreshing...")}</button>
        </div>
        <div class="status-strip">
          <span><strong>${tasks.length}</strong> total</span>
          <span><strong>${queued}</strong> queued</span>
          <span><strong>${running}</strong> running</span>
          <span><strong>${completed}</strong> completed</span>
          <span><strong>${failed}</strong> failed</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Type</th>
                <th>Status</th>
                <th>Server</th>
                <th>Message</th>
                <th>Created</th>
                <th>Updated</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h3>Task Detail</h3>
          <span>GET /executor/tasks/{task_id}</span>
        </div>
        <div class="report-preview compact">
          <pre>${escapeHtml(renderJsonBlock(state.executorTaskDetail))}</pre>
        </div>
      </section>
    </div>
  `;
}

function renderReports() {
  const settings = state.aiSettings || {};
  const planItems = planSteps(state.plan);
  const actionItems = planSteps(state.actionPlan);
  const executionTasks = state.executionResult?.tasks || [];
  const safetyReport = state.executionResult?.safety_report || state.actionPlan?.safety_report || [];

  return `
    <div class="ops-layout">
      <section class="panel">
        <div class="panel-header">
          <h3>AI Settings</h3>
          <span>GET /ai/settings</span>
        </div>
        <div class="key-value-list">
          <span>Provider</span><strong>${escapeHtml(displayValue(settings.provider || settings.ai_provider))}</strong>
          <span>Model</span><strong>${escapeHtml(displayValue(settings.model || settings.ai_model))}</strong>
          <span>API Key</span><strong>${escapeHtml(booleanDisplay(settings.api_key_configured ?? settings.has_api_key))}</strong>
          <span>Status</span><strong>${escapeHtml(displayValue(settings.status))}</strong>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3>AI Action Plan</h3>
          <span>POST /projects/{id}/ai/plan-action</span>
        </div>
        <form class="stack-form" data-action-plan-form data-draft-form="actionPlan">
          <label>
            <span>目标</span>
            <textarea name="goal">${escapeHtml(state.drafts.actionPlan.goal)}</textarea>
          </label>
          <div class="form-grid">
            <label>
              <span>源服务器</span>
              <select name="source_server_id">
                ${renderServerOptions(state.drafts.actionPlan.source_server_id)}
              </select>
            </label>
            <label>
              <span>目标服务器</span>
              <select name="target_server_id">
                ${renderServerOptions(state.drafts.actionPlan.target_server_id)}
              </select>
            </label>
          </div>
          <label class="checkbox-row">
            <input name="allow_command_generation" type="checkbox" ${state.drafts.actionPlan.allow_command_generation ? "checked" : ""} />
            <span>允许生成命令</span>
          </label>
          <label class="checkbox-row">
            <input name="auto_execute" type="checkbox" ${state.drafts.actionPlan.auto_execute ? "checked" : ""} />
            <span>直接转入 executor 队列</span>
          </label>
          <label class="checkbox-row">
            <input name="confirmed" type="checkbox" ${state.drafts.actionPlan.confirmed ? "checked" : ""} />
            <span>已人工确认执行</span>
          </label>
          <button type="submit" ${actionAttrs("plan-action")}>${actionText("plan-action", "生成主动计划", "生成中...")}</button>
        </form>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3>Action Preview</h3>
          <span>${escapeHtml(displayValue(state.actionPlan?.status))}</span>
        </div>
        <p class="muted-copy">${escapeHtml(displayValue(state.actionPlan?.message))}</p>
        <div class="steps vertical">
          ${actionItems.length ? actionItems.map(renderStep).join("") : `<p class="muted-copy">${MISSING_VALUE}</p>`}
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3>Config Plan</h3>
          <div class="row-actions">
            <span>${escapeHtml(displayValue(state.plan?.status))}</span>
            <button type="button" data-generate-config-plan ${actionAttrs("config-plan")}>${actionText("config-plan", "Generate", "Generating...")}</button>
          </div>
        </div>
        <p class="muted-copy">${escapeHtml(displayValue(state.plan?.summary))}</p>
        <div class="steps vertical">
          ${planItems.length ? planItems.map(renderStep).join("") : `<p class="muted-copy">${MISSING_VALUE}</p>`}
        </div>
        <button class="full-button" type="button" data-execute-plan ${actionAttrs("execute-plan")}>${actionText("execute-plan", "执行配置计划", "执行中...")}</button>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3>Execution Result</h3>
          <span>${escapeHtml(displayValue(state.executionResult?.status))}</span>
        </div>
        <p class="muted-copy">${escapeHtml(displayValue(state.executionResult?.message))}</p>
        <div class="key-value-list">
          <span>Queued Tasks</span><strong>${escapeHtml(displayValue(executionTasks.length))}</strong>
          <span>Safety Items</span><strong>${escapeHtml(displayValue(safetyReport.length))}</strong>
        </div>
        <div class="report-preview compact">
          <pre>${escapeHtml(renderJsonBlock(state.executionResult || state.actionPlan?.tasks || null))}</pre>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3>Git AI</h3>
          <button type="button" data-analyze-git ${actionAttrs("analyze-git")}>${actionText("analyze-git", "Analyze Git", "Analyzing...")}</button>
        </div>
        <div class="report-preview compact">
          <pre>${escapeHtml(renderJsonBlock(state.gitAnalysis))}</pre>
        </div>
      </section>

      <section class="panel report-panel">
        <div class="panel-header">
          <h3>AI Report</h3>
          <button type="button" data-generate-report ${actionAttrs("generate-report")}>${actionText("generate-report", "生成 Markdown 报告", "生成中...")}</button>
        </div>
        <div class="report-preview markdown-render">
          ${renderMarkdown(state.report)}
        </div>
      </section>
    </div>
  `;
}

function renderApiMap() {
  return `
    <section class="panel">
      <div class="panel-header">
        <h3>Frontend API Contract</h3>
        <span>来自 frontend-api-final (3).md</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th>Endpoint</th>
              <th>Status</th>
              <th>Use</th>
            </tr>
          </thead>
          <tbody>
            ${apiContract
              .map(
                ([method, endpoint, status, use]) => `
                  <tr>
                    <td><span class="method">${method}</span></td>
                    <td><code>${escapeHtml(endpoint)}</code></td>
                    <td><span class="badge ${status === "已接入" ? "healthy" : "warning"}">${status}</span></td>
                    <td>${escapeHtml(use)}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderSettings() {
  const localData = readLocalDemoData();
  const mode = backendModeMeta();
  return `
    <div class="two-column">
      <section class="panel">
        <div class="panel-header">
          <h3>Backend Connection</h3>
          <span>${escapeHtml(state.backendMode)}</span>
        </div>
        <form class="stack-form" data-settings-form data-draft-form="settings">
          <label>
            <span>API Base URL</span>
            <input name="apiBase" type="url" value="${escapeHtml(state.drafts.settings.apiBase)}" autocomplete="off" />
          </label>
          <button type="submit" ${actionAttrs("save-settings")}>${actionText("save-settings", "保存并重新连接", "连接中...")}</button>
        </form>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h3>Data Source</h3>
          <span>${escapeHtml(mode.label)}</span>
        </div>
        <div class="key-value-list">
          <span>Source</span><strong>${escapeHtml(mode.summary)}</strong>
          <span>Projects</span><strong>${escapeHtml(localData.projects.length)}</strong>
          <span>Servers</span><strong>${escapeHtml(localData.servers.length)}</strong>
          <span>Tasks</span><strong>${escapeHtml(localData.executorTasks.length)}</strong>
          <span>Last Issue</span><strong>${escapeHtml(displayValue(state.backendIssue))}</strong>
        </div>
        <button class="full-button" type="button" data-use-local-demo ${actionAttrs("use-local-demo")}>${actionText("use-local-demo", "Use Local Demo")}</button>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h3>Executor Boundary</h3>
          <span>headless</span>
        </div>
        <div class="key-value-list">
          <span>CLI</span><strong>projectpilot executor</strong>
          <span>GUI</span><strong>ProjectPilot Desktop</strong>
          <span>Worker</span><strong>No app command</strong>
        </div>
      </section>
      <section class="panel">
        <div class="panel-header">
          <h3>Session</h3>
          <span>${escapeHtml(state.user.name)}</span>
        </div>
        <p class="muted-copy">当前是本地登录态。后续接入后端认证后，这里会展示团队、角色和 Token 状态。</p>
        <button class="danger-button" type="button" data-logout>退出登录</button>
      </section>
    </div>
  `;
}

function bindLogin() {
  document.querySelector("[data-login-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") || "admin@projectpilot.local");
    const name = email.split("@")[0] || "Admin";
    state.user = {
      email,
      name,
      initials: name.slice(0, 2).toUpperCase()
    };
    saveSession(state.user);
    state.route = "dashboard";
    await loadData();
  });

  bindDraftInputs();
}

function bindShell() {
  bindDraftInputs();

  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => {
      state.route = button.dataset.route;
      render();
    });
  });

  document.querySelector("[data-refresh]")?.addEventListener("click", async () => {
    await runAction("refresh-data", "正在刷新后端数据", async () => {
      await loadData({ silent: true });
    });
  });

  document.querySelector("[data-use-local-demo]")?.addEventListener("click", async () => {
    await runAction("use-local-demo", "正在切换到 Local Demo", async () => {
      await activateLocalDemo("已切换到 Local Demo");
    });
  });

  document.querySelector("[data-retry-backend]")?.addEventListener("click", async () => {
    await runAction("retry-backend", "正在重新连接后端", async () => {
      state.localDemoActive = false;
      state.backendMode = "checking";
      state.backendIssue = "";
      await loadData({ silent: true });
    });
  });

  document.querySelector("[data-project-select]")?.addEventListener("change", async (event) => {
    state.selectedProjectId = Number(event.currentTarget.value);
    await loadData({ silent: true });
  });

  document.querySelectorAll("[data-select-project]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedProjectId = Number(button.dataset.selectProject);
      state.route = "dashboard";
      await loadData({ silent: true });
    });
  });

  bindFormSubmit("[data-project-form]", handleCreateProject);
  bindFormSubmit("[data-server-form]", handleCreateServer);
  bindFormSubmit("[data-binding-form]", handleBindServer);
  bindFormSubmit("[data-action-plan-form]", handlePlanAction);
  bindFormSubmit("[data-settings-form]", handleSettings);
  document.querySelector("[data-generate-report]")?.addEventListener("click", handleReport);
  document.querySelector("[data-detect-project]")?.addEventListener("click", handleDetectProject);
  document.querySelector("[data-generate-ai]")?.addEventListener("click", handleRefreshAi);
  document.querySelector("[data-generate-config-plan]")?.addEventListener("click", handleGenerateConfigPlan);
  document.querySelector("[data-analyze-git]")?.addEventListener("click", handleAnalyzeGit);
  document.querySelector("[data-execute-plan]")?.addEventListener("click", handleExecutePlan);
  document.querySelector("[data-refresh-tasks]")?.addEventListener("click", async () => {
    await runAction("refresh-tasks", "正在刷新 executor tasks", async () => {
      await loadData({ silent: true });
    });
  });

  document.querySelectorAll("[data-check-server]").forEach((button) => {
    button.addEventListener("click", () => handleCheckServer(Number(button.dataset.checkServer)));
  });

  document.querySelectorAll("[data-server-detail]").forEach((button) => {
    button.addEventListener("click", () => handleServerDetail(Number(button.dataset.serverDetail)));
  });

  document.querySelectorAll("[data-detect-server]").forEach((button) => {
    button.addEventListener("click", () => handleDetectServer(Number(button.dataset.detectServer)));
  });

  document.querySelectorAll("[data-unbind-server]").forEach((button) => {
    button.addEventListener("click", () => handleUnbindServer(Number(button.dataset.unbindServer)));
  });

  document.querySelectorAll("[data-task-detail]").forEach((button) => {
    button.addEventListener("click", () => handleTaskDetail(button.dataset.taskDetail));
  });

  document.querySelector("[data-logout]")?.addEventListener("click", () => {
    localStorage.removeItem(SESSION_KEY);
    state.user = null;
    render();
  });
}

function bindDraftInputs() {
  document.querySelectorAll("[data-draft-form]").forEach((form) => {
    const syncDraft = (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) {
        return;
      }

      const draftKey = form.dataset.draftForm;
      if (!draftKey || !state.drafts[draftKey] || !target.name) {
        return;
      }

      state.drafts[draftKey][target.name] =
        target instanceof HTMLInputElement && target.type === "checkbox" ? target.checked : target.value;
      if (draftKey === "settings" && target.name === "apiBase") {
        state.apiBase = target.value;
      }
    };

    form.addEventListener("input", syncDraft);
    form.addEventListener("change", syncDraft);
  });
}

function bindFormSubmit(selector, handler) {
  const form = document.querySelector(selector);
  if (!form) return;

  const runHandler = (eventLike) => {
    Promise.resolve(handler(eventLike)).catch((error) => {
      setToast(error?.message || "表单提交失败");
    });
  };

  form.addEventListener("submit", runHandler);
  form.querySelector('button[type="submit"]')?.addEventListener("click", (event) => {
    event.preventDefault();
    runHandler({
      currentTarget: form,
      preventDefault() {}
    });
  });
}

async function handleCreateProject(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = {
    name: String(form.get("name") || "").trim(),
    path: String(form.get("path") || "").trim(),
    description: String(form.get("description") || "").trim()
  };
  if (!body.name || !body.path) {
    setToast("项目名称和路径不能为空");
    return;
  }
  await runAction("create-project", "正在创建项目", async () => {
    const created = await request(
      "/projects",
      { method: "POST", body },
      null
    );
    if (!created) {
      setToast("后端未返回创建结果");
      return;
    }
    state.projects = [created, ...state.projects];
    state.selectedProjectId = created.id;
    state.drafts.project = {
      name: "",
      path: "",
      description: ""
    };
    setToast("项目已创建");
    await loadData({ silent: true });
  });
}

async function activateLocalDemo(message = "Local Demo 已启用") {
  state.localDemoActive = true;
  state.backendMode = "local";
  state.backendIssue = "Using browser localStorage as the demo backend.";
  setToast(message);
  await loadData({ silent: true });
}

async function handleCreateServer(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = {
    name: String(form.get("name") || "").trim(),
    host: String(form.get("host") || "").trim(),
    port: Number(form.get("port")),
    username: String(form.get("username") || "").trim(),
    connection_mode: String(form.get("connection_mode") || "executor"),
    description: String(form.get("description") || "").trim()
  };
  if (!body.name || !body.host || !body.username || !Number.isInteger(body.port) || body.port < 1 || body.port > 65535) {
    setToast("服务器名称、Host、Port、Username 不能为空");
    return;
  }
  await runAction("create-server", "正在创建服务器", async () => {
    const created = await request(
      "/servers",
      { method: "POST", body },
      null
    );
    if (!created) {
      setToast("后端未返回创建结果");
      return;
    }
    state.servers = [created, ...state.servers];
    state.drafts.server = {
      name: "",
      host: "",
      port: "",
      username: "",
      connection_mode: "executor",
      description: ""
    };
    setToast("服务器已创建");
    await loadData({ silent: true });
  });
}

async function handleBindServer(event) {
  event.preventDefault();
  const projectId = projectIdForActions();
  const form = new FormData(event.currentTarget);
  const serverId = Number(form.get("server_id"));
  const body = {
    server_id: serverId,
    project_path: String(form.get("project_path") || "").trim()
  };

  if (!projectId) {
    setToast("后端未返回项目，无法绑定服务器");
    return;
  }
  if (!Number.isInteger(serverId) || serverId <= 0 || !body.project_path) {
    setToast("服务器和项目路径不能为空");
    return;
  }
  const duplicateBinding = (state.bindings || []).find(
    (binding) =>
      Number(binding.server_id) === serverId &&
      String(binding.project_path || "").trim() === body.project_path
  );
  if (duplicateBinding) {
    setToast("该服务器和项目路径已经绑定");
    return;
  }
  const sameServerBinding = (state.bindings || []).find((binding) => Number(binding.server_id) === serverId);
  if (
    sameServerBinding &&
    !confirmAction("该服务器已绑定到当前项目。确认继续为同一服务器新增另一个项目路径绑定？")
  ) {
    return;
  }

  await runAction("bind-server", "正在绑定服务器", async () => {
    const created = await request(
      `/projects/${projectId}/bind-server`,
      { method: "POST", body },
      null
    );
    if (!created) {
      setToast("后端未返回绑定结果");
      return;
    }

    state.drafts.binding = {
      server_id: "",
      project_path: ""
    };
    setToast("服务器绑定已创建");
    await loadData({ silent: true });
  });
}

async function handleUnbindServer(serverId) {
  const projectId = projectIdForActions();
  if (!projectId || !serverId) {
    setToast("后端未返回项目或服务器，无法解绑");
    return;
  }

  const server = state.servers.find((item) => Number(item.id) === Number(serverId));
  if (!confirmAction(`确认解除 ${displayValue(server?.name || `Server ${serverId}`)} 与当前项目的绑定？`)) {
    return;
  }

  await runAction(`unbind-server-${serverId}`, "正在解除服务器绑定", async () => {
    const result = await request(
      `/projects/${projectId}/servers/${serverId}`,
      { method: "DELETE" },
      null
    );
    if (!result) {
      setToast("后端未返回解绑结果");
      return;
    }

    state.bindings = state.bindings.filter((binding) => Number(binding.server_id) !== Number(serverId));
    setToast(result.message || "服务器绑定已解除");
    await loadData({ silent: true });
  });
}

async function handleDetectServer(serverId) {
  const projectId = projectIdForActions();
  if (!projectId || !serverId) {
    setToast("后端未返回项目或服务器，无法检测");
    return;
  }

  const server = state.servers.find((item) => Number(item.id) === Number(serverId));
  if (!confirmAction(`确认为 ${displayValue(server?.name || `Server ${serverId}`)} 创建 Git 和环境检测任务？`)) {
    return;
  }

  await runAction(`detect-server-${serverId}`, "正在创建检测任务", async () => {
    const result = await request(
      `/projects/${projectId}/servers/${serverId}/detect`,
      { method: "POST" },
      null
    );
    if (!result) {
      setToast("后端未返回检测结果");
      return;
    }

    setToast(result.message || `检测状态：${displayValue(result.status)}`);
    await loadData({ silent: true });
  });
}

async function handleSettings(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const nextApiBase = normalizeApiBase(form.get("apiBase"));
  if (!nextApiBase) {
    setToast("API Base URL 不能为空");
    return;
  }

  await runAction("save-settings", "正在保存并连接后端", async () => {
    state.apiBase = nextApiBase;
    localStorage.setItem(API_BASE_KEY, state.apiBase);
    localStorage.setItem(API_BASE_VERSION_KEY, API_BASE_VERSION);
    state.drafts.settings.apiBase = state.apiBase;
    state.localDemoActive = false;
    state.backendMode = "checking";
    state.backendIssue = "";
    setToast("后端地址已保存");
    await loadData({ silent: true });
  });
}

async function handleReport() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法生成报告");
    return;
  }
  await runAction("generate-report", "正在生成报告", async () => {
    const report = await request(
      "/reports/project",
      {
        method: "POST",
        body: {
          project_id: projectId,
          include_ai_analysis: true
        }
      },
      null
    );
    if (!report?.content) {
      setToast("后端未返回报告内容");
      return;
    }
    state.report = report.content;
    state.route = "reports";
    setToast("报告已生成");
    render();
  });
}

async function handleDetectProject() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法检测");
    return;
  }
  const targets = (state.bindings || []).filter((binding) => binding.server_id);
  if (!targets.length) {
    setToast("后端未返回可检测的服务器");
    return;
  }

  if (!confirmAction(`确认给当前项目的 ${targets.length} 台绑定服务器创建检测任务？`)) {
    return;
  }

  await runAction("detect-project", "正在创建项目检测任务", async () => {
    const results = await Promise.all(
      targets.map((binding) =>
        request(`/projects/${projectId}/servers/${binding.server_id}/detect`, { method: "POST" }, null)
      )
    );
    const returned = results.filter(Boolean);
    if (!returned.length) {
      setToast("后端未返回检测结果");
      return;
    }

    const queued = returned.filter((item) => item.status === "queued").length;
    const completed = returned.filter((item) => item.status === "completed").length;
    setToast(`检测触发完成：${completed} completed，${queued} queued`);
    await loadData({ silent: true });
  });
}

async function handleRefreshAi() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法刷新 AI");
    return;
  }
  await runAction("refresh-ai", "正在刷新 AI 分析", async () => {
    state.analysis = await request(
      `/projects/${projectId}/ai/analyze-env`,
      {
        method: "POST",
        body: {
          question: "请重新分析当前项目风险",
          focus: "environment"
        }
      },
      null
    );
    if (!state.analysis) {
      setToast("后端未返回 AI 分析");
      return;
    }
    setToast("AI 分析已刷新");
    render();
  });
}

async function handleGenerateConfigPlan() {
  const projectId = projectIdForActions();
  const targetServerId = Number(state.drafts.actionPlan.target_server_id);
  const sourceServerId = Number(state.drafts.actionPlan.source_server_id);
  const goal = String(state.drafts.actionPlan.goal || "").trim();

  if (!projectId) {
    setToast("后端未返回项目，无法生成配置计划");
    return;
  }
  if (!goal || !Number.isInteger(targetServerId) || targetServerId <= 0) {
    setToast("请先填写目标并选择目标服务器");
    return;
  }

  const body = {
    target_server_id: targetServerId,
    goal,
    allow_command_generation: Boolean(state.drafts.actionPlan.allow_command_generation)
  };
  if (Number.isInteger(sourceServerId) && sourceServerId > 0) {
    body.source_server_id = sourceServerId;
  }

  await runAction("config-plan", "正在生成配置计划", async () => {
    const result = await request(
      `/projects/${projectId}/ai/config-plan`,
      { method: "POST", body },
      null
    );
    if (!result) {
      setToast("后端未返回配置计划");
      return;
    }

    state.plan = result;
    state.actionPlan = null;
    setToast(`配置计划状态：${displayValue(result.status)}`);
    render();
  });
}

async function handleAnalyzeGit() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法分析 Git");
    return;
  }

  await runAction("analyze-git", "正在分析 Git", async () => {
    const result = await request(
      `/projects/${projectId}/ai/analyze-git`,
      {
        method: "POST",
        body: {
          analyses: ["status", "doctor", "map", "sync_plan", "commit_plan"]
        }
      },
      null
    );
    if (!result) {
      setToast("后端未返回 Git AI 分析");
      return;
    }

    state.gitAnalysis = result;
    state.route = "reports";
    setToast("Git AI 分析已返回");
    render();
  });
}

async function handlePlanAction(event) {
  event.preventDefault();
  const projectId = projectIdForActions();
  const form = new FormData(event.currentTarget);
  const targetServerRaw = String(form.get("target_server_id") || "");
  const sourceServerRaw = String(form.get("source_server_id") || "");
  const targetServerId = Number(targetServerRaw);
  const sourceServerId = Number(sourceServerRaw);
  const body = {
    goal: String(form.get("goal") || "").trim(),
    target_server_id: targetServerId,
    allow_command_generation: form.get("allow_command_generation") === "on",
    auto_execute: form.get("auto_execute") === "on",
    confirmed: form.get("confirmed") === "on"
  };

  if (sourceServerRaw && Number.isInteger(sourceServerId) && sourceServerId > 0) {
    body.source_server_id = sourceServerId;
  }

  if (!projectId) {
    setToast("后端未返回项目，无法生成主动计划");
    return;
  }
  if (!body.goal || !Number.isInteger(targetServerId) || targetServerId <= 0) {
    setToast("目标和目标服务器不能为空");
    return;
  }
  if (body.auto_execute && !body.confirmed) {
    setToast("直接进入 executor 队列前必须人工确认");
    return;
  }
  if (body.auto_execute && !confirmAction("确认将主动计划直接转入 executor 队列？")) {
    return;
  }

  await runAction("plan-action", "正在生成主动计划", async () => {
    const result = await request(
      `/projects/${projectId}/ai/plan-action`,
      { method: "POST", body },
      null
    );
    if (!result) {
      setToast("后端未返回主动计划");
      return;
    }

    state.actionPlan = result;
    if (result.plan) {
      state.plan = {
        ...result.plan,
        goal: result.goal || body.goal,
        status: result.plan.status || result.status,
        target_server_id: result.target_server?.id || body.target_server_id,
        target_server_name: result.target_server?.name,
        source_server_id: body.source_server_id
      };
    }
    if (Array.isArray(result.tasks)) {
      state.executionResult = result;
    }
    setToast(result.message || `主动计划状态：${displayValue(result.status)}`);
    render();
  });
}

async function handleCheckServer(serverId) {
  await runAction(`check-server-${serverId}`, "正在检查服务器连接", async () => {
    const result = await request(
      `/servers/${serverId}/check-connection`,
      { method: "POST" },
      null
    );
    if (!result) {
      setToast("后端未返回连接检查结果");
      return;
    }
    state.servers = state.servers.map((server) =>
      server.id === serverId
        ? { ...server, connection_status: result.connected ? "online" : "warning" }
        : server
    );
    setToast(result.message || "连接检查完成");
  });
}

async function handleServerDetail(serverId) {
  if (!serverId) {
    setToast("后端未返回 server id，无法读取服务器详情");
    return;
  }

  await runAction(`server-detail-${serverId}`, "正在读取服务器详情", async () => {
    const detail = await request(
      `/servers/${serverId}/status`,
      {},
      null
    );
    if (!detail) {
      setToast("后端未返回服务器详情");
      return;
    }

    state.selectedServerId = serverId;
    state.serverDetail = detail;
    state.route = "serverDetail";
    setToast("服务器详情已返回");
    render();
  });
}

async function handleTaskDetail(taskId) {
  if (!taskId) {
    setToast("后端未返回 task id，无法读取详情");
    return;
  }

  await runAction(`task-detail-${taskId}`, "正在读取 Task 详情", async () => {
    const detail = await request(
      `/executor/tasks/${encodeURIComponent(taskId)}`,
      {},
      null
    );
    if (!detail) {
      setToast("后端未返回 task 详情");
      return;
    }

    state.executorTaskDetail = detail;
    state.route = "tasks";
    setToast("Task 详情已返回");
    render();
  });
}

async function handleExecutePlan() {
  const targetServerId = planTargetServerId();
  if (!targetServerId) {
    setToast("没有可执行的目标服务器");
    return;
  }
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法执行");
    return;
  }
  const steps = planSteps(state.plan);
  if (!steps.length) {
    setToast("后端未返回配置步骤，无法执行");
    return;
  }

  const target = state.servers.find((server) => Number(server.id) === Number(targetServerId));
  if (!confirmAction(`确认执行 ${steps.length} 个配置步骤到 ${displayValue(target?.name || `Server ${targetServerId}`)}？`)) {
    return;
  }

  await runAction("execute-plan", "正在执行配置计划", async () => {
    const result = await request(
      `/projects/${projectId}/servers/${targetServerId}/execute-config-plan`,
      {
        method: "POST",
        body: {
          confirmed: true,
          steps
        }
      },
      null
    );
    if (!result) {
      setToast("后端未返回执行结果");
      return;
    }
    state.executionResult = result;
    setToast(result.message || `执行状态：${displayValue(result.status)}`);
    render();
  });
}

render();
if (state.user) {
  loadData();
}
