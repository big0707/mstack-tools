param([string]$PythonExe = 'python')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $PythonExe -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create virtual environment. Specify -PythonExe with Python 3.10+.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.\.venv\Scripts\python.exe' -m log_checker doctor
exit $LASTEXITCODE
