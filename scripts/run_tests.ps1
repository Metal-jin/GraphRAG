# 一键运行测试（任务 30：显式返回 pytest 退出码，路径相对仓库根）
param(
    [string]$Python = "python",
    [string]$Args = ""
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$repoRoot = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = Join-Path $repoRoot "src"

Push-Location $repoRoot
try {
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "GraphRAG Test Suite" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan

    $pytestArgs = @("-m", "pytest", "-v", "--tb=short")
    if ($Args -ne "") { $pytestArgs += $Args.Split(" ") }
    & $Python @pytestArgs
    $code = $LASTEXITCODE

    Write-Host ""
    if ($code -eq 0) {
        Write-Host "测试全部通过" -ForegroundColor Green
    } else {
        Write-Host "测试失败（退出码 $code）" -ForegroundColor Red
    }
    exit $code
}
finally {
    Pop-Location
}
