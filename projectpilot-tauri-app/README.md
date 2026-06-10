# ProjectPilot Desktop App

This directory contains the human-facing ProjectPilot desktop prototype. It is not the executor. The executor remains a headless worker under `projectpilot executor ...`.

## Structure

- `src/` contains the browser UI.
- `src-tauri/` contains the Tauri desktop shell.
- `backend/` contains the local FastAPI backend used by this prototype.
- `scripts/` contains local development helpers.
- `vendor/` contains vendored build support used by the Windows desktop build.

Generated directories such as `node_modules/`, `dist/`, `dist-app/`, `.cargo/`, `.rustup/`, `.venv*`, and `src-tauri/target/` are ignored by Git.

## Run Web Preview

```bash
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Run Backend

```bash
python3 -m pip install -r backend/requirements.txt
npm run seed:backend
npm run dev:backend
```

`npm run seed:backend` rebuilds the local Git demo workspace at
`/Users/eddz/work/projectpilot-demo`. It creates multiple local repositories
with merge commits, feature branches, tags, diverged history, dirty files,
conflicts, detached HEAD, and wrong-branch states for Git Workspace demos.

The local backend runs at:

```text
http://127.0.0.1:8000
```

## Run Full Desktop App

```bash
npm install
npm run tauri:dev
```

The Tauri dev command starts the frontend and backend helpers declared in `src-tauri/tauri.conf.json`.

## Build

Build frontend assets:

```bash
npm run build
```

Build the Tauri app:

```bash
npm run tauri:build
```

## E2E Test

Run the browser E2E flow:

```bash
npm run test:e2e
```

The test starts the local web preview, drives headless Chrome through project creation, server creation, binding, detection, and executor task detail views, then writes a screenshot to `/tmp/projectpilot-e2e-tasks.png`.

## macOS Release

Local ad-hoc release validation:

```bash
npm run release:macos
```

Formal Developer ID signing and notarization require external Apple credentials:

```bash
export PROJECTPILOT_MACOS_SIGNING_IDENTITY="Developer ID Application: Your Team (TEAMID)"
export PROJECTPILOT_NOTARY_APPLE_ID="apple-id@example.com"
export PROJECTPILOT_NOTARY_TEAM_ID="TEAMID"
export PROJECTPILOT_NOTARY_PASSWORD="app-specific-password"
npm run release:macos
```

The release script builds the Tauri app, signs the `.app`, verifies the signature, submits to `notarytool` when the notarization variables are present, and staples the notarization ticket.

## Update Manifest

Generate a Tauri updater signing key outside Git:

```bash
npm run tauri:signer:generate -- --write-keys ~/.projectpilot/updater.key
```

Build updater artifacts when the updater signing private key is available:

```bash
export TAURI_SIGNING_PRIVATE_KEY_PATH="$HOME/.projectpilot/updater.key"
export PROJECTPILOT_CREATE_UPDATER_ARTIFACTS=1
npm run release:macos
```

Sign a release artifact with Tauri CLI when signing an externally hosted file, then write the static update manifest:

```bash
npx tauri signer sign --private-key-path ~/.projectpilot/updater.key path/to/ProjectPilot.tar.gz
npm run release:update-manifest -- --url https://updates.example.com/ProjectPilot.tar.gz --signature "<signature>"
```

The manifest is written to `dist/update-manifest.json` by default and is ready to host from a static update endpoint.
