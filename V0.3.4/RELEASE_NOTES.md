# 拾图 v0.3.4 / Shitu v0.3.4

## 中文

- 同时提供直接解压版和按当前用户安装的安装版；安装版可选择目录、创建快捷方式，覆盖安装及卸载保留用户数据。发布包均不含个人图库、数据库或定位配置。详见 docs/INSTALLATION.md。
- 自定义主题色改为临时实时预览，点击“应用颜色”才保存；关闭、Esc、关闭设置或退出时放弃未应用的颜色，自动保存不会写入预览色。
- 新增图片单张 / 批量移除、右键与图库操作入口，保留原图。
- 新增“已移除”页面，支持原标签恢复、重新关联、手动删除记录，以及按移除时间 3 / 7 / 15 / 30 天自动清理（默认关闭）。
- 文件夹管理区分停止同步与移除目录内容，包含子目录，处理父子来源重叠；恢复可选择是否同时同步。
- 删除记录只清除管理记录和图片标签关联，保留原图、全局标签及扫描排除规则；自动扫描不会重新导入被排除路径。
- 显式重新导入已移除范围时提示恢复，尚未删除的记录保留原标签。
- 备份、迁移和更新保留移除状态、排除规则、清理设置；兼容旧版备份并在旧数据库升级前创建快照。
- 延续 v0.3 的其他功能、外观和主题切换优化。详细操作见 docs/REMOVAL.md。

## English

- Portable ZIP and per-user installer are both available. Setup supports destination selection and shortcuts; reinstall/uninstall preserve user data. Neither package contains personal collections, databases or local configuration. See docs/INSTALLATION.md.
- Custom colors now preview immediately and save only with Apply color. Closing, Escape, closing Settings or exiting discards an unconfirmed color; background saves retain the committed color.
- Added single/batch image removal with gallery and context-menu actions; originals are preserved.
- Added Removed with tag-preserving restore, relinking, manual record deletion and optional 3/7/15/30-day cleanup based on removal time (off by default).
- Folder management separates pause sync from remove contents, handles nested/overlapping sources and offers optional sync on restore.
- Record deletion retains original files, global tags and independent scan exclusions, preventing automatic reimport at those paths.
- Explicit reimport confirms recovery of existing records and their tags.
- Backup, migration and updates preserve removed records, scan rules and retention. Legacy backups remain readable; old databases receive a pre-upgrade snapshot.
- Other v0.3 features and appearance behavior are retained. See docs/REMOVAL.md.

---

# 拾图 v0.3 / Shitu v0.3

## 中文

- 修复设置页签切换瞬间闪白：新页签映射时及时绘制背景和控件显示层，防止父容器覆盖背景；保留原生清晰文字。
- 修复白色按钮文字与面板底色共用色值时，切换深色主题可能残留白色面板的问题。
- 优化主题色与设置页签切换：换色不再重新筛选图库；页签仅刷新设置窗口，复用背景与布局缓存。
- 外观即时预览，连续调整合并保存；关闭、退出、迁移和更新前保存最终设置。页签高亮与主题色选中环增加轻量过渡，并遵循系统动画偏好。
- 保持中性背景稳定，让主题色集中用于操作和选中状态；文字继续使用清晰的原生绘制。
- 移除 Acrylic 磨砂效果、相关开关和系统材质绘制，文字统一采用原生绘制；已有材质偏好自动忽略，不影响标签、图片库及其他设置。
- 保留浅色、深色、自定义背景三个主题、主题色与实时预览；自定义背景的半透明标签区域继续可用。
- 三个主题色主按钮的文字统一水平、垂直居中，保留平滑的圆形主题色选项。
- 修复三主题换色与下拉菜单焦点异常，主题和页签批次刷新，减少中间白底。

