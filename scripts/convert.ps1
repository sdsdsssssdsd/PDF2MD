# 批量转换：扫描 input\*.pdf，默认 Docling，输出到指定导出目录\<stem>\
param(
    [ValidateSet("Docling", "MinerU")]
    [string]$Engine = "Docling",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "input"))) {
    $Root = $PSScriptRoot
    if (-not (Test-Path (Join-Path $Root "input"))) {
        $Root = "D:\Docling"
    }
}

$Python = "C:\python\python3-12.3\python.exe"
$Docling = "C:\python\python3-12.3\Scripts\docling.exe"
$MinerU = "C:\python\python3-12.3\Scripts\mineru.exe"
$InputDir = Join-Path $Root "input"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "output"
}
$LogDir = Join-Path $Root "logs"

New-Item -ItemType Directory -Force -Path $OutputDir, $LogDir | Out-Null
$pdfs = Get-ChildItem -Path $InputDir -Filter *.pdf -File -ErrorAction SilentlyContinue
if (-not $pdfs) {
    Write-Host "input 目录没有 PDF：$InputDir"
    exit 0
}

foreach ($pdf in $pdfs) {
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($pdf.Name)
    $out = Join-Path $OutputDir $stem
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    Write-Host "==== 转换 $($pdf.Name) ($Engine) ===="
    try {
        if ($Engine -eq "MinerU") {
            & $MinerU -p $pdf.FullName -o $out -b pipeline -m auto
        } else {
            & $Docling convert $pdf.FullName --to md --output $out
        }
        Write-Host "OK -> $out"
    } catch {
        Write-Host "FAIL $($pdf.Name): $_"
        $_ | Out-File -Append -FilePath (Join-Path $LogDir "convert_errors.log") -Encoding utf8
    }
}
