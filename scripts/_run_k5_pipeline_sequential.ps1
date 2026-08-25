# k5 串行评测流水线（避免 GPU 互抢）
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $PSScriptRoot\..
$Paddle = if ($env:PDF2MD_PADDLE_PYTHON) { $env:PDF2MD_PADDLE_PYTHON } else { 'python' }
$Py = if ($env:PDF2MD_PYTHON) { $env:PDF2MD_PYTHON } else { 'python' }
$Ds = if ($env:PDF2MD_DSOCR2_PYTHON) { $env:PDF2MD_DSOCR2_PYTHON } else { 'python' }
$Gold = 'benchmarks/gold/verified_all.jsonl'

Write-Host '=== PP-L 361 ===' -ForegroundColor Cyan
& $Paddle scripts/run_ppformula_on_crops.py --gold $Gold --model PP-FormulaNet_plus-L --prefer-tight --out benchmarks/results/pp_l_verified_all_tight.json

Write-Host '=== PaddleVL 361 ===' -ForegroundColor Cyan
& $Paddle scripts/run_paddlevl_on_crops.py --gold $Gold --prefer-tight --out benchmarks/results/paddlevl_verified_all_tight.json

Write-Host '=== L2 52 chunks ===' -ForegroundColor Cyan
& $Py scripts/run_l2_unscored_chunks.py --chunk 10

Write-Host '=== merge + gate ===' -ForegroundColor Cyan
& $Py scripts/run_k5_full_recognition_compare.py
& $Py scripts/run_shadow_gate_calibration.py
& $Py scripts/build_hard200_manifest.py

Write-Host 'DONE' -ForegroundColor Green
