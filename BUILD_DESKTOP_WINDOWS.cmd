@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title SherlockPC v0.1 - Windows Release Builder

set "NO_PAUSE="
if /I "%~1"=="--ci" set "NO_PAUSE=1"
set "VERSION=0.1"
set "RELEASE_DIR=%CD%\release"
set "CARGO_TARGET_DIR=%CD%\desktop\src-tauri\target"

cls
echo ============================================================
echo   SherlockPC v%VERSION% - Windows Release Builder
echo   Observe ^& Investigate
echo ============================================================
echo.

echo [1/9] Checking release files...
if not exist "desktop\package.json" (echo ERROR: desktop\package.json is missing. & goto :fail)
if not exist "desktop\src-tauri\tauri.conf.json" (echo ERROR: Tauri config is missing. & goto :fail)
if not exist "desktop\src-tauri\icons\icon.ico" (echo ERROR: SherlockPC icon is missing. & goto :fail)
if not exist "desktop\src-tauri\binaries\.gitkeep" (echo ERROR: desktop\src-tauri\binaries is missing. & goto :fail)
if not exist "tests\test_telemetry.py" (echo ERROR: Python test suite is missing from tests\. Re-extract the full release archive. & goto :fail)
if exist "desktop\src-tauri\binares" (echo ERROR: legacy typo folder desktop\src-tauri\binares still exists. & goto :fail)
echo OK

echo.
echo [2/9] Checking Python...
set "PY_CMD=python"
python --version >nul 2>&1
if errorlevel 1 (
  py -3 --version >nul 2>&1
  if errorlevel 1 (echo ERROR: Python 3 was not found. & goto :fail)
  set "PY_CMD=py -3"
)
%PY_CMD% --version

echo.
echo [3/9] Checking Node/npm and Rust/Cargo...
where node >nul 2>&1 || (echo ERROR: Node.js was not found. & goto :fail)
where npm >nul 2>&1 || (echo ERROR: npm was not found. & goto :fail)
where cargo >nul 2>&1 || (echo ERROR: Cargo was not found. & goto :fail)
where rustc >nul 2>&1 || (echo ERROR: rustc was not found. & goto :fail)
node --version
call npm --version
cargo --version
set "TARGET_TRIPLE="
for /f "delims=" %%T in ('rustc --print host-tuple') do set "TARGET_TRIPLE=%%T"
if not defined TARGET_TRIPLE (echo ERROR: Could not resolve Rust target triple. & goto :fail)
echo Target: %TARGET_TRIPLE%
if not "%TARGET_TRIPLE%"=="x86_64-pc-windows-msvc" (echo ERROR: This release requires Rust x64 MSVC. & goto :fail)
%PY_CMD% -c "import struct,sys; sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (echo ERROR: Python 3.11 or newer, 64-bit is required. & goto :fail)

echo.
echo [4/9] Preparing isolated Python build environment...
if not exist ".venv-desktop-build\Scripts\python.exe" (
  %PY_CMD% -m venv .venv-desktop-build
  if errorlevel 1 goto :fail
)
set PY_CMD="%CD%\.venv-desktop-build\Scripts\python.exe"
%PY_CMD% -m pip install -e ".[dev,desktop-build]"
if errorlevel 1 goto :fail

echo.
echo [5/9] Running Python test suite...
%PY_CMD% -m pytest "%~dp0tests" -q
if errorlevel 1 (
  echo ERROR: Python tests failed. Release build stopped.
  goto :fail
)

echo.
echo [6/9] Building and smoke-testing standalone backend...
%PY_CMD% build_support\build_desktop_sidecar.py
if errorlevel 1 goto :fail
if not exist "desktop\src-tauri\binaries\sherlock-backend-%TARGET_TRIPLE%.exe" (
  echo ERROR: Expected sidecar was not produced.
  goto :fail
)

echo.
echo [7/9] Preparing and validating frontend...
pushd desktop
if exist "package-lock.json" (
  call npm ci
) else (
  call npm install
)
if errorlevel 1 (popd & goto :fail)
call npm run check
if errorlevel 1 (popd & echo ERROR: Frontend build failed. & goto :fail)
call npm test
if errorlevel 1 (popd & echo ERROR: Frontend tests failed. & goto :fail)

echo.
echo [8/9] Building Tauri release + NSIS installer...
if exist "src-tauri\target\release\bundle\nsis" rmdir /s /q "src-tauri\target\release\bundle\nsis"
if exist "src-tauri\target\release\bundle\nsis" (popd & echo ERROR: Old installer is locked. Close it and retry. & goto :fail)
call npm run tauri build
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" (
  echo ERROR: Tauri release build exited with code %EXIT_CODE%.
  goto :fail
)

echo.
echo [9/9] Preparing clean release artifacts...
%PY_CMD% build_support\package_desktop_release.py
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo   SHERLOCKPC v%VERSION% IS READY
echo ============================================================
echo.
echo Release folder:
echo   %RELEASE_DIR%
echo.
echo Files:
echo   SherlockPC-v%VERSION%-Setup.exe   ^<- publish this for users
echo   SHA256SUMS.txt                    ^<- integrity hash
echo   RELEASE_NOTES.md                  ^<- GitHub release text
echo.
echo End users do NOT need Python, Node.js, npm, Rust or Cargo.
echo Data is stored in %%LOCALAPPDATA%%\SherlockPC\data\sherlock.db
echo.
if not defined NO_PAUSE pause
exit /b 0

:fail
echo.
echo ============================================================
echo   RELEASE BUILD FAILED
echo ============================================================
echo Read the error above. No release should be published yet.
echo.
if not defined NO_PAUSE pause
exit /b 1
