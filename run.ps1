param([string]$Query = '查台積電 2330', [string]$Date = '')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($Date) { & .venv/Scripts/python.exe agent.py $Query --date $Date }
else { & .venv/Scripts/python.exe agent.py $Query }
exit $LASTEXITCODE
