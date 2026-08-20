# Batch convert: scan input\*.pdf, default Docling, output to <OutputDir>\<stem>\
param(
    [ValidateSet("Docling", "MinerU")]
    [string]$Engine = "Docling",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "input"))) {
    $Root = $PSScriptRoot
}

# Prefer active Python / PATH tools; override with env if needed
$Python = if ($env:PDF2MD_PYTHON) { $env:PDF2MD_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
$DoclingCmd = Get-Command docling -ErrorAction SilentlyContinue
$MinerUCmd = Get-Command mineru -ErrorAction SilentlyContinue

$InputDir = Join-Path $Root "input"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "output"
}
$LogDir = Join-Path $Root "logs"

New-Item -ItemType Directory -Force -Path $OutputDir, $LogDir | Out-Null
$pdfs = Get-ChildItem -Path $InputDir -Filter *.pdf -File -ErrorAction SilentlyContinue
if (-not $pdfs) {
    Write-Host "No PDF in input: $InputDir"
    exit 0
}

foreach ($pdf in $pdfs) {
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($pdf.Name)
    $out = Join-Path $OutputDir $stem
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    Write-Host "==== Converting $($pdf.Name) ($Engine) ===="
    try {
        if ($Engine -eq "MinerU") {
            if (-not $MinerUCmd) { throw "mineru CLI not found on PATH" }
            & $MinerUCmd.Source -p $pdf.FullName -o $out -b pipeline -m auto
        } else {
            if (-not $DoclingCmd) { throw "docling CLI not found on PATH" }
            & $DoclingCmd.Source convert $pdf.FullName --to md --output $out
        }
        Write-Host "OK -> $out"
    } catch {
        Write-Host "FAIL $($pdf.Name): $_"
        $_ | Out-File -Append -FilePath (Join-Path $LogDir "convert_errors.log") -Encoding utf8
    }
}
