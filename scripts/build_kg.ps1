# One-click KG build pipeline (B): chunk -> LLM extract -> load into Neo4j
# Usage:
#   powershell -File scripts\build_kg.ps1            # full build
#   powershell -File scripts\build_kg.ps1 -Limit 20  # trial run on first 20 chunks
#   powershell -File scripts\build_kg.ps1 -Resume    # resume from checkpoint
param(
    [int]$Limit = 0,
    [switch]$Resume
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

# 1. chunk raw novels into data/interim/chunks.json
python src\ingest\corpus.py
if ($LASTEXITCODE -ne 0) { throw "corpus.py failed" }

# 2. LLM extraction + Neo4j loading (era field supported from day one)
$buildArgs = @()
if ($Limit -gt 0) { $buildArgs += "--limit"; $buildArgs += $Limit }
if ($Resume)      { $buildArgs += "--resume" }
python src\ingest\build_kg.py @buildArgs
if ($LASTEXITCODE -ne 0) { throw "build_kg.py failed" }

# 3. sanity check: read back chunks and graph stats
python src\ingest\data_loader.py
if ($LASTEXITCODE -ne 0) { throw "data_loader.py sanity check failed" }

Write-Host "[build_kg] Done." -ForegroundColor Green
