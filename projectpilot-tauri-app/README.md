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
