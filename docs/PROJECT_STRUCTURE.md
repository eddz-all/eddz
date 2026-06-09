# ProjectPilot Project Structure

This repository has three active code surfaces:

- `projectpilot/`: installable Python package and CLI.
- `projectpilot-tauri-app/`: human-facing desktop prototype.
- `tests/`: Python unit tests for the package and CLI behavior.

## Python Package

`projectpilot/cli.py` is the main CLI entrypoint.

The default `projectpilot` command opens the backend control console for a human operator. The executor is only available through explicit `projectpilot executor ...` commands.

Key package areas:

- `projectpilot/backend_console.py`: terminal backend control console.
- `projectpilot/executor/`: headless executor configuration, polling, task execution, backend publishing, and remote helpers.
- `projectpilot/git/`: Git inspection, analysis, planning, and safe execution helpers.
- `projectpilot/integration/`: backend-facing integration functions.
- `projectpilot/models/`: structured data models used across the package.

## Executor Boundary

The executor is a worker process. It should not own a GUI or browser app.

Allowed executor responsibilities:

- save and load connection configuration;
- poll backend task APIs;
- inspect allowed local or remote project paths;
- execute approved tasks;
- publish structured task results.

Human-facing UI belongs in:

- the backend control console (`projectpilot/backend_console.py`);
- the desktop management prototype (`projectpilot-tauri-app/`);
- future web or desktop control surfaces that call backend APIs.

## Desktop Prototype

`projectpilot-tauri-app/` contains:

- `src/`: browser UI code;
- `src-tauri/`: Tauri shell and Rust commands;
- `backend/`: local FastAPI backend used by the prototype;
- `scripts/`: development and build helpers.

Do not commit generated desktop-app artifacts. The root `.gitignore` excludes local toolchains, dependency folders, build outputs, packaged installers, and local SQLite databases under this directory.

## Generated And Local State

Ignored local state includes:

- Python caches and virtual environments;
- `dist/`, `build/`, and package metadata;
- `.projectpilot/reports/` and `.projectpilot/audit/`;
- desktop app dependency folders and build outputs;
- local SQLite databases created by the desktop prototype.
