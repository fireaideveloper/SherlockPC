@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title SherlockPC - Package existing Windows build
set "PY_CMD=python"
python --version >nul 2>&1
if errorlevel 1 set "PY_CMD=py -3"
echo Packaging an EXISTING build. Source changes require BUILD_DESKTOP_WINDOWS.cmd.
%PY_CMD% build_support\package_desktop_release.py
if errorlevel 1 goto :fail
echo Done. Open the release folder for the installer and SHA256SUMS.txt.
if /I not "%~1"=="--ci" pause
exit /b 0
:fail
echo Packaging failed. Read the error above.
if /I not "%~1"=="--ci" pause
exit /b 1
