# 拾图应用图标 / Shitu application icon

原创二次元猫耳角色，以紫色照片卡片和薄荷绿标签表达图片收藏与分类。圆角外侧透明，无文字，适配浅色与深色桌面。

- `app-icon.svg`：可编辑矢量原图。
- `app-icon.png`：1024 × 1024、带透明通道的图像。
- `app-icon.ico`：Windows 图标，包含 16、20、24、32、40、48、64、128、256 像素。

制作方式：内置图像生成服务调用失败后，改为原创矢量路径绘制；使用 `python tools/create_icon.py` 和 Pillow 超采样渲染，不使用外部 API。该脚本会重新生成本目录的三个图标文件。

设计要求：为离线图片标签管理程序设计原创二次元图标；猫耳角色搭配照片与标签，清晰轮廓、简化细节，紫色与薄荷绿配色，无文字与水印，保留透明外边缘。

Original anime mascot artwork with a photo card and mint tag. `app-icon.svg` is the editable vector source; the PNG has transparent outer corners, and the ICO contains nine sizes from 16 to 256 pixels. Created with original vector paths and supersampled Pillow rendering after the built-in image-generation service failed. Regenerate with `python tools/create_icon.py`; no external API is used.
