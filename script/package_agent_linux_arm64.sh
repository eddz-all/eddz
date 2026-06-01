#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TUI_DIR="$ROOT_DIR/tui/projectpilot-tui"
DIST_ROOT="$ROOT_DIR/dist"
PACKAGE_DIR="$DIST_ROOT/projectpilot-agent-linux-arm64"
ARCHIVE="$DIST_ROOT/projectpilot-agent-linux-arm64.tar.gz"
TARGET="aarch64-unknown-linux-musl"
CARGO_BIN="${CARGO_BIN:-$HOME/.cargo/bin/cargo}"
RUSTUP_BIN="${RUSTUP_BIN:-$HOME/.cargo/bin/rustup}"

if [[ ! -x "$CARGO_BIN" ]]; then
  if command -v cargo >/dev/null 2>&1; then
    CARGO_BIN="$(command -v cargo)"
  else
    echo "cargo was not found. Install Rust on the build machine first." >&2
    exit 1
  fi
fi

if [[ ! -x "$RUSTUP_BIN" ]]; then
  if command -v rustup >/dev/null 2>&1; then
    RUSTUP_BIN="$(command -v rustup)"
  else
    echo "rustup was not found. Install Rust on the build machine first." >&2
    exit 1
  fi
fi

if ! "$RUSTUP_BIN" target list --installed | grep -qx "$TARGET"; then
  echo "==> Installing Rust target $TARGET"
  "$RUSTUP_BIN" target add "$TARGET"
fi

cd "$ROOT_DIR"

echo "==> Building Linux arm64 static TUI binary"
RUSTFLAGS="-C linker=rust-lld" "$CARGO_BIN" build \
  --release \
  --target "$TARGET" \
  --manifest-path "$TUI_DIR/Cargo.toml"

echo "==> Creating $PACKAGE_DIR"
rm -rf "$PACKAGE_DIR" "$ARCHIVE"
mkdir -p "$PACKAGE_DIR/bin" "$PACKAGE_DIR/examples"

cp "$TUI_DIR/target/$TARGET/release/projectpilot-tui" "$PACKAGE_DIR/bin/projectpilot-tui"
cp "$TUI_DIR/target/$TARGET/release/projectpilot-tui" "$PACKAGE_DIR/bin/projectpilot-agent"
chmod +x "$PACKAGE_DIR/bin/projectpilot-tui" "$PACKAGE_DIR/bin/projectpilot-agent"

cat > "$PACKAGE_DIR/install.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

APP_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"

mkdir -p "$BIN_DIR"
cp "$APP_HOME/bin/projectpilot-tui" "$BIN_DIR/projectpilot-tui"
cp "$APP_HOME/bin/projectpilot-agent" "$BIN_DIR/projectpilot-agent"
chmod +x "$BIN_DIR/projectpilot-tui" "$BIN_DIR/projectpilot-agent"

echo "Installed:"
echo "  $BIN_DIR/projectpilot-tui"
echo "  $BIN_DIR/projectpilot-agent"
echo
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "Add this to your shell profile if needed:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac
SH
chmod +x "$PACKAGE_DIR/install.sh"

cat > "$PACKAGE_DIR/examples/run-script-task.json" <<'JSON'
{
  "type": "run_script",
  "approved": true,
  "project_path": "/home/hzy",
  "interpreter": "bash",
  "script": "set -euo pipefail\necho PROJECTPILOT_SERVER_OK\nwhoami\npwd\nuname -a\n",
  "params": {
    "env": {
      "PROJECTPILOT_ENV": "production"
    },
    "args": []
  }
}
JSON

cat > "$PACKAGE_DIR/README.md" <<'MD'
# ProjectPilot Agent for Linux arm64

This package is intended to be copied to an Ubuntu server. It does not require
Rust, Python, a virtualenv, or source code on the customer machine.

## Install

```bash
tar -xzf projectpilot-agent-linux-arm64.tar.gz
cd projectpilot-agent-linux-arm64
./install.sh
```

By default this installs to `~/.local/bin`. Override with:

```bash
PREFIX=/usr/local ./install.sh
```

## Run On The Server

The reviewer SSHs into the server and starts the TUI there:

```bash
projectpilot-tui \
  --server-url http://BACKEND_HOST:PORT \
  --token YOUR_TOKEN \
  --executor-id ubuntu \
  --execution-mode local
```

Equivalent environment variables:

```bash
export PROJECTPILOT_SERVER_URL=http://BACKEND_HOST:PORT
export PROJECTPILOT_EXECUTOR_TOKEN=YOUR_TOKEN
export PROJECTPILOT_EXECUTOR_ID=ubuntu
export PROJECTPILOT_EXECUTION_MODE=local
projectpilot-tui
```

## Runtime Model

`local` execution means the script runs on the same Linux server where the TUI
is launched:

```text
cd <project_path> && bash -s --
```

The reviewer can inspect, edit, approve, or reject the script in the terminal.
After execution, stdout, stderr, exit code, script hashes, and metadata are sent
back to the backend.

`--execution-mode ssh` is only for remote debugging from another machine.

## Task Shape

See `examples/run-script-task.json`.
MD

echo "==> Verifying binary"
file "$PACKAGE_DIR/bin/projectpilot-tui"

echo "==> Creating archive $ARCHIVE"
tar -C "$DIST_ROOT" -czf "$ARCHIVE" "$(basename "$PACKAGE_DIR")"

echo "==> Linux arm64 package ready:"
echo "    $ARCHIVE"
