@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SherlockPC Desktop Alpha - Sidecar Development Launcher

cls
echo ============================================================
echo   SherlockPC Desktop Alpha - Standalone Sidecar Dev Launcher
echo ============================================================
echo.

echo [1/7] Checking project files...
if not exist "desktop\package.json" (
  echo ERROR: desktop\package.json was not found.
  echo Make sure you extracted the ENTIRE ZIP before running this file.
  goto :fail
)
if not exist "pyproject.toml" (
  echo ERROR: pyproject.toml was not found.
  goto :fail
)
if not exist "desktop\src-tauri\icons\icon.ico" (
  echo ERROR: required Tauri icon is missing.
  goto :fail
)
echo OK

echo.
echo [2/7] Checking Python...
set "PY_CMD=python"
python --version >nul 2>&1
if errorlevel 1 (
  py -3 --version >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python 3 was not found. Python is required to BUILD the sidecar.
    goto :fail
  )
  set "PY_CMD=py -3"
)
%PY_CMD% --version

echo.
echo [3/7] Checking Node.js and npm...
where node >nul 2>&1 || (echo ERROR: Node.js was not found in PATH. & goto :fail)
where npm >nul 2>&1 || (echo ERROR: npm was not found in PATH. & goto :fail)
node --version
call npm --version
if errorlevel 1 goto :fail

echo.
echo [4/7] Checking Rust and Cargo...
where cargo >nul 2>&1 || (echo ERROR: Rust/Cargo was not found in PATH. & goto :fail)
cargo --version
rustc --print host-tuple
if errorlevel 1 goto :fail

echo.
echo [5/7] Installing build dependencies and preparing Python sidecar...
%PY_CMD% -m pip install -e ".[desktop-build]"
if errorlevel 1 (
  echo ERROR: Python/PyInstaller dependency installation failed.
  goto :fail
)
%PY_CMD% build_support\build_desktop_sidecar.py --if-needed
if errorlevel 1 (
  echo ERROR: SherlockPC backend sidecar build failed.
  goto :fail
)

echo.
echo [6/7] Preparing frontend...
pushd desktop
if errorlevel 1 goto :fail
if not exist "node_modules" (
  call npm install
  if errorlevel 1 (
    popd
    echo ERROR: npm install failed.
    goto :fail
  )
) else (
  echo node_modules already exists - skipping npm install.
)

echo.
echo [7/7] Starting Tauri with the bundled Python sidecar...
echo The UI no longer calls python.exe at runtime.
echo Keep this terminal open while development mode is running.
echo.
call npm run tauri dev
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo ERROR: Tauri exited with code %EXIT_CODE%.
  goto :fail
)

echo.
echo SherlockPC Desktop closed normally.
goto :success

:fail
echo.
echo ============================================================
echo   SherlockPC Desktop DID NOT START
echo ============================================================
echo Read the ERROR message above. This window will stay open.
echo.
pause
exit /b 1

:success
echo.
pause
exit /b 0
