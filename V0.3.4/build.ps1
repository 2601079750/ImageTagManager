param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not $SkipTests) {
    python -m unittest discover -s tests -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw '核心测试失败，已停止打包。' }
    python tests/smoke_removal.py
    if ($LASTEXITCODE -ne 0) { throw '图片移除与恢复界面测试失败，已停止打包。' }
    python tests/smoke_ui.py
    if ($LASTEXITCODE -ne 0) { throw '界面测试失败，已停止打包。' }
    python tests/smoke_glass.py
    if ($LASTEXITCODE -ne 0) { throw '半透明界面测试失败，已停止打包。' }
    python tests/smoke_color_dialog.py
    if ($LASTEXITCODE -ne 0) { throw '自定义主题色预览与保存测试失败，已停止打包。' }
    python tests/smoke_theme.py
    if ($LASTEXITCODE -ne 0) { throw '主题交互回归测试失败，已停止打包。' }
    python tests/smoke_native.py
    if ($LASTEXITCODE -ne 0) { throw '托盘和窗口测试失败，已停止打包。' }
    python tests/smoke_tab_paint.py
    if ($LASTEXITCODE -ne 0) { throw '设置页首帧绘制测试失败，已停止打包。' }
    python tests/profile_switching.py --output .test-output/switching-after.json --check
    if ($LASTEXITCODE -ne 0) { throw '主题切换性能回归检查失败，已停止打包。' }
}

python -m PyInstaller --noconfirm --clean --windowed --onefile --name ImageTagManager --distpath . --icon assets/app-icon.ico --add-data "assets;assets" --add-data "RELEASE_NOTES.md;." --collect-all PIL --exclude-module numpy --exclude-module pandas --exclude-module matplotlib main.py
if ($LASTEXITCODE -ne 0) { throw '打包失败。' }
Write-Host "已生成：$PSScriptRoot\ImageTagManager.exe"
