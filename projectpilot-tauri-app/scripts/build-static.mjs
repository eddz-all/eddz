import { copyFile, mkdir, rm } from "node:fs/promises";
import { existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const root = resolve(".");
const dist = join(root, "dist");

async function copyRecursive(from, to) {
  if (statSync(from).isDirectory()) {
    await mkdir(to, { recursive: true });
    for (const entry of readdirSync(from)) {
      await copyRecursive(join(from, entry), join(to, entry));
    }
    return;
  }

  await mkdir(dirname(to), { recursive: true });
  await copyFile(from, to);
}

if (existsSync(dist)) {
  await rm(dist, { recursive: true, force: true });
}

await mkdir(dist, { recursive: true });
await copyFile(join(root, "index.html"), join(dist, "index.html"));
await copyRecursive(join(root, "src"), join(dist, "src"));

console.log(`Static app built at ${dist}`);
