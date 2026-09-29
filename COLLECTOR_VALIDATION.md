# Collector validation

Validation performed in Linux on the provided project plus collector changes:

- Full pytest suite: 109 passed.
- Real subprocess smoke: all four scenarios, 2/2/2-second phases, one repeat, 16 MiB and CPU duty 0.1. Completed successfully and created a ZIP.
- Real cancellation during the active mixed-load phase: metadata marked interrupted, forced_terminations=0, no active child processes after return.
- Python sources compiled successfully.

Not verified in this environment: Windows EXE build, execution without installed Python,
Tk window rendering, Windows sleep-inhibition API and Windows file-lock behavior.
Follow COLLECTOR_START_RU.md to validate the Windows executable before distributing it.
This archive contains source code and build commands, not a prebuilt executable.

Automatic build update: BUILD_WINDOWS.cmd delegates to BUILD_WINDOWS.ps1. Python detection, install-manager route, signed python.org fallback, checked native exit codes and build.log added. Windows installation/build and PowerShell execution have not been run in this Linux environment. Previous collector runtime checks above are unchanged.

Build revision auto-install-2: moved Python detection from native -c argument to build_support/check_runtime.py to avoid Windows PowerShell 5.1 quote loss. Checked probe success and wrong-version rejection via simulated sys.version_info on Linux. Detection errors retained in python-probe.log. Windows end-to-end build remains untested.
