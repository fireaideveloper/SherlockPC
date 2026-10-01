@echo off
setlocal
cd /d "%~dp0"

echo [SherlockPC] Desktop Alpha development launcher

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3 was not found in PATH.
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js/npm was not found in PATH.
  exit /b 1
)

where cargo >nul 2>&1
if errorlevel 1 (
  echo ERROR: Rust/Cargo was not found in PATH.
  echo Install Rust with rustup, then reopen the terminal.
  exit /b 1
)

python -m pip install -e .
if errorlevel 1 exit /b 1

pushd desktop
if not exist node_modules (
  call npm install
  if errorlevel 1 exit /b 1
)

call npm run tauri dev
set EXIT_CODE=%ERRORLEVEL%
popd
exit /b %EXIT_CODE%
