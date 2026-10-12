param([Parameter(Mandatory=$true)][string]$Docx,
      [Parameter(Mandatory=$true)][string]$Pdf)
$ErrorActionPreference='Stop'
$source=(Resolve-Path -LiteralPath $Docx).Path
$target=[IO.Path]::GetFullPath($Pdf)
$evidenceRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\docs\verification')).TrimEnd('\')
if(-not $target.StartsWith($evidenceRoot+'\',[StringComparison]::OrdinalIgnoreCase)){
    throw 'Render output must be under docs/verification.'
}
if(Test-Path -LiteralPath $target){throw 'Render output already exists.'}
New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
$word=$null
$document=$null
$initialDocumentCount=0
$originalVisible=$false
$originalAlerts=0
try {
    $word=New-Object -ComObject Word.Application
    $initialDocumentCount=$word.Documents.Count
    $originalVisible=$word.Visible
    $originalAlerts=$word.DisplayAlerts
    if($initialDocumentCount -eq 0){$word.Visible=$false}
    $word.DisplayAlerts=0
    $document=$word.Documents.Open($source,$false,$true,$false)
    $document.ExportAsFixedFormat($target,17)
    if(-not (Test-Path -LiteralPath $target)){throw 'Word did not create the PDF.'}
    "Native Office render: $target"
} finally {
    if($null -ne $document){
        try {$document.Close(0)} catch [Runtime.InteropServices.COMException] {
            if($_.Exception.HResult -ne -2147023174){throw}
        }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if($null -ne $word){
        try {
            $remaining=$word.Documents.Count
            if($initialDocumentCount -eq 0 -and $remaining -eq 0){$word.Quit(0)}
            elseif($remaining -gt 0){
                $word.DisplayAlerts=$originalAlerts
                if($initialDocumentCount -gt 0){$word.Visible=$originalVisible}else{$word.Visible=$true}
            }
        } catch [Runtime.InteropServices.COMException] {
            # Some native Office providers terminate after closing their last
            # hidden document. RPC unavailable means the owned process is gone.
            if($_.Exception.HResult -ne -2147023174){throw}
        }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
}
