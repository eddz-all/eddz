import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const root = resolve(join(dirname(fileURLToPath(import.meta.url)), ".."));
const host = "127.0.0.1";
const screenshotPath = process.env.PROJECTPILOT_E2E_SCREENSHOT || "/tmp/projectpilot-e2e-tasks.png";
const chromePath = process.env.PROJECTPILOT_CHROME || findChrome();

if (!chromePath) {
  console.error("Chrome was not found. Set PROJECTPILOT_CHROME to a Chromium-compatible executable.");
  process.exit(1);
}

const frontendPort = await freePort();
const cdpPort = await freePort();
const userDataDir = mkdtempSync(join(tmpdir(), "projectpilot-e2e-chrome-"));
let serverProcess = null;
let chromeProcess = null;
let client = null;

try {
  serverProcess = spawn(process.execPath, ["scripts/dev-server.mjs"], {
    cwd: root,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      PORT: String(frontendPort)
    }
  });
  serverProcess.stdout.on("data", (chunk) => process.stdout.write(chunk));
  serverProcess.stderr.on("data", (chunk) => process.stderr.write(chunk));
  await waitForUrl(`http://${host}:${frontendPort}/`, 10000);

  chromeProcess = spawn(chromePath, [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${userDataDir}`,
    `http://${host}:${frontendPort}/`
  ], {
    shell: false,
    stdio: ["ignore", "ignore", "pipe"]
  });
  chromeProcess.stderr.on("data", (chunk) => process.stderr.write(chunk));
  await waitForUrl(`http://${host}:${cdpPort}/json/version`, 10000);

  client = await connectCdp(cdpPort);
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  await client.send("Page.navigate", { url: `http://${host}:${frontendPort}/` });
  await waitForPageLoad(client);
  await setE2eStorage(client);
  await client.send("Page.reload", { ignoreCache: true });
  await waitForPageLoad(client);

  const result = await runScenario(client);
  const screenshot = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  mkdirSync(dirname(screenshotPath), { recursive: true });
  writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));

  console.log(JSON.stringify({ success: true, screenshot: screenshotPath, result }, null, 2));
} finally {
  if (client) client.close();
  await stopProcess(chromeProcess);
  await stopProcess(serverProcess);
  await removeWithRetry(userDataDir);
}

function findChrome() {
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function freePort() {
  return new Promise((resolvePort, rejectPort) => {
    const server = createServer();
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close(() => {
        if (port) resolvePort(port);
        else rejectPort(new Error("Failed to allocate a port."));
      });
    });
    server.on("error", rejectPort);
  });
}

async function waitForUrl(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch (error) {
      lastError = error;
    }
    await sleep(150);
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError?.message || "no response"}`);
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null || child.signalCode) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolveExit) => child.once("exit", resolveExit)),
    sleep(2000)
  ]);
  if (child.exitCode === null && !child.signalCode) {
    child.kill("SIGKILL");
    await Promise.race([
      new Promise((resolveExit) => child.once("exit", resolveExit)),
      sleep(1000)
    ]);
  }
}

async function removeWithRetry(path) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      rmSync(path, { recursive: true, force: true });
      return;
    } catch (error) {
      if (attempt === 7) {
        console.warn(`Could not remove temporary directory ${path}: ${error.message}`);
        return;
      }
      await sleep(250);
    }
  }
}

async function connectCdp(port) {
  const targets = await fetch(`http://${host}:${port}/json/list`).then((response) => response.json());
  const target = targets.find((item) => item.type === "page") || targets[0];
  if (!target?.webSocketDebuggerUrl) {
    throw new Error("Chrome did not expose a page target.");
  }

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  const pending = new Map();
  const errors = [];
  let nextId = 1;
  await new Promise((resolveOpen, rejectOpen) => {
    ws.addEventListener("open", resolveOpen, { once: true });
    ws.addEventListener("error", rejectOpen, { once: true });
  });

  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") {
      errors.push(message.params?.exceptionDetails?.text || "Runtime exception");
    }
    if (message.id && pending.has(message.id)) {
      const { resolveMessage, rejectMessage } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) rejectMessage(new Error(message.error.message));
      else resolveMessage(message.result || {});
    }
  });

  return {
    errors,
    send(method, params = {}) {
      const id = nextId++;
      ws.send(JSON.stringify({ id, method, params }));
      return new Promise((resolveMessage, rejectMessage) => {
        pending.set(id, { resolveMessage, rejectMessage });
      });
    },
    close() {
      ws.close();
    }
  };
}

async function waitForPageLoad(cdp) {
  await cdp.send("Runtime.evaluate", {
    expression: "new Promise((resolve) => document.readyState === 'complete' ? resolve(true) : window.addEventListener('load', () => resolve(true), { once: true }))",
    awaitPromise: true
  });
}

