# 拾图 · ImageTagManager 0.2

## 中文

- 新增统一设置界面，分为外观、同步、备份与恢复；主题与自动同步开关保存后在重启时沿用。
- 标签选中行使用更清晰的蓝紫色，浅色与深色主题分别适配；切换主题保留标签选择。
- 筛选文字简化为“全部”和“任一”，分别满足全部选中标签或至少一个选中标签。
- 换上原创二次元应用图标，EXE、窗口及任务栏一致；程序直接位于 `V0.2/ImageTagManager.exe`，版本保持 0.2。
- 版本目录独立保存，V0.1 完整归档，V0.2 包含本次迭代。
- 下拉栏屏蔽滚轮误触，保留点击和键盘选择。
- 缩略图平滑放大/缩小、圆角卡片与抗锯齿选中图标；保留动图悬停播放。
- 右侧调整为创建标签、图片已有标签、选择已有标签，支持批量移除。
- 新标签管理页：批量删除标签、移动类别、搜索、新建和重命名；类别可以自定义、重命名、删除。
- 白色、黑色、跟随系统主题，可保存选择并自动响应系统主题变化。

完整解压附件后运行 ImageTagManager.exe，无需 Python。标签数据库沿用原位置；标签备份不包含原图。当前界面为简体中文。非空类别删除前需转移标签，同名冲突会取消整个操作。

## English

- Unified Settings with Appearance, Sync and Backup/Restore tabs. Theme and automatic-sync preferences persist across restarts.
- More distinct blue-violet tag selection for both themes, with selections retained when switching themes.
- Filter labels simplified to All (全部) and Any (任一), preserving every-tag and at-least-one-tag matching.
- Original anime-style icon for the executable, windows and taskbar. Run `V0.2/ImageTagManager.exe` directly from the version folder. Version remains 0.2.
- Separate version folders preserve V0.1; V0.2 contains this iteration.
- Wheel-safe comboboxes with click and keyboard selection.
- Smooth thumbnail hover growth/shrink, rounded cards and antialiased selection badges; animated hover playback remains supported.
- Inspector reordered into tag creation, attached tags, and existing tags, with bulk removal.
- Tag Manager adds bulk deletion, category moves, search, creation and renaming. Categories can be customized, renamed and deleted.
- Persistent White, Black and Follow system themes, with automatic system-theme detection.

Extract the entire ZIP and run ImageTagManager.exe. Python is not required. Existing catalogue data remains in its original location. Tag backups exclude original images. The UI is Simplified Chinese. Deleting a nonempty category requires transferring its tags; name conflicts cancel the entire operation.
