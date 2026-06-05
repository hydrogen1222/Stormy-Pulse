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
