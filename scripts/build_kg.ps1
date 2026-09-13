# One-click KG build pipeline (B): chunk -> LLM extract -> load into Neo4j
# Usage:
#   powershell -File scripts\build_kg.ps1                            # full build (legacy: chunks.json / 射雕)
#   powershell -File scripts\build_kg.ps1 -Book 神雕侠侣              # build a specific book (phase 2)
#   powershell -File scripts\build_kg.ps1 -Book 神雕侠侣 -Limit 20    # trial run on first 20 chunks
#   powershell -File scripts\build_kg.ps1 -Book 神雕侠侣 -Resume      # resume from checkpoint
param(
    [string]$Book = "",
    [int]$Limit = 0,
    [switch]$Resume,
    [string]$Python = "python"   # 用 PATH 里的 python（组长 Anaconda 环境）
)

$ErrorActionPreference = "Stop"
# Force UTF-8 so Chinese text / pytest.ini comments work on any Windows code page
$env:PYTHONUTF8 = "1"
# Make src/ importable no matter which directory this script is invoked from
$repoRoot = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = Join-Path $repoRoot "src"

# 0. check .env exists (keys must not be committed to git)
if (-Not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[build_kg] Created .env from template. Edit it and fill in NEO4J_PASSWORD / LLM_TOKEN, then re-run." -ForegroundColor Yellow
        exit 1
    } else {
        throw "Missing .env and .env.example"
    }
}

# 1. chunk raw novels: -Book 指定单书，否则处理 data/source/ 下所有 txt（每书一个 chunks_<书名>.json）
if ($Book -ne "") {
    & $Python "src\ingest\corpus.py" --source "data\source\$Book.txt"
} else {
    & $Python "src\ingest\corpus.py"
}
if ($LASTEXITCODE -ne 0) { throw "corpus.py failed" }

# 2. LLM extraction + Neo4j loading (era injected per-book; checkpoint per-book)
$buildArgs = @()
if ($Book -ne "")      { $buildArgs += "--book"; $buildArgs += $Book }
if ($Limit -gt 0)      { $buildArgs += "--limit"; $buildArgs += $Limit }
if ($Resume)           { $buildArgs += "--resume" }
& $Python "src\ingest\build_kg.py" @buildArgs
if ($LASTEXITCODE -ne 0) { throw "build_kg.py failed" }

# 3. sanity check: read back chunks and graph stats
& $Python "src\ingest\data_loader.py"
if ($LASTEXITCODE -ne 0) { throw "data_loader.py sanity check failed" }

Write-Host "[build_kg] Done." -ForegroundColor Green
