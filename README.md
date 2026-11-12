# 拾图 · ImageTagManager

完全离线的 Windows 图片标签管理工具。每个版本独立放在对应文件夹中，历史版本保留。

当前发布：[v0.2 程序下载与中英文更新说明](https://github.com/2601079750/ImageTagManager/releases/tag/v0.2)。完整解压 ZIP 后运行主文件夹中的 `ImageTagManager.exe`，无需安装 Python。GitHub 仓库保存源码和文档，EXE 与程序压缩包从 Releases 下载。

- **V0.2**：当前迭代，新增统一设置界面、三种主题、清晰的标签选中配色、平滑悬停动画、圆角卡片和完整标签/类别管理。使用说明见 [中文](V0.2/README.md) / [English](V0.2/README.en.md)。
- **V0.1**：原版归档，保留源码、构建产物和原始发布压缩包。

运行新版：完整解压 `V0.2/release/ImageTagManager-0.2-Windows-x64.zip`，运行其中的 `ImageTagManager.exe`；也可直接运行 `V0.2/ImageTagManager.exe`。V0.2 采用原创二次元图标，EXE 直接放在版本目录下。

后续版本均新建 `V<版本号>` 目录，复制上一版本的源码和文档后迭代，构建及发布包写入新版本目录。已归档版本不作修改。不要复制真实图片库、标签数据库和测试缓存到发布包。

程序的标签数据库位于 `%LOCALAPPDATA%\ImageTagManager`，独立于版本目录；归档程序文件不等于备份个人图库。V0.2 可以继续读取 V0.1 的标签库；使用新版删除分类后，重新运行 V0.1 可能重新补入默认分类。

Offline Windows image tag manager. Each version has its own `V<version>` folder. Keep archived versions unchanged; build and package new versions inside their own folders. Application data is stored separately from version folders.

Download the Windows app and read the bilingual changelog on the [v0.2 release page](https://github.com/2601079750/ImageTagManager/releases/tag/v0.2). Extract the entire ZIP and run `ImageTagManager.exe` from its main folder; Python is not required. Read the [English guide](V0.2/README.en.md) for features, usage and build instructions. The repository stores source and documentation; executable downloads are provided through Releases.
