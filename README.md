# 拾图 · ImageTagManager

Windows 图片标签管理工具，图库功能完全离线运行，联网检查更新为可选功能。

**最新版本：v0.3.4** · [下载 / Downloads](https://github.com/2601079750/ImageTagManager/releases/tag/v0.3.4) · [中文使用说明](V0.3.4/README.md) · [English guide](V0.3.4/README.en.md)

## 下载与运行

- **直接解压版**：`ImageTagManager-0.3.4-Windows-x64.zip`。完整解压后运行主文件夹中的 `ImageTagManager.exe`，无需 Python；包含源码和中英文说明。
- **安装版**：`ImageTagManager-0.3.4-Windows-x64-Setup.exe`。支持中英文安装向导、自选目录、开始菜单和可选桌面快捷方式，以及 Windows 卸载入口；默认按当前用户安装，无需管理员权限。应用界面为简体中文。
- 两种发布包均不含个人数据库、标签记录、图片库、背景、日志或 `portable.json`。首次启动需选择图片库；应用数据默认保存于程序旁的 `data`，可在设置中迁移。
- **升级前退出主窗口与托盘实例并备份。** 安装版请选择原程序目录；解压版可仅替换原目录的 EXE。保留 `portable.json`、`data` 和外部图片库。卸载保留运行时用户数据。更换安装目录不会自动连接另一份解压版的数据。
- 下载页提供 SHA-256 校验文件；安装包暂未代码签名。详细说明见 [安装与升级](V0.3.4/docs/INSTALLATION.md)。

## 功能

- 引用、复制或移动导入图片和多个文件夹，默认包含子目录，不改原图名称。
- 自定义标签类别、已有标签复用、批量打标签、重命名和类别管理。
- 多标签“全部 / 任一”筛选，文件名和标签搜索，按修改时间、分辨率、文件大小等排序。
- 缩略图动画、大图缩放平移、动图预览；支持常见图片格式。
- 单张 / 批量移除、文件夹管理、恢复原有标签；移除保留磁盘原图。
- “已移除”支持手动删除记录，以及可选的 3 / 7 / 15 / 30 天自动清理；扫描排除规则保留。
- 路径恢复、标签备份与恢复、自定义数据位置、可调同步间隔、单实例和系统托盘。
- 浅色、深色和自定义背景主题，整窗背景、主题色、取色及实时预览；自定义颜色需点击“应用颜色”保存。
- 可选 GitHub 更新检查、下载校验、重启更新与数据位置核验。当前接口限流时请等待或从 Releases 手动下载。

## 版本目录

- **V0.3.4**：当前发布源码、测试、文档和打包脚本。
- **V0.3 / V0.2 / V0.1**：历史版本按独立目录保留，归档文件不修改。先前已发布的版本可从 Releases 下载。
- 发布附件位于 GitHub Releases；源码仓库不保存用户数据库、图片库或本地对话记录。

## English

An offline Windows image manager with grouped tags, batch tagging, All/Any filtering, search, previews, path recovery and backups. Optional online updates are disabled by default.

**Latest: v0.3.4** · [Downloads and bilingual release notes](https://github.com/2601079750/ImageTagManager/releases/tag/v0.3.4) · [English guide](V0.3.4/README.en.md)

Choose the **portable ZIP** to extract and run, or the **per-user installer** for destination selection, shortcuts and uninstall support. Both contain the same application, require no Python and exclude personal collections, catalogues and configuration. The application UI is Simplified Chinese; setup and documentation support Chinese and English.

This release adds single/batch removal, folder management, tag-preserving recovery, optional timed cleanup and custom-color preview with explicit Apply. It also includes the v0.3 storage, tray, theme and UI improvements since v0.2. Acrylic has been removed for text clarity.

Back up and exit all instances before upgrading. Install into the existing application directory, or replace its EXE from the ZIP. Keep `portable.json`, `data` and image libraries. Reinstall and uninstall retain runtime user files. A different installation folder does not automatically attach another portable catalogue. See [installation and upgrade instructions](V0.3.4/docs/INSTALLATION.md).
