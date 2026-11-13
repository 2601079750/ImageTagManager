# 下载、安装与升级 / Download, install and upgrade

## 中文

- **直接解压版**：下载 `ImageTagManager-0.3.4-Windows-x64.zip`，完整解压后运行一级目录中的 `ImageTagManager.exe`。包含源码和中英文使用说明，不需要 Python。
- **安装版**：下载 `ImageTagManager-0.3.4-Windows-x64-Setup.exe`。支持中英文安装向导、安装目录选择、开始菜单快捷方式、可选桌面快捷方式及 Windows 卸载入口。应用界面仍为简体中文。
- 默认按当前用户安装到 `%LOCALAPPDATA%\Programs\ImageTagManager`，无需管理员权限，也可选择其他可写目录。两个包使用同一个程序，版本均为 v0.3.4。
- 两个包均不含用户数据库、标签记录、图片库、个人背景、日志或 `portable.json`。首次启动需要选择图片库，数据默认写入程序旁的 `data`。
- **已有用户升级**：先退出主窗口和托盘实例，并备份。安装版请选择原程序目录覆盖安装；解压版可只替换原程序目录的 `ImageTagManager.exe`。两种方式均须保留原有 `portable.json`、`data` 和外部图片库。新版会在旧数据库升级前创建快照。
- 在新目录安装会被视作另一份程序配置，不会自动连接其他解压目录的数据。若要更换程序位置，退出程序后连同 `portable.json` 和 `data` 移动，或在“设置 → 存储与备份”选择已有数据目录；同时保留原图片库路径。
- 安装覆盖和卸载均不删除运行时生成的用户数据、定位配置、备份或原图。卸载后目录非空是正常现象；如要清理，请先确认已完成独立备份。
- 当前安装包没有代码签名。可用同页 `.sha256` 校验下载完整性；SHA-256 不等于发布者签名。
- v0.3.4 的更新检查仍可能受到 GitHub API 限流影响；出现该提示时可等待恢复或从项目 Releases 手动下载。本次仅增加发布形式，未修改更新检查机制。

## English

- **Portable**: download `ImageTagManager-0.3.4-Windows-x64.zip`, extract everything and run `ImageTagManager.exe` from the main folder. Source and bilingual guides are included; Python is not required.
- **Installer**: download `ImageTagManager-0.3.4-Windows-x64-Setup.exe`. It provides Chinese/English setup, destination selection, a Start menu shortcut, an optional desktop shortcut and Windows uninstall registration. The application UI remains Simplified Chinese.
- Installation is per-user, defaults to `%LOCALAPPDATA%\Programs\ImageTagManager`, and requires no administrator rights. You may select another writable directory. Both packages run the same v0.3.4 executable.
- Neither package includes user databases, tag records, collections, personal backgrounds, logs or `portable.json`. First launch asks for a library; data defaults to the adjacent `data` folder.
- **Upgrade**: exit the main and tray instances and back up first. Install into the existing application folder, or replace only its EXE using the portable ZIP. Preserve existing `portable.json`, `data` and external image libraries. Legacy databases receive a safety snapshot before schema upgrades.
- Installing in a different folder does not automatically connect another portable copy's catalogue. To relocate, move `portable.json` and `data` with the closed program, or open the existing data folder under Storage & Backup. Keep the original library location accessible.
- Reinstallation and uninstall preserve runtime user data, configuration, backups and originals. A nonempty folder may remain after uninstall; back up before manually cleaning it.
- The installer is unsigned. Published `.sha256` files verify download integrity and are not publisher signatures.
- Optional GitHub update checks may still encounter API rate limits in v0.3.4. Wait or download from Releases manually. This packaging update does not change the updater.