async function setE2eStorage(cdp) {
  await cdp.send("Runtime.evaluate", {
    expression: `
      localStorage.setItem("projectpilot.session", JSON.stringify({ email: "e2e@projectpilot.local", name: "E2E Operator" }));
      localStorage.setItem("projectpilot.apiBase", "http://127.0.0.1:9");
      localStorage.setItem("projectpilot.apiBaseVersion", "20260610-cloudflare-functioning-element");
      localStorage.removeItem("projectpilot.localDemo.v1");
      true;
    `,
    returnByValue: true
  });
}

async function runScenario(cdp) {
  const expression = `
    (async () => {
      const suffix = Date.now();
      const projectName = "E2E Project " + suffix;
      const serverName = "E2E Local " + suffix;
      const projectPath = "/tmp/projectpilot-e2e-" + suffix;
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      window.confirm = () => true;
      const waitFor = async (predicate, label, timeout = 8000) => {
        const deadline = Date.now() + timeout;
        while (Date.now() < deadline) {
          if (predicate()) return true;
          await sleep(100);
        }
        throw new Error("Timed out waiting for " + label);
      };
      const click = async (selector) => {
        await waitFor(() => document.querySelector(selector), selector);
        document.querySelector(selector).click();
        await sleep(100);
      };
      const setValue = async (selector, value) => {
        await waitFor(() => document.querySelector(selector), selector);
        const input = document.querySelector(selector);
        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      };
      const selectByText = async (selector, text) => {
        await waitFor(() => document.querySelector(selector), selector);
        const select = document.querySelector(selector);
        const option = Array.from(select.options).find((item) => item.textContent.includes(text));
        if (!option) throw new Error("Missing select option: " + text);
        select.value = option.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      };
      const visibleText = () => document.body.innerText;

      await waitFor(() => document.querySelector('button[data-route="projects"]'), "shell");

      await click('button[data-route="projects"]');
      await setValue('[data-project-form] input[name="name"]', projectName);
      await setValue('[data-project-form] input[name="path"]', projectPath);
      await setValue('[data-project-form] textarea[name="description"]', "Created by E2E");
      await click('[data-project-form] button[type="submit"]');
      await waitFor(() => visibleText().includes(projectName), "created project");

      await click('button[data-route="servers"]');
      await setValue('[data-server-form] input[name="name"]', serverName);
      await setValue('[data-server-form] input[name="host"]', "127.0.0.1");
      await setValue('[data-server-form] input[name="port"]', "22");
      await setValue('[data-server-form] input[name="username"]', "eddz");
      await setValue('[data-server-form] textarea[name="description"]', "E2E local target");
      await selectByText('[data-server-form] select[name="connection_mode"]', "local");
      await click('[data-server-form] button[type="submit"]');
      await waitFor(() => visibleText().includes(serverName), "created server");

      await click('button[data-route="bindings"]');
      await selectByText('[data-binding-form] select[name="server_id"]', serverName);
      await setValue('[data-binding-form] input[name="project_path"]', projectPath);
      await click('[data-binding-form] button[type="submit"]');
      await waitFor(() => visibleText().includes(projectPath), "created binding");

      await click('button[data-detect-server]');
      await sleep(500);
      await click('button[data-route="tasks"]');
      await waitFor(() => document.querySelectorAll('[data-task-detail]').length >= 2, "task rows");
      await click('[data-task-detail]');
      await waitFor(() => visibleText().includes("GET /executor/tasks/{task_id}"), "task detail");
      const taskRows = document.querySelectorAll('[data-task-detail]').length;

      await click('button[data-route="git"]');
      await waitFor(() => visibleText().includes("Managed Repositories"), "git workspace");
      await waitFor(() => visibleText().includes("Git Problem Solver"), "git problem solver");
      await waitFor(() => visibleText().includes("10 Common Git Issues"), "git issue playbook");
      await waitFor(() => visibleText().includes("Push rejected risk"), "push rejected playbook item");
      await waitFor(() => visibleText().includes(projectPath), "git workspace project path");
      await click('[data-analyze-git]');
      await waitFor(() => visibleText().includes("smart-git.v1"), "smart git analysis");
      await waitFor(() => visibleText().includes("Operation Plans"), "git operation plans");

      const gitRows = document.querySelectorAll('.git-table tbody tr').length;
      const gitOperations = document.querySelectorAll('.git-operation').length;
      const gitIssueCards = document.querySelectorAll('.git-issue-card').length;
      const failedBadges = Array.from(document.querySelectorAll(".badge")).filter((item) => /failed|error|blocked/i.test(item.textContent)).length;
      if (taskRows < 2) throw new Error("Expected at least two task rows.");
      if (gitRows < 1) throw new Error("Expected at least one Git workspace row.");
      if (gitOperations < 1) throw new Error("Expected at least one Git operation plan.");
      if (gitIssueCards < 10) throw new Error("Expected Git issue playbook cards.");

      return { projectName, serverName, projectPath, taskRows, gitRows, gitOperations, gitIssueCards, failedBadges };
    })()
  `;

  const response = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true
  });

  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || "E2E scenario failed");
  }
  if (cdp.errors.length) {
    throw new Error(`Runtime errors during E2E: ${cdp.errors.join("; ")}`);
  }
  return response.result?.value;
}
