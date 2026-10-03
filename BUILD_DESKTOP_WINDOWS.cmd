@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SherlockPC Desktop - Windows Release Builder

cls
echo ============================================================
echo   SherlockPC Desktop - Standalone Windows Release Builder
echo ============================================================
echo.

echo [1/7] Checking project files...
if not exist "desktop\package.json" (echo ERROR: desktop\package.json is missing. & goto :fail)
if not exist "desktop\src-tauri\tauri.conf.json" (echo ERROR: Tauri config is missing. & goto :fail)
if not exist "desktop\src-tauri\icons\icon.ico" (echo ERROR: Tauri icon is missing. & goto :fail)
echo OK

echo.
echo [2/7] Checking Python...
set "PY_CMD=python"
python --version >nul 2>&1
if errorlevel 1 (
  py -3 --version >nul 2>&1
  if errorlevel 1 (echo ERROR: Python 3 was not found. & goto :fail)
  set "PY_CMD=py -3"
)
%PY_CMD% --version

echo.
echo [3/7] Checking Node/npm and Rust/Cargo...
where node >nul 2>&1 || (echo ERROR: Node.js was not found. & goto :fail)
where npm >nul 2>&1 || (echo ERROR: npm was not found. & goto :fail)
where cargo >nul 2>&1 || (echo ERROR: Cargo was not found. & goto :fail)
node --version
call npm --version
cargo --version
for /f "delims=" %%T in ('rustc --print host-tuple') do set "TARGET_TRIPLE=%%T"
if not defined TARGET_TRIPLE (echo ERROR: Could not resolve Rust target triple. & goto :fail)
echo Target: %TARGET_TRIPLE%

echo.
echo [4/7] Installing Python build dependencies...
%PY_CMD% -m pip install -e ".[desktop-build]"
if errorlevel 1 goto :fail

echo.
echo [5/7] Building standalone Sherlock backend sidecar...
%PY_CMD% build_support\build_desktop_sidecar.py
if errorlevel 1 goto :fail
if not exist "desktop\src-tauri\binaries\sherlock-backend-%TARGET_TRIPLE%.exe" (
  echo ERROR: Expected sidecar was not produced.
  goto :fail
)

echo.
echo [6/7] Preparing frontend dependencies...
pushd desktop
if not exist "node_modules" (
  call npm install
  if errorlevel 1 (popd & goto :fail)
) else (
  echo node_modules already exists - skipping npm install.
)

echo.
echo [7/7] Building Tauri release + NSIS installer...
call npm run tauri build
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" (
  echo ERROR: Tauri release build exited with code %EXIT_CODE%.
  goto :fail
)

echo.
echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo Standalone EXE:
echo   desktop\src-tauri\target\release\sherlockpc-desktop.exe
echo.
echo Installer folder:
echo   desktop\src-tauri\target\release\bundle\nsis\
echo.
echo End users do NOT need Python, Node.js, npm or Rust installed.
echo.
pause
exit /b 0

:fail
echo.
echo ============================================================
echo   RELEASE BUILD FAILED
echo ============================================================
echo Read the error above. This window will stay open.
echo.
pause
exit /b 1
