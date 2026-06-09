import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(join(dirname(fileURLToPath(import.meta.url)), ".."));
const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
const skipBuild = args.has("--skip-build");
const skipNotarize = args.has("--skip-notarize") || process.env.PROJECTPILOT_SKIP_NOTARIZE === "1";
const createUpdaterArtifacts =
  args.has("--updater-artifacts") || process.env.PROJECTPILOT_CREATE_UPDATER_ARTIFACTS === "1";
const signingIdentity =
  process.env.PROJECTPILOT_MACOS_SIGNING_IDENTITY ||
  process.env.APPLE_SIGNING_IDENTITY ||
  "-";

function run(command, commandArgs, options = {}) {
  if (dryRun) {
    console.log(`[dry-run] ${command} ${commandArgs.join(" ")}`);
    return;
  }

  const result = spawnSync(command, commandArgs, {
    cwd: options.cwd || root,
    stdio: "inherit",
    shell: false,
    env: {
      ...process.env
    }
  });

  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

function walk(dir, matcher, found = []) {
  if (!existsSync(dir)) return found;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (matcher(path)) {
        found.push(path);
      } else {
        walk(path, matcher, found);
      }
    }
  }
  return found;
}

function findAppBundle() {
  const bundleRoot = join(root, "src-tauri", "target", "release", "bundle");
  const candidates = walk(bundleRoot, (path) => path.endsWith(".app"));
  return candidates.find((path) => basename(path) === "ProjectPilot.app") || candidates[0] || null;
}

function notaryConfig() {
  return {
    appleId: process.env.PROJECTPILOT_NOTARY_APPLE_ID,
    teamId: process.env.PROJECTPILOT_NOTARY_TEAM_ID,
    password: process.env.PROJECTPILOT_NOTARY_PASSWORD
  };
}

function canNotarize(config) {
  return Boolean(config.appleId && config.teamId && config.password && signingIdentity !== "-");
}

console.log("ProjectPilot macOS release");
console.log(`signing identity: ${signingIdentity === "-" ? "ad-hoc (-)" : signingIdentity}`);
console.log(`notarization: ${skipNotarize ? "skipped by flag" : canNotarize(notaryConfig()) ? "enabled" : "waiting for credentials"}`);
console.log(`updater artifacts: ${createUpdaterArtifacts ? "enabled" : "disabled"}`);

if (!skipBuild) {
  const buildArgs = ["run", "tauri:build"];
  if (createUpdaterArtifacts) {
    const releaseDir = join(root, "dist", "release");
    const updaterConfig = join(releaseDir, "tauri-updater-build.json");
    if (!dryRun) {
      mkdirSync(releaseDir, { recursive: true });
      writeFileSync(updaterConfig, `${JSON.stringify({ bundle: { createUpdaterArtifacts: true } }, null, 2)}\n`, "utf-8");
    }
    buildArgs.push("--", "--config", updaterConfig);
  }
  run("npm", buildArgs);
}

if (dryRun) {
  console.log("Dry run complete.");
  process.exit(0);
}

const appBundle = findAppBundle();
if (!appBundle) {
  console.error("ProjectPilot.app was not found under src-tauri/target/release/bundle.");
  console.error("Run npm run tauri:build first, or rerun without --skip-build.");
  process.exit(1);
}

const signArgs = ["--force", "--deep", "--sign", signingIdentity];
if (signingIdentity !== "-") {
  signArgs.push("--options", "runtime", "--timestamp");
}
signArgs.push(appBundle);
run("codesign", signArgs);
run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appBundle]);

const config = notaryConfig();
if (!skipNotarize && canNotarize(config)) {
  const releaseDir = join(root, "dist", "release");
  mkdirSync(releaseDir, { recursive: true });
  const zipPath = join(releaseDir, "ProjectPilot-notary.zip");
  run("ditto", ["-c", "-k", "--keepParent", appBundle, zipPath]);
  run("xcrun", [
    "notarytool",
    "submit",
    zipPath,
    "--wait",
    "--apple-id",
    config.appleId,
    "--team-id",
    config.teamId,
    "--password",
    config.password
  ]);
  run("xcrun", ["stapler", "staple", appBundle]);
} else {
  console.log("Notarization skipped. Set PROJECTPILOT_NOTARY_APPLE_ID, PROJECTPILOT_NOTARY_TEAM_ID, and PROJECTPILOT_NOTARY_PASSWORD to enable it.");
}

console.log(`Release app verified: ${appBundle}`);
