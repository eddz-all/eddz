import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve, join, delimiter } from "node:path";

const root = resolve(".");
const userHome = process.env.USERPROFILE || process.env.HOME || root;
const globalCargoHome = join(userHome, ".cargo");
const globalRustupHome = join(userHome, ".rustup");
const localCargoHome = join(root, ".cargo");
const localRustupHome = join(root, ".rustup");
const cargoHome = existsSync(join(globalCargoHome, "registry")) ? globalCargoHome : localCargoHome;
const rustupHome = existsSync(globalRustupHome) ? globalRustupHome : localRustupHome;
const cargoBin = join(cargoHome, "bin");
const args = process.argv.slice(2);

const command =
  process.platform === "win32" ? process.env.ComSpec || "cmd.exe" : "npx";
const commandArgs =
  process.platform === "win32"
    ? ["/d", "/s", "/c", ["npx", "tauri", ...args].join(" ")]
    : ["tauri", ...args];
const env = { ...process.env };
const pathKey = Object.keys(env).find((key) => key.toLowerCase() === "path") || "PATH";
env.CARGO_HOME = env.CARGO_HOME || cargoHome;
env.RUSTUP_HOME = env.RUSTUP_HOME || rustupHome;
env[pathKey] = `${cargoBin}${delimiter}${env[pathKey] || ""}`;

const child = spawn(command, commandArgs, {
  cwd: root,
  shell: false,
  stdio: "inherit",
  env
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 0);
});

child.on("error", (error) => {
  console.error("Failed to launch Tauri CLI.");
  console.error(error.message);
  process.exit(1);
});
