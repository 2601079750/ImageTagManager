# 拾图 · ImageTagManager 0.1

## 中文

首个公开版本：完全离线的 Windows 图片标签管理工具，适合按画师、角色、场景等标签整理本地收藏。当前应用界面为简体中文，仓库提供中英文说明。

### 功能

- 多文件夹与多图片导入，包含子文件夹；选择引用原位置、复制或移动到 Windows“图片”目录中的专用图片库。
- 分组标签、复用已有标签、批量添加/移除、仅选中图片更换标签，以及全局重命名。
- 多标签交集/并集筛选，文件名/标签搜索，按名称、修改时间、分辨率、文件大小和导入时间升降序排序。
- 常见图片格式、大图预览缩放与拖动、缩略图悬停放大、动图角标与悬停播放。
- 启动检查、每 15 秒自动同步、手动扫描；内容指纹恢复移动/改名图片，多个候选由用户确认。
- 独立标签数据库、JSON 备份与恢复；恢复前自动备份当前标签库。

### 下载与使用

下载附件 **ImageTagManager-0.1-Windows-x64.zip**，完整解压后双击主文件夹中的 **ImageTagManager.exe**。无需安装 Python，无需账号，离线运行。附件包含 EXE、源码、构建脚本、测试与中英文说明。

首次打开后点击“导入图片 / 文件夹”，建议先使用默认的“复制到图片库”。选中图片后在右侧创建/选择标签，再从左侧选择标签筛选。详细说明见仓库 `README.md`。

### 数据与限制

标签与缓存位于 `%LOCALAPPDATA%\ImageTagManager`；默认原图库位于 Windows“图片”目录下的 `ImageTagManager 图片库`。**标签备份不包含原图，请另外备份原图。** 选择“移动”会在复制并验证成功后删除源图片。

0.1 暂不提供标签合并、重复图片识别、AI 标签、云同步和复杂交并集混合表达式。已通过 23 项核心测试、原生界面流程测试与当前 Windows 11 x64 环境下的 EXE 验证；尚未在其他电脑或实际千张高分辨率收藏中验证性能。

## English

First public release of an offline Windows desktop application for organizing local image collections with artist, character, scene, and custom tags. The current UI is in Simplified Chinese; Chinese and English documentation are included.

### Features

- Import multiple folders/images recursively; reference existing files or copy/move them into a managed library under Windows Pictures.
- Grouped tags, existing-tag reuse, bulk add/remove, selected-image tag replacement, and global tag renaming.
- Intersection/union tag filtering, filename/tag search, and ascending/descending sorting by filename, modification time, resolution, file size, and import time.
- Common image formats, large previews with zoom and pan, hover enlargement, animation badges, and hover playback.
- Startup checks, automatic scans every 15 seconds, manual rescan, and fingerprint-based recovery of renamed/moved files with manual selection for ambiguous matches.
- A separate tag database and JSON backup/restore with an automatic safety backup before restore.

### Download and use

Download **ImageTagManager-0.1-Windows-x64.zip**, extract the entire archive, and launch **ImageTagManager.exe** inside the main folder. No Python installation or account is required. The ZIP includes the EXE, source, build script, tests, and bilingual documentation.

Click **导入图片 / 文件夹** (Import images/folders), preferably using the default Copy to library option for your first trial. Select images, create/apply tags on the right, and select filters on the left. See `README.en.md` for the full guide.

### Data and limitations

Tags/cache are stored in `%LOCALAPPDATA%\ImageTagManager`; the default managed library is `ImageTagManager 图片库` inside Windows Pictures. **Tag backups do not contain original images. Back up originals separately.** Move mode deletes source images after copying and verification.

Version 0.1 does not include tag merging, duplicate detection, AI tagging, cloud sync, or nested mixed AND/OR expressions. Validation includes 23 core tests, native UI flows, and EXE checks on the current Windows 11 x64 computer. Other computers and initial-import performance on real collections of thousands of high-resolution images have not been tested.
