@echo off
setlocal
cd /d "%~dp0"
if exist dist\SherlockBenchCollector.exe (
    start "" dist\SherlockBenchCollector.exe
    exit /b 0
)
if not exist .venv-build-auto\Scripts\python.exe goto missing
.venv-build-auto\Scripts\python.exe collector_launcher.py
if errorlevel 1 pause
exit /b
:missing
echo Run BUILD_WINDOWS.cmd first. It installs Python and dependencies automatically.
pause
exit /b 1
