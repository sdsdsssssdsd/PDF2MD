# 一键同步 Docling → github-submit 并推送到 GitHub
# 用法: .\scripts\publish_github_submit.ps1 "提交说明（可选）"
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommitMessage
)

$msg = ($CommitMessage -join " ").Trim()
if ($msg) {
    python "$PSScriptRoot\publish_github_submit.py" $msg
} else {
    python "$PSScriptRoot\publish_github_submit.py"
}
exit $LASTEXITCODE
