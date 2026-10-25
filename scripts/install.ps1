$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$transcriptStarted = $false
try {
    Start-Transcript -Path (Join-Path $projectRoot 'installation.log') -Append | Out-Null
    $transcriptStarted = $true
    Write-Host 'PanoTess - preparing your private Python environment' -ForegroundColor Cyan

    function Find-CompatiblePython {
        $candidates = [System.Collections.Generic.List[string]]::new()
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            $listed = & $launcher.Source --list-paths 2>$null
            foreach ($line in $listed) {
                if ($line -match '([A-Za-z]:\\.+python(?:3)?\.exe)\s*$') {
                    $candidates.Add($Matches[1])
                }
            }
        }
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
            $candidates.Add($pythonCommand.Source)
        }
        $localPythonRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
        if (Test-Path -LiteralPath $localPythonRoot) {
            Get-ChildItem -LiteralPath $localPythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
                ForEach-Object { $candidates.Add($_.FullName) }
        }
        foreach ($candidate in ($candidates | Select-Object -Unique)) {
            & $candidate -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,15) and sys.maxsize > 2**32 else 1)'
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
        return $null
    }

    $pythonPath = Find-CompatiblePython
    if (-not $pythonPath) {
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw 'Python 3.11-3.14 (64-bit) is required. Install it from https://www.python.org/downloads/windows/ then run this installer again.'
        }
        Write-Host 'Installing Python 3.13 for the current Windows user...'
        & $winget.Source install --id Python.Python.3.13 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'E_PYTHON_INSTALL: Python installation failed.' }
        $pythonPath = Find-CompatiblePython
        if (-not $pythonPath) { throw 'E_PYTHON_NOT_FOUND: Close this installer and run it again to detect the newly installed Python.' }
    }
    Write-Host "Using $pythonPath"
    $venv = Join-Path $projectRoot '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        & $pythonPath -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'E_VENV: Could not create .venv. Move PanoTess to a writable folder and retry.' }
    }
    & $venvPython -m pip install --upgrade pip --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'E_PIP: Could not prepare pip. Check your internet connection.' }
    & $venvPython -m pip install -r (Join-Path $projectRoot 'requirements.txt') --only-binary=:all: --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'E_DEPENDENCIES: Dependency installation failed. Check your internet connection and installation.log.' }
    & $venvPython -c 'import PySide6, PIL; print(PySide6.__version__, PIL.__version__)'
    if ($LASTEXITCODE -ne 0) { throw 'E_IMPORT: Installed dependencies could not be loaded.' }
    Write-Host 'PanoTess is ready.' -ForegroundColor Green
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
