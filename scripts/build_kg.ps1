# 一键构建知识图谱（任务 30：路径相对仓库根、模式清晰、退出码正确）
# 用法：
#   powershell -File scripts\build_kg.ps1 -Book 射雕英雄传 -Preview      # 只读预览，不调 LLM
#   powershell -File scripts\build_kg.ps1 -Book 射雕英雄传 -Limit 20 -DryRun  # 调 LLM 但不写库
#   powershell -File scripts\build_kg.ps1 -Book 射雕英雄传              # 真实入库
#   powershell -File scripts\build_kg.ps1 -Resume                       # 多书断点续跑
param(
    [string]$Book = "",
    [int]$Limit = 0,
    [int]$Size = 0,
    [int]$Overlap = 0,
    [switch]$Resume,
    [switch]$ReingestFailed,
    [switch]$Preview,
    [switch]$DryRun,
    [switch]$SaveRaw,
    [switch]$SkipChunking,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$repoRoot = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = Join-Path $repoRoot "src"

# 所有路径相对仓库根（不再依赖当前工作目录）
Push-Location $repoRoot
try {
    if (-Not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Host "[build_kg] 已从模板创建 .env，请填写 NEO4J_PASSWORD / LLM_TOKEN 后重跑。" -ForegroundColor Yellow
            exit 1
        }
        throw "缺少 .env 与 .env.example"
    }

    $chunkArgs = @()
    if ($Size -gt 0)    { $chunkArgs += "--size";    $chunkArgs += $Size }
    if ($Overlap -gt 0) { $chunkArgs += "--overlap"; $chunkArgs += $Overlap }

    if (-Not $SkipChunking -and -Not $Preview -and -Not $DryRun) {
        # 1. 切块（多书时每本一个 chunks_<书名>.json + manifest）
        if ($Book -ne "") {
            & $Python "src/ingest/corpus.py" --source "data/source/$Book.txt" @chunkArgs
        } else {
            & $Python "src/ingest/corpus.py" @chunkArgs
        }
        if ($LASTEXITCODE -ne 0) { throw "corpus.py 失败（退出码 $LASTEXITCODE）" }
    }

    # 2. LLM 抽取与入库
    $buildArgs = @()
    if ($Book -ne "") { $buildArgs += "--book"; $buildArgs += $Book }
    if ($Limit -gt 0) { $buildArgs += "--limit"; $buildArgs += $Limit }
    if ($Resume)      { $buildArgs += "--resume" }
    if ($ReingestFailed) { $buildArgs += "--reingest-failed" }
    if ($Preview)     { $buildArgs += "--preview" }
    if ($DryRun)      { $buildArgs += "--dry-run" }
    if ($SaveRaw)     { $buildArgs += "--save-raw" }
    & $Python "src/ingest/build_kg.py" @buildArgs
    if ($LASTEXITCODE -ne 0) { throw "build_kg.py 失败（退出码 $LASTEXITCODE）" }

    # 3. 自检（预览模式跳过）
    if (-Not $Preview) {
        & $Python "src/ingest/data_loader.py"
        if ($LASTEXITCODE -ne 0) { throw "data_loader.py 自检失败" }
    }

    Write-Host "[build_kg] 完成。" -ForegroundColor Green
    exit 0
}
finally {
    Pop-Location
}
