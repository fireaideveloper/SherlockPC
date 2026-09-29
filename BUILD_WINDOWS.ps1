# Windows PowerShell 5.1 compatible. Invoked by BUILD_WINDOWS.cmd.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$transcribing = $false
$stage = 'initialization'

function Find-Python312 {
    $probe = Join-Path $PSScriptRoot 'build_support\check_runtime.py'
    $probeLog = Join-Path $PSScriptRoot 'python-probe.log'
    if (-not (Test-Path -LiteralPath $probe)) { throw "Missing runtime check: $probe. Extract the entire ZIP." }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'SherlockBenchBuild\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
    )
    # Missing runtimes and obsolete launchers may write to stderr; these are probes.
    $ErrorActionPreference = 'Continue'
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $result = & $candidate $probe 2>>$probeLog
            if ($LASTEXITCODE -eq 0 -and $result) { return [string]($result | Select-Object -Last 1) }
        }
    }
    foreach ($launcher in @('py', 'pymanager')) {
        if (Get-Command $launcher -ErrorAction SilentlyContinue) {
            $result = & $launcher -3.12 $probe 2>>$probeLog
            if ($LASTEXITCODE -eq 0 -and $result) { return [string]($result | Select-Object -Last 1) }
        }
    }
    return $null
}

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    # Native stderr is diagnostic output, not by itself a failing exit code.
    $ErrorActionPreference = 'Continue'
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Exe" }
}

try {
    Start-Transcript -Path (Join-Path $PSScriptRoot 'build.log') -Force | Out-Null
    $transcribing = $true
    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'python-probe.log') -Value 'Python runtime detection diagnostics'
    Write-Host 'Build script revision: auto-install-2'
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    $stage = 'finding Python 3.12 x64 with Tk'
    Write-Host '[1/4] Checking Python 3.12 x64...'
    $python = Find-Python312
    if (-not $python) {
        $stage = 'installing Python with the Python install manager'
        foreach ($manager in @('pymanager', 'py')) {
            if (Get-Command $manager -ErrorAction SilentlyContinue) {
                Write-Host "Trying: $manager install 3.12"
                try { Invoke-Checked -Exe $manager -Arguments @('install', '3.12') }
                catch { Write-Host "Manager unavailable or installation failed: $_" }
                $python = Find-Python312
                if ($python) { break }
            }
        }
    }
    if (-not $python) {
        $stage = 'downloading the official Python installer'
        Write-Host 'Downloading Python 3.12.10 x64 from python.org...'
        $cache = Join-Path $env:LOCALAPPDATA 'SherlockBenchBuild'
        New-Item -ItemType Directory -Path $cache -Force | Out-Null
        $installer = Join-Path $cache 'python-3.12.10-amd64.exe'
        $target = Join-Path $cache 'Python312'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $installer
        $stage = 'checking the Python installer signature'
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|,\s*)O=Python Software Foundation(,|$)') {
            throw 'Python installer signature is not valid or its publisher is unexpected. Installation stopped.'
        }
        $stage = 'installing Python for the current Windows user'
        $installLog = Join-Path $cache 'python-install.log'
        $arguments = @('/quiet', '/norestart', 'InstallAllUsers=0', 'PrependPath=0',
            'Include_launcher=0', 'Include_pip=1', 'Include_tcltk=1', 'Include_test=0',
            'Shortcuts=0', ('TargetDir="{0}"' -f $target), '/log', ('"{0}"' -f $installLog))
        $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) { throw "Python installer exit $($process.ExitCode). Log: $installLog" }
        $python = Find-Python312
        if (-not $python) { throw "Python 3.12 x64 with Tk was not found after installation. Logs: $installLog and python-probe.log" }
    }
    Write-Host "Using Python: $python"
    $stage = 'creating the build environment'
    Write-Host '[2/4] Creating the build environment...'
    # Separate folder avoids a damaged environment left by the previous script.
    $venv = Join-Path $PSScriptRoot '.venv-build-auto'
    Invoke-Checked -Exe $python -Arguments @('-m', 'venv', $venv)
    $buildPython = Join-Path $venv 'Scripts\python.exe'
    $stage = 'installing build dependencies'
    Write-Host '[3/4] Installing dependencies...'
    Invoke-Checked -Exe $buildPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip')
    Invoke-Checked -Exe $buildPython -Arguments @('-m', 'pip', 'install', '-e', '.', 'psutil==7.2.2', 'pyinstaller>=6.11,<7')
    Invoke-Checked -Exe $buildPython -Arguments @('-c', 'import tkinter, psutil, PyInstaller; r=tkinter.Tk(); r.withdraw(); r.destroy()')
    $stage = 'building the Windows executable (close a running collector first)'
    Write-Host '[4/4] Building SherlockBenchCollector.exe...'
    Invoke-Checked -Exe $buildPython -Arguments @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--noupx', '--name', 'SherlockBenchCollector', 'collector_launcher.py')
    $output = Join-Path $PSScriptRoot 'dist\SherlockBenchCollector.exe'
    if (-not (Test-Path -LiteralPath $output)) { throw 'Build finished without the expected EXE.' }
    Write-Host "SUCCESS: $output"
    Write-Host 'Test the EXE on Windows before sharing it.'
    try { Start-Process explorer.exe -ArgumentList ('"{0}"' -f (Join-Path $PSScriptRoot 'dist')) }
    catch { Write-Host "Open the dist folder manually: $_" }
}
catch {
    Write-Host "BUILD FAILED during: $stage" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'Check your internet connection and available disk space. Send build.log if the problem persists.'
    if ($transcribing) { Stop-Transcript | Out-Null }
    exit 1
}
if ($transcribing) { Stop-Transcript | Out-Null }
exit 0
