# k5 串行评测（从 PP-L 起；PP-M 已完成）
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'd:\Docling'
$Lock = 'benchmarks/results/.k5_pipeline.lock'
if (Test-Path $Lock) {
    $old = Get-Content $Lock -Raw
    throw "Another k5 pipeline may be running (lock: $old). Remove $Lock only if sure."
}
New-Item -ItemType Directory -Force -Path (Split-Path $Lock) | Out-Null
$PID | Set-Content $Lock
try {
$Paddle = 'd:\Docling\.venv-paddle-formula\Scripts\python.exe'
$Py = 'C:\python\python3-12.3\python.exe'
$Gold = 'benchmarks/gold/verified_all.jsonl'
$Log = "benchmarks/results/k5_pipeline_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

function Log($msg) { $msg | Tee-Object -FilePath $Log -Append }

function Run-Step([string]$Name, [scriptblock]$Block) {
    Log "=== $(Get-Date -Format o) $Name ==="
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Block 2>&1 | Tee-Object -FilePath $Log -Append
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) { throw "$Name failed exit=$code" }
}

Run-Step 'PP-L 361' {
    & $Paddle scripts/run_ppformula_on_crops.py --gold $Gold --model PP-FormulaNet_plus-L --prefer-tight --out benchmarks/results/pp_l_verified_all_tight.json
}

Run-Step 'PaddleVL 361' {
    & $Paddle scripts/run_paddlevl_on_crops.py --gold $Gold --prefer-tight --out benchmarks/results/paddlevl_verified_all_tight.json
}

Run-Step 'L2 chunks' {
    & $Py scripts/run_l2_unscored_chunks.py --chunk 10
}

Run-Step 'merge compare' {
    & $Py scripts/run_k5_full_recognition_compare.py
}
Run-Step 'shadow gate' {
    & $Py scripts/run_shadow_gate_calibration.py
}
Run-Step 'hard200' {
    & $Py scripts/build_hard200_manifest.py
}

Log "=== $(Get-Date -Format o) DONE ==="
} finally {
    Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}
