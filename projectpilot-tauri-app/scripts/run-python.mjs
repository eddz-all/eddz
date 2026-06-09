import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(join(scriptDir, ".."));
const backendDir = join(root, "backend");
const localPythonCandidates = process.platform === "win32"
  ? [join(root, ".venv", "Scripts", "python.exe")]
  : [join(root, ".venv-macos", "bin", "python"), join(root, ".venv", "bin", "python")];
const localPython = localPythonCandidates.find((candidate) => existsSync(candidate));
const pythonExecutable = process.env.PYTHON || process.env.PYTHON_EXECUTABLE || localPython || "python3";
const args = process.argv.slice(2);

const child = spawn(pythonExecutable, args, {
  cwd: backendDir,
  shell: false,
  stdio: "inherit",
  env: {
    ...process.env
  }
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 0);
});

child.on("error", (error) => {
  console.error(`Failed to launch backend Python executable: ${pythonExecutable}`);
  console.error(error.message);
  process.exit(1);
});
