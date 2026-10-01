# SherlockPC Desktop Alpha

Desktop Alpha is the first real UI layer on top of the existing deterministic SherlockPC core.
It is intentionally small: **Diagnose only**, no LLM router, no actions and no unrestricted shell execution.

## What is connected already

```text
Tauri 2 window
    ↓ invoke("backend_call")
Rust allow-listed command
    ↓ JSON via stdin/stdout
python -m sherlock.desktop_bridge
    ↓
DesktopService
    ├── StateCollector
    ├── StateRepository / SQLite
    └── Investigation Engine
          ├── Investigator
          ├── Critic
          └── Verifier
```

The UI displays real values from the current machine:

- CPU usage;
- RAM usage and available memory;
- swap usage;
- process count;
- top processes by RSS memory;
- recent stored state snapshots;
- investigation status, conclusion, hypotheses, evidence references and trace.

## Important limitations

- The text question is **not interpreted by an LLM yet**. Desktop Alpha attaches it to the current Diagnose flow.
- The existing Investigation Engine currently reasons about CPU/RAM/swap resource signals. It does not establish a root cause.
- On a fresh database, the engine will normally return `INSUFFICIENT_EVIDENCE` until enough historical snapshots exist.
- Disk/GPU health cards are deliberately not shown because the current state model does not collect those health metrics.
- The current Tauri Rust command launches the repository Python backend during development. A release EXE should replace that development dependency with a bundled PyInstaller sidecar.

## Run on Windows

Requirements for development:

1. Python 3.11+.
2. Node.js/npm.
3. Rust/Cargo (rustup).
4. Microsoft C++ Build Tools / WebView2 requirements used by Tauri on Windows.

From the repository root:

```bat
RUN_DESKTOP_DEV.cmd
```

The launcher installs the Python package editable, installs frontend dependencies if needed and starts `tauri dev`.

Manual equivalent:

```powershell
python -m pip install -e .
cd desktop
npm install
npm run tauri dev
```

## Backend bridge smoke test

Without starting Tauri:

```powershell
'{"action":"ping"}' | python -m sherlock.desktop_bridge
'{"action":"overview"}' | python -m sherlock.desktop_bridge
```

## Next packaging step

For a distributable `SherlockPC.exe`, package `sherlock.desktop_bridge` and the Python core as a PyInstaller executable and register it in Tauri as an `externalBin` sidecar. That removes the requirement for the end user to have Python installed.
