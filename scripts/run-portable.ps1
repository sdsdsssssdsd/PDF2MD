# PDF2MD portable entry（不做 MSI）。在仓库根目录运行 GUI，不启动转换。
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error "python not found. Install Python 3.10+ and pdf2md[gui]."
    exit 1
}
python -m app @args
