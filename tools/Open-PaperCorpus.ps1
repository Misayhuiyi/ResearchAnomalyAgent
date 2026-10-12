param([int]$Port=8895,[switch]$NoOpen)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$corpusRoot=Join-Path $projectRoot 'test-corpus'
if(-not (Test-Path -LiteralPath (Join-Path $corpusRoot 'manifest.json'))){throw '测试材料未准备，请先运行 tools/prepare_paper_corpus.py。'}
$pythonCandidates=@((Join-Path $projectRoot '.venv\Scripts\python.exe'),(Join-Path $projectRoot 'mvp-demo\.venv\Scripts\python.exe'),(Join-Path (Split-Path -Parent $projectRoot) 'mvp-demo\.venv\Scripts\python.exe'))
$pythonPath=$pythonCandidates | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
if(-not $pythonPath){$pythonPath=(Get-Command python -ErrorAction Stop).Source}
if($Port -lt 1024 -or $Port -gt 65535){throw '请选择有效的本机端口。'}
$baseUrl="http://127.0.0.1:$Port/"
$runtimeTarget=Join-Path $projectRoot 'test-results\manual-runtime'
$pointerPath=Join-Path $corpusRoot 'current-test-results.json'
if(Test-Path -LiteralPath $pointerPath){
    $pointer=Get-Content -LiteralPath $pointerPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $candidate=[IO.Path]::GetFullPath((Join-Path $projectRoot ($pointer.results_relative+'\runtime')))
    $resultsBoundary=[IO.Path]::GetFullPath((Join-Path $projectRoot 'test-results'))+[IO.Path]::DirectorySeparatorChar
    if(-not $candidate.StartsWith($resultsBoundary,[StringComparison]::OrdinalIgnoreCase)){throw '测试记录路径不在项目目录内。'}
    if(Test-Path -LiteralPath $candidate){$runtimeTarget=$candidate}
}
$runtimeText=[IO.Path]::GetFullPath($runtimeTarget).Replace('\','/').ToLowerInvariant()
$hasher=[Security.Cryptography.SHA256]::Create()
try{$runtimeId=([BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($runtimeText)))).Replace('-','').ToLowerInvariant().Substring(0,16)}finally{$hasher.Dispose()}
$ready=$false
try{$health=Invoke-RestMethod -Uri ($baseUrl+'api/health') -TimeoutSec 3;$ready=$health.ok -and $health.service -eq 'PaperAudit MVP' -and $health.runtime_id -eq $runtimeId}catch{}
if(-not $ready){
    if(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue){throw '该端口正被其他程序使用，请设置其他 Port。'}
    $env:PAPER_AUDIT_RUNTIME_DIR=$runtimeTarget
    $env:PYTHONIOENCODING='utf-8'
    $serviceArgs=@('-u',('"'+(Join-Path $projectRoot 'mvp-demo\app.py')+'"'),'--port',$Port)
    $serviceProcess=Start-Process -FilePath $pythonPath -ArgumentList $serviceArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
    for($attempt=0;$attempt -lt 30;$attempt++){
        Start-Sleep -Milliseconds 500
        try{$health=Invoke-RestMethod -Uri ($baseUrl+'api/health') -TimeoutSec 2;if($health.ok -and $health.runtime_id -eq $runtimeId){$ready=$true;break}}catch{}
        if($serviceProcess.HasExited){break}
    }
    if(-not $ready){throw '检查工具未启动；请检查 Python 依赖和 PaperConan 是否已安装。'}
}
if(-not $NoOpen){Start-Process $baseUrl;Start-Process (Join-Path $corpusRoot '测试集导航.html')}
Write-Host '已打开检查工具和测试集导航。扫描免费，智能解释需要在页面单独确认费用。'
