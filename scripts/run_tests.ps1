# run_tests.ps1
# 一键运行所有测试

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "GraphRAG Test Suite" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 设置输出编码，避免中文乱码
$env:PYTHONIOENCODING = "utf-8"

# 运行 pytest
python -m pytest -v --tb=short

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Test run completed" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
