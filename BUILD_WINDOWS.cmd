@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0BUILD_WINDOWS.ps1"
if errorlevel 1 goto failed
echo.
echo SUCCESS: dist\SherlockBenchCollector.exe
pause
exit /b 0
:failed
echo.
echo BUILD FAILED. Send build.log from this folder to the developer.
echo If build.log is missing, send the error displayed above.
pause
exit /b 1
