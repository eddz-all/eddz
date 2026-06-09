import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(".");
const backendDir = join(root, "backend");
const pythonLauncher = join(root, "scripts", "run-python.mjs");

function run(name, command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd || root,
    shell: true,
    stdio: "inherit",
    env: {
      ...process.env,
      ...options.env
    }
  });

  child.on("exit", (code) => {
    if (code && code !== 0) {
      console.error(`${name} exited with code ${code}`);
    }
  });

  return child;
}

const children = [];

if (existsSync(backendDir)) {
  children.push(
    run("backend", process.execPath, [pythonLauncher, "-m", "uvicorn", "main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"], {
      cwd: backendDir
    })
  );
}

children.push(run("frontend", "node", ["scripts/dev-server.mjs"]));

function shutdown() {
  for (const child of children) {
    child.kill();
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
