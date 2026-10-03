# SherlockPC Desktop Alpha — standalone sidecar build

The desktop shell now runs the existing deterministic SherlockPC core through a **bundled Python sidecar** instead of calling a system `python.exe`.

## Runtime architecture

```text
SherlockPC.exe (Tauri 2)
    ↓ invoke("backend_call")
Rust allow-listed command
    ↓ tauri-plugin-shell sidecar
sherlock-backend-<target-triple>.exe
    ↓ JSON argument / JSON stdout
DesktopService
    ├── StateCollector
    ├── StateRepository / SQLite
    └── Investigation Engine
          ├── Investigator
          ├── Critic
          └── Verifier
```

The sidecar is built from `sherlock/desktop_bridge.py` with PyInstaller `--onefile`. Tauri bundles it through `bundle.externalBin`.

## Data location

The packaged app stores its database in a writable per-user location instead of beside the installed EXE:

```text
%LOCALAPPDATA%\SherlockPC\data\sherlock.db
```

`SHERLOCK_DB_PATH` can still override the location for development/tests.

## Development

Run from the repository root:

```bat
RUN_DESKTOP_DEV.cmd
```

The launcher:

1. checks Python, Node/npm and Rust/Cargo;
2. installs the `desktop-build` Python extra (PyInstaller);
3. builds/refreshes the target-specific backend sidecar;
4. installs frontend dependencies when required;
5. runs `tauri dev`.

Python is still required on a developer machine to **build** the sidecar, but the Tauri UI itself talks to the sidecar rather than `python.exe`.

## Windows release build

Run:

```bat
BUILD_DESKTOP_WINDOWS.cmd
```

Expected outputs:

```text
desktop\src-tauri\target\release\sherlockpc-desktop.exe
desktop\src-tauri\target\release\bundle\nsis\*.exe
```

The NSIS setup contains both the Tauri application and the packaged Python backend. A target Windows user does **not** need Python, Node.js/npm, or Rust installed.

## Security boundary

The React frontend still has no generic shell endpoint. It invokes one Rust command, and the Python bridge still accepts only the explicit operations `ping`, `overview`, `capture_state`, `recent_states`, and `investigate`.

## Current limitation

The PyInstaller backend is a one-shot sidecar: one process is started for each backend request. This keeps the Alpha architecture simple and distributable. A later optimization can turn it into a long-running local worker to reduce cold-start overhead while preserving the same allow-listed command boundary.
