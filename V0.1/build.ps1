param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not $SkipTests) {
    python -m unittest discover -s tests -p test_core.py -v
    if ($LASTEXITCODE -ne 0) { throw '核心测试失败，已停止打包。' }
    python tests/smoke_ui.py
    if ($LASTEXITCODE -ne 0) { throw '界面测试失败，已停止打包。' }
}

python -m PyInstaller --noconfirm --clean --windowed --onefile --name ImageTagManager --collect-all PIL --exclude-module numpy --exclude-module pandas --exclude-module matplotlib main.py
if ($LASTEXITCODE -ne 0) { throw '打包失败。' }
Write-Host "已生成：$PSScriptRoot\dist\ImageTagManager.exe"
