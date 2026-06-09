const API_BASE_KEY = "projectpilot.apiBase";
const API_BASE_VERSION_KEY = "projectpilot.apiBaseVersion";
const API_BASE_VERSION = "20260609-cloudflare-unique-painted";
const DEFAULT_API_BASE = "https://unique-painted-runner-last.trycloudflare.com";
const LOCAL_API_PROXY_BASE = "/api";
const SESSION_KEY = "projectpilot.session";
const MISSING_VALUE = "未返回";

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
  isLoading: false,
  toast: "",
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
      return result;
    }

    const response = await fetch(url, init);
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    state.backendMode = "connected";
    const text = await response.text();
    if (!text) {
      return { ok: true };
    }
    try {
      return JSON.parse(text);
    } catch {
      return { content: text };
    }
  } catch (error) {
    if (!options.optional) {
      state.backendMode = "error";
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

  const projectsResponse = await request("/projects", {}, null);
  state.dataLoaded.projects = Array.isArray(projectsResponse);
  state.projects = state.dataLoaded.projects ? projectsResponse : [];

  const serversResponse = await request("/servers", {}, null);
  state.dataLoaded.servers = Array.isArray(serversResponse);
  state.servers = state.dataLoaded.servers ? serversResponse : [];

  if (!state.selectedProjectId && state.projects[0]) {
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
  const statusResponse = projectId ? await request(`/projects/${projectId}/status`, {}, null) : null;
  state.dataLoaded.status = Boolean(statusResponse);
  state.status = statusResponse || { project: project || null, servers: [] };
  const bindingsResponse = projectId ? await request(`/projects/${projectId}/servers`, {}, null) : null;
  state.dataLoaded.bindings = Array.isArray(bindingsResponse);
  state.bindings = state.dataLoaded.bindings ? bindingsResponse : [];
  state.executorTasks = normalizeTaskList(
    await request(projectId ? `/executor/tasks?project_id=${projectId}` : "/executor/tasks", { optional: true }, [])
  );
  state.aiSettings = await request("/ai/settings", { optional: true }, null);
  state.activities = await request("/operation-logs", {}, []);
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
          <small>Real Data</small>
        </div>
      </section>
      <form class="login-panel" data-login-form data-draft-form="login">
        <h2>登录管理台</h2>
        <p>使用本地登录入口进入，数据只来自后端接口。</p>
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

function renderTopbar() {
  const modeClass = state.backendMode === "connected" ? "online" : state.backendMode === "error" ? "error" : "checking";
  const modeText = state.backendMode === "connected" ? "Backend online" : state.backendMode === "error" ? "Backend error" : "Checking API";
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
        <span class="connection ${modeClass}">${modeText}</span>
        <button class="icon-button" type="button" data-refresh title="刷新数据">↻</button>
        <button class="user-pill" type="button" data-route="settings">
          <span>${escapeHtml(state.user.initials)}</span>
          ${escapeHtml(state.user.name)}
        </button>
      </div>
    </header>
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

    <div class="content-grid">
      <section class="panel wide">
        <div class="panel-header">
          <h3>Server Health Overview</h3>
          <button type="button" data-detect-project>Run Detection</button>
        </div>
        <div class="table-wrap">
          <table>
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
          <button type="button" data-generate-ai>Refresh AI</button>
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
        <div class="table-wrap">
          <table>
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
          <button type="submit">创建项目</button>
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
                            <button type="button" data-check-server="${server.id}">Check</button>
                            <button type="button" data-server-detail="${server.id}">Details</button>
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
          <button type="submit">创建服务器</button>
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
          <button type="button" data-detect-server="${escapeHtml(binding.server_id)}">Detect</button>
          <button class="danger-button" type="button" data-unbind-server="${escapeHtml(binding.server_id)}">Unbind</button>
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
          <button type="submit" ${!projectId ? "disabled" : ""}>绑定服务器</button>
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
      <td><button type="button" data-task-detail="${escapeHtml(task.id)}">Details</button></td>
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
          <button type="button" data-refresh-tasks>Refresh Tasks</button>
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
          <button type="submit">生成主动计划</button>
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
            <button type="button" data-generate-config-plan>Generate</button>
          </div>
        </div>
        <p class="muted-copy">${escapeHtml(displayValue(state.plan?.summary))}</p>
        <div class="steps vertical">
          ${planItems.length ? planItems.map(renderStep).join("") : `<p class="muted-copy">${MISSING_VALUE}</p>`}
        </div>
        <button class="full-button" type="button" data-execute-plan>执行配置计划</button>
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
          <button type="button" data-analyze-git>Analyze Git</button>
        </div>
        <div class="report-preview compact">
          <pre>${escapeHtml(renderJsonBlock(state.gitAnalysis))}</pre>
        </div>
      </section>

      <section class="panel report-panel">
        <div class="panel-header">
          <h3>AI Report</h3>
          <button type="button" data-generate-report>生成 Markdown 报告</button>
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
          <button type="submit">保存并重新连接</button>
        </form>
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
    setToast("正在刷新后端数据");
    await loadData({ silent: true });
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

  document.querySelector("[data-project-form]")?.addEventListener("submit", handleCreateProject);
  document.querySelector("[data-server-form]")?.addEventListener("submit", handleCreateServer);
  document.querySelector("[data-binding-form]")?.addEventListener("submit", handleBindServer);
  document.querySelector("[data-action-plan-form]")?.addEventListener("submit", handlePlanAction);
  document.querySelector("[data-settings-form]")?.addEventListener("submit", handleSettings);
  document.querySelector("[data-generate-report]")?.addEventListener("click", handleReport);
  document.querySelector("[data-detect-project]")?.addEventListener("click", handleDetectProject);
  document.querySelector("[data-generate-ai]")?.addEventListener("click", handleRefreshAi);
  document.querySelector("[data-generate-config-plan]")?.addEventListener("click", handleGenerateConfigPlan);
  document.querySelector("[data-analyze-git]")?.addEventListener("click", handleAnalyzeGit);
  document.querySelector("[data-execute-plan]")?.addEventListener("click", handleExecutePlan);
  document.querySelector("[data-refresh-tasks]")?.addEventListener("click", async () => {
    setToast("正在刷新 executor tasks");
    await loadData({ silent: true });
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
}

async function handleUnbindServer(serverId) {
  const projectId = projectIdForActions();
  if (!projectId || !serverId) {
    setToast("后端未返回项目或服务器，无法解绑");
    return;
  }

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
}

async function handleDetectServer(serverId) {
  const projectId = projectIdForActions();
  if (!projectId || !serverId) {
    setToast("后端未返回项目或服务器，无法检测");
    return;
  }

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
}

async function handleSettings(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.apiBase = normalizeApiBase(form.get("apiBase"));
  localStorage.setItem(API_BASE_KEY, state.apiBase);
  localStorage.setItem(API_BASE_VERSION_KEY, API_BASE_VERSION);
  state.drafts.settings.apiBase = state.apiBase;
  setToast("后端地址已保存");
  await loadData({ silent: true });
}

async function handleReport() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法生成报告");
    return;
  }
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
}

async function handleDetectProject() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法检测");
    return;
  }
  const bindings = await request(`/projects/${projectId}/servers`, {}, null);
  if (!Array.isArray(bindings)) {
    setToast("后端未返回绑定服务器列表");
    return;
  }

  const targets = bindings.filter((binding) => binding.server_id);
  if (!targets.length) {
    setToast("后端未返回可检测的服务器");
    return;
  }

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
}

async function handleRefreshAi() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法刷新 AI");
    return;
  }
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
}

async function handleAnalyzeGit() {
  const projectId = projectIdForActions();
  if (!projectId) {
    setToast("后端未返回项目，无法分析 Git");
    return;
  }

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
}

async function handleCheckServer(serverId) {
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
}

async function handleServerDetail(serverId) {
  if (!serverId) {
    setToast("后端未返回 server id，无法读取服务器详情");
    return;
  }

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
}

async function handleTaskDetail(taskId) {
  if (!taskId) {
    setToast("后端未返回 task id，无法读取详情");
    return;
  }

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
}

render();
if (state.user) {
  loadData();
}
