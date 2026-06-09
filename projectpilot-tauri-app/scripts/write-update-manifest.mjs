import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(join(dirname(fileURLToPath(import.meta.url)), ".."));

function argValue(name) {
  const index = process.argv.indexOf(name);
  if (index === -1) return null;
  return process.argv[index + 1] || null;
}

function currentPlatform() {
  if (process.platform === "darwin" && process.arch === "arm64") return "darwin-aarch64";
  if (process.platform === "darwin") return "darwin-x86_64";
  if (process.platform === "win32" && process.arch === "arm64") return "windows-aarch64";
  if (process.platform === "win32") return "windows-x86_64";
  if (process.arch === "arm64") return "linux-aarch64";
  return "linux-x86_64";
}

const packageJson = JSON.parse(readFileSync(join(root, "package.json"), "utf-8"));
const version = argValue("--version") || process.env.PROJECTPILOT_UPDATE_VERSION || packageJson.version;
const platform = argValue("--platform") || process.env.PROJECTPILOT_UPDATE_PLATFORM || currentPlatform();
const url = argValue("--url") || process.env.PROJECTPILOT_UPDATE_URL;
const signature =
  argValue("--signature") ||
  process.env.PROJECTPILOT_UPDATE_SIGNATURE ||
  (argValue("--signature-file") ? readFileSync(resolve(argValue("--signature-file")), "utf-8").trim() : null);
const notes = argValue("--notes") || process.env.PROJECTPILOT_UPDATE_NOTES || "ProjectPilot desktop update.";
const output = resolve(argValue("--out") || process.env.PROJECTPILOT_UPDATE_MANIFEST || join(root, "dist", "update-manifest.json"));

if (!url || !signature) {
  console.error("Update manifest requires --url and --signature, or PROJECTPILOT_UPDATE_URL and PROJECTPILOT_UPDATE_SIGNATURE.");
  console.error("Generate a Tauri updater signing key with: npx tauri signer generate --write-keys updater.key");
  console.error("Sign the release artifact with: npx tauri signer sign --private-key-path updater.key <artifact>");
  process.exit(1);
}

const manifest = {
  version,
  notes,
  pub_date: new Date().toISOString(),
  platforms: {
    [platform]: {
      signature,
      url
    }
  }
};

mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");
console.log(`Wrote update manifest: ${output}`);
