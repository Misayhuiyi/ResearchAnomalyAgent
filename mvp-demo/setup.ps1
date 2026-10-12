$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    py -3 -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw '创建运行环境失败。' }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw '安装工具更新失败。' }
& $VenvPython -m pip install -r (Join-Path $ProjectRoot 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw '安装依赖失败。' }
& $VenvPython -m unittest discover -s (Join-Path $ProjectRoot 'tests') -v
if ($LASTEXITCODE -ne 0) { throw '测试未通过，请查看上方失败信息。' }

Write-Host ''
Write-Host '安装和测试已完成。运行 .\start.ps1 启动 Demo。' -ForegroundColor Green
