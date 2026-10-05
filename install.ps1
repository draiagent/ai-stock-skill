$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .venv/Scripts/python.exe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '建立 venv 失敗' }
}
& .venv/Scripts/python.exe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw '套件安裝失敗' }
& .venv/Scripts/python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw '套件相依性檢查失敗' }
