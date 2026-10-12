$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw '尚未安装依赖，请先运行 setup.ps1。'
}

Start-Process 'http://127.0.0.1:8765'
& $VenvPython (Join-Path $ProjectRoot 'app.py') --host 127.0.0.1 --port 8765
