# Stormy-Pulse: 音乐可视化播放器

一款可视化的桌面音乐播放器，支持本地音频播放、高精度音频特征分析与实时可视化特效渲染（由 CPU 渲染），并支持视频导出。

具体运行效果可参考：
- **横屏演示**: [Bilibili 视频链接](https://www.bilibili.com/video/BV17FD1BmEhe/?spm_id_from=333.1387.homepage.video_card.click&vd_source=4b4b0bce46607b3376213560ca269073)
- **竖屏演示**: [抖音视频链接](https://www.douyin.com/user/self?from_tab_name=live&modal_id=7626718341222141225)

---

## 🚀 快速开始

本项目使用 [uv](https://github.com/astral-sh/uv) 进行高效的依赖管理与项目打包。新用户只需以下三步即可直接运行：

### 1. 克隆仓库
```bash
git clone <repository_url>
cd Stormy-Pulse
```

### 2. 同步并安装依赖
在项目根目录下，执行 `uv sync` 会自动创建虚拟环境，并将当前项目以开发模式打包安装：
```bash
uv sync
```

### 3. 运行程序
同步完成后，使用下述命令一键运行播放器：
```bash
uv run music-visualizer
```
*(注：你也可以通过运行 `uv run main.py` 或 `uv run run.py` 来启动项目)*

---

## 📦 特征缓存说明

首次播放某首歌曲时，程序会在后台完成完整的音频特征分析（L1~L5 特征，耗时与歌曲长度相关）；分析结果会持久化缓存，再次播放同一首歌时直接读取缓存，加载几乎瞬时完成（CPU / GPU 两种渲染后端共用同一份分析缓存）。

- **缓存位置**：项目根目录下的 `cache/` 文件夹（文件名形如 `v4_<hash>.npz`），方便直接查看和管理
- **识别方式**：按「文件名 + 文件大小 + 修改时间」识别歌曲，歌曲文件发生变化后会自动重新分析
- **清空缓存**：直接删除 `cache/` 文件夹即可，下次播放时自动重建
- **旧版本迁移**：早期版本缓存存放于 `~/.music_visualizer/cache`，启动时会自动迁移到项目目录并清理旧位置