- 修复切换设置页签时窗口短暂消失的问题，刷新期间保持窗口显示与任务栏状态。
- 统一主窗口与设置页的透明样式：仅导入图片/文件夹、创建并添加到所选图片、添加所选标签三个主操作保留主题色底，选中导航/页签/标签高亮。
- 新增 15/30 秒、1/5/10 分钟与自定义同步间隔，默认 1 分钟；显示最近同步时间。
- 默认程序旁 data 数据目录，可迁移或切换已有数据；首次选择图片库并持久保存，支持旧版数据迁移。
- 单实例提示与窗口唤回；新增托盘、关闭询问、不再提醒与关闭行为设置。
- 设置扩展为外观、同步与后台、存储与备份、更新、关于五页。
- 自定义背景下去除设置页大块白底，以细实线分隔；三个标签区域改为半透明背景，保留原生选择/滚动/键盘操作，增强辅助文字及选中态对比度。
- 自定义背景使用整窗统一的半透明可读性衬底，避免标题/说明处的局部白块；文字独立清晰绘制。
- 背景支持覆盖、填充、居中、拉伸、自由；自由模式可缩放并调整水平/垂直位置。
- 主题色适用于所有主题；四个圆形候选色与圆形 + 自定义入口，支持颜色选择器和屏幕取色。
- 同步下拉移除“自定义”，输入“自定义间隔”即清空预设并自动应用有效值。
- 新增 GitHub 手动更新、可选启动检查（默认关闭）、通知气泡、下载校验、辅助进程替换及启动数据校验回退。
- 更新只替换 EXE，保留 portable.json 与用户数据；更新前备份数据库和程序，保留回滚副本。
- 关于页：v0.3、项目主页、Issue、反馈邮箱 yh.gao0520@qq.com、系统信息复制。
- 窗口标题与界面版本号统一添加 v 前缀。

v0.2 用户需手动下载一次 v0.3。首次启动检测到旧数据时可迁移，原目录保留；标签与原图片库沿用。请完整解压，保留 portable.json 与 data。

## English

- Fixed white flashes when switching Settings tabs by preparing background/control surfaces as pages map and clipping container repaint around children; native text stays crisp.
- Fixed panels retaining a white background in Dark mode when their previous color matched unchanged primary-button text.
- Faster theme-color and settings-tab switching: color changes no longer refilter the gallery, while tab changes refresh only Settings and reuse background/layout caches.
- Live appearance previews with coalesced settings saves; final values are flushed before closing, exit, migration and updates. Lightweight tab and swatch selection transitions respect system animation preferences.
- Stable neutral backgrounds keep theme colors focused on actions and selections, with crisp native text.
- Removed Acrylic, its settings toggle and system material rendering. All themes now use native text. Legacy material preferences are ignored without affecting tags, library records or other settings.
- Retained Light, Dark and Custom Background themes, theme colors and live previews, including translucent tag panels on custom backgrounds.
- Centered primary-button labels horizontally and vertically, with smooth circular theme-color swatches.
- Fixed theme-color and dropdown-focus errors, with batched theme/tab refreshes to reduce white flashes.

- Fixed settings tabs briefly disappearing during repaint; window visibility and taskbar state now remain intact.
- Unified transparent controls across the main window and settings. Only Import Images/Folders, Create and Apply, and Apply Selected Tags retain a theme-color fill; selected navigation, tabs and tags stay highlighted.
- Configurable 15/30-second, 1/5/10-minute and custom sync intervals; default one minute, with last-sync status.
- Portable adjacent data storage, verified migration, existing-catalogue switching, first-run library selection and legacy-data migration.
- Single-instance activation, system tray, close prompt and remembered close behavior.
- Five settings pages: Appearance, Sync & Background, Storage & Backup, Updates, About.
- Custom Background settings use thin outlines instead of large white fills. Three translucent tag areas retain native selection, scrolling and keyboard controls, with improved text and selection contrast.
- A shared full-window readability veil replaces local white label patches on custom backgrounds; text remains crisp and opaque.
- Cover, Fit, Center, Stretch and Free background layouts; Free supports zoom and positioning.
- Theme colors for every theme, four circular suggestions, and a circular + custom picker/eyedropper.
- Five sync presets; custom input clears the preset and automatically applies valid intervals.
- Optional GitHub update checks (automatic checks off by default), notification bubbles, verified downloads and restart updates.
- Database snapshot, executable rollback and post-update verification of data/library locations and image/tag associations.
- About page with project/Issue links, feedback email, version and system information.
- Consistent v prefix for version displays.

v0.2 users must download v0.3 manually once. Legacy migration retains the original data folder and library. Keep portable.json and data when moving or updating the application.
