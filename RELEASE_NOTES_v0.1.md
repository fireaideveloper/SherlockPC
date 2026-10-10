# SherlockPC v0.1

SherlockPC is a local Windows x64 desktop application for collecting system
measurements and investigating CPU, RAM and swap deviations against saved history.

## Available functionality

- Live overview of CPU, memory, swap, process count and recent saved states.
- Native background collection targeting a sample about every 10 seconds.
- Bounded investigations with baseline comparison, evidence references,
  hypotheses, critic/verifier results, trace and explicit limitations.
- Paginated state history, the actual database location, opening its folder,
  and confirmation before clearing states and their associated measurements.
- System tray operation: closing the window keeps collection running;
  the tray exit action stops the application. Single-instance desktop launch.
- Windows sign-in autostart controls. The installed application enables
  autostart on its first launch; later explicit user preferences are preserved.
- Light, dark and system themes, saved preferences, and 12 interface languages:
  English, Russian, Spanish, Brazilian Portuguese, Simplified Chinese, French,
  Italian, German, Japanese, Korean, Arabic and Hindi. Arabic supports RTL;
  bundled Noto fonts support offline rendering.

## Installation and data

Install `SherlockPC-v0.1-Setup.exe`. The NSIS installer bundles the Python backend;
end users do not need Python, Node.js, npm, Rust or Cargo. WebView2 is required.
Use `SHA256SUMS.txt` to verify the downloaded installer when supplied with it.

The default Windows database is
`%LOCALAPPDATA%\SherlockPC\data\sherlock.db`. The application shows its actual
location. Collection and diagnosis are local and do not require a cloud API or LLM.
Exit through the tray before backing up the complete data folder.

## Limits

- Questions label a fixed CPU/RAM/swap check; arbitrary natural-language answers
  are not implemented in the desktop release.
- Baseline readiness requires historical samples and elapsed observation time.
  Insufficient evidence is reported explicitly. A result with no detected
  deviations does not establish complete PC health or rule out hardware faults.
- Search, Recall, Actions, disk health and GPU health are not desktop features.
  File indexing/search, State Diff and workload experiments are separate Python tools.
- History has no automatic retention limit. Its database grows while collection
  runs; users can inspect its size and explicitly clear states.
- Windows x64 is the installer target. This source tree alone does not certify
  native installation, tray or autostart behavior on a particular machine.

Public version: `0.1`; npm, Cargo and Tauri version: `0.1.0`.

See [the desktop guide](docs/desktop.md) and [README](README.md) for build,
validation, privacy and usage details.
