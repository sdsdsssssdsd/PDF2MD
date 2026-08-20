# Create / refresh PDF2MD.lnk next to project root with custom icon.
param(
    [string]$Root = "",
    [string]$TargetBat = ""
)

$ErrorActionPreference = "Stop"
if (-not $Root) {
    $Root = Split-Path -Parent $PSScriptRoot
}
$Root = (Resolve-Path $Root).Path
$icon = Join-Path $Root "icons\pdf2md.ico"
if (-not (Test-Path -LiteralPath $icon)) {
    Write-Error "Icon not found: $icon"
}

if (-not $TargetBat) {
    $candidates = @(
        (Join-Path $Root "run_gui.bat"),
        (Join-Path $Root "启动PDF2MD.bat")
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { $TargetBat = $c; break }
    }
}
if (-not $TargetBat -or -not (Test-Path -LiteralPath $TargetBat)) {
    Write-Error "Launcher bat not found under $Root"
}

$lnkPath = Join-Path $Root "PDF2MD.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnkPath)
$s.TargetPath = $TargetBat
$s.WorkingDirectory = $Root
$s.IconLocation = "$icon,0"
$s.Description = "PDF2MD — academic PDF to Markdown"
$s.Save()
Write-Output "Shortcut ready: $lnkPath"
