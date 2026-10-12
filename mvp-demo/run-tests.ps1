$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw '尚未安装依赖，请先运行 setup.ps1。'
}

& $VenvPython -m unittest discover -s (Join-Path $ProjectRoot 'tests') -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
