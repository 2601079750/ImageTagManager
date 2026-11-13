# 图片移除与恢复 / Removal and recovery

## 中文

- 单张或多选图片后，点击图库上方“移除图片 / 移除所选 N 张”，也可右键操作。Ctrl+A 只选择当前筛选结果。确认时冻结所选记录范围，不会扩大到全部图库。
- 所有移除操作只改变拾图中的管理状态，保留磁盘原图、文件名、全局标签和分类。尚未删除的移除记录保留图片标签关联。
- 左侧“已移除”支持搜索、标签筛选、大图预览、多选恢复及删除记录。单张详情显示移除时间；原图缺失可先重新关联或恢复后到“原图缺失”处理。
- 恢复所选图片保留现有标签，不恢复同目录的其他图片，也不自动开启该目录同步。已移除期间不能在图片详情中修改其标签；全局标签管理仍遵循原有规则，删除全局标签会删除对应关联。
- “删除记录”清除所选移除记录及其图片标签关联；原图和全局标签保留。操作后无法直接恢复，主动重新导入只能获得新记录。
- “自动删除记录”默认不启用，可选择 3、7、15、30 天；从每张图片最近一次移除的时间计算。开启或缩短周期时如有已到期记录，确认后立即清理。程序运行时约每分钟检查，关闭期间不会执行，下次启动后清理到期记录。恢复的图片不参与清理。
- 扫描排除规则独立保存；删除记录不会取消排除。启动检查、自动同步、手动扫描、自动路径恢复均尊重移除状态。排除按路径管理；在软件外另行改名或复制到新路径的文件，可能被识别为新图片。
- 主动重新导入已移除或已排除的范围时会要求确认；尚有记录的图片恢复原标签，已删除记录的图片无法恢复原标签关联。

## 文件夹管理

- “文件夹与路径管理”列出来源、图片库、被排除目录、同步状态，以及“图库 / 已移除”数量。
- “停止 / 恢复同步”控制该来源。停止时已有图片及标签保留；如另有启用的父目录或子目录来源，重叠范围仍可能同步，确认框会说明。
- “移除所选文件夹内图片”包含全部子目录，停用该范围内的来源并排除该范围。即使父目录仍同步，排除也生效。可通过“选择其他子文件夹移除”管理未单独导入的子目录。
- 恢复文件夹时选择：同时恢复同步，或仅恢复现有记录。仅恢复记录时，目录内未来新增的图片仍被排除；已删除的记录无法恢复。
- 图片库根路径继续保留。移除其中内容不会删除目录，也不会改变图片库位置。
- 原有重新定位、查找丢失图片及打开图片库入口保留。

## 升级与数据

已有安装：退出拾图后，在原安装目录替换 EXE，保留原 `portable.json`、`data` 和原图。不要用新空目录覆盖用户数据。独立解压到新目录后，如需连接已有数据，可在“设置 → 存储与备份 → 使用已有数据”选择原数据目录。

v0.3.4 首次打开旧数据库前保存 `data/backups/before-v0.3.4-*.sqlite3` 快照，再添加移除状态字段和扫描规则；原有图片 ID、标签和关联保持。新版 JSON 备份包含移除记录、排除规则、来源启用状态及清理周期，并兼容读取旧版 JSON 备份。回退旧版时应使用对应的升级前数据库副本；请先另存新版数据。

## English

Select one or more images and use Remove above the gallery or in its context menu. Ctrl+A selects the current filtered results. Removal preserves original files, global tags and categories. Image/tag links remain available until their removed records are deleted.

Removed supports search, tag filters, preview, batch restore and Delete records. Restoring selected images keeps their tags without restoring siblings or enabling folder sync. Missing originals can be relinked. Delete records permanently clears those records and their image/tag links, while retaining original files and scan exclusions.

Automatic record deletion is disabled by default. Choose 3, 7, 15 or 30 days from the removal time. Enabling a period confirms any immediately expired records. Checks run about once per minute while the app runs and after startup; restored images are never purged. Expired records cannot recover their previous tag links on reimport.

Folder and path management separates Stop syncing from Remove folder contents. Removal includes subfolders and takes precedence over overlapping parent/child sources. Folder restoration can restore records alone or also resume synchronization. The library root remains configured; originals and directories are preserved. Existing relink and missing-image recovery actions remain available.

Exclusion rules survive manual/automatic record deletion, backup, data migration and updates. They are path based: external renames or copies to new paths can appear as new images. Explicit reimport asks permission to restore existing records or allow previously excluded paths.

Update the EXE in the existing installation with the app closed, preserving portable.json, data and originals. An independent extraction can connect to the existing data directory through Settings > Storage and backup. Legacy v0.3 databases receive a pre-migration SQLite backup. v0.3.4 JSON backups include removed records, scan rules, source states and retention; legacy JSON backups remain readable. Use the matching pre-migration database when rolling back to older software.
