# 更新日志

本项目所有显著变更记录于此。格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本（`vX.Y.Z`，发版即打 tag，不覆盖旧标签）。

## [Unreleased]

### 新增（v0.4.0 进行中）
- **GUI ffmpeg 二进制来源设置**：输出设置区可选「自动（推荐）/ 内置二进制 / 自定义路径」，QSettings 持久化；切换即时生效于下次生成/检测
- **「检测」结果增强**：同时显示当前实际使用的 ffmpeg 二进制与来源；Linux 未检测到硬件编码器时提示安装系统 ffmpeg
- **Linux AppImage 产物**（批次 C 进行中）

### 计划中
- VAAPI 硬件编码（AMD Linux）——见 README「已知限制」

## [v0.3.2] - 2026-09-06

### 新增
- **ffmpeg 二进制解析层（`app/core/ffbin.py`）**：统一决定全项目使用的 ffmpeg，经 imageio-ffmpeg 官方覆写点 `IMAGEIO_FFMPEG_EXE` 生效，编码/探测调用零改动
- **Linux GPU 硬件编码**：Linux 版内置 ffmpeg 无硬件编码器时自动探测系统 ffmpeg 并切换（NVENC/QSV 可用），无系统 ffmpeg 时维持内置零依赖
- CLI `--ffmpeg PATH|internal` 显式指定二进制（或强制内置）；GUI 用户可设环境变量 `VIDEO_WATERMARK_FFMPEG`
- 新增测试 `verify_ffbin.py`（解析层 7 项边界用例），测试体系增至 **10 套**

### 变更
- `verify_hw.py` / `verify_pipeline.py` 在无硬件编码器环境下对 GPU 断言自动 SKIP，测试结论随环境自适应
- Windows 真机全套回归 + exe 自检通过（WSL2 + RTX 4050 实测 NVENC 全链路）

### 修复
- ffbin 子进程继承场景下显式指定被镜像环境变量压过的优先级问题

## [v0.3.0] - 2026-09-06

> v0.3.1 未发布，无内容损失。

### 新增
- **Linux 平台支持**：核心引擎（渲染/合成/编码/音频保留）跨平台行为一致，CI 双平台构建与自动发布（`.github/workflows/build.yml`，推 `v*` 标签触发）
- **字体自动适配**：Linux 递归枚举系统字体（含子目录），默认选用思源黑体（Noto Sans CJK）/ 文泉驿等中文字体；Windows 行为不变
- **`启动.sh`**：Linux/macOS 启动器（自动建 venv、缺 ensurepip 时 get-pip 引导、装依赖自动切换清华镜像、缺系统图形库提示）

### 变更
- 硬件编码器探测缓存路径 XDG 化（Linux/macOS `~/.config/VideoWatermark/`）

## [v0.2.2] - 2026-08-16

### 变更
- 左侧参数面板加宽（400px → 480px），消除横向滚动条
- 窗口标题栏与任务栏显示软件图标（打包 exe 同样生效）
- 帧速率显示改用约 2 秒滑动窗口平滑，消除闪烁跳变；批量处理同步显示速率

## [v0.2.1] - 2026-08-15

### 修复
- 生成视频时一闪而过的黑色命令窗：所有 ffmpeg / explorer 子进程统一经 `app/core/subproc.py` 封装（Windows 附加 `CREATE_NO_WINDOW`）隐藏启动

## [v0.2.0] - 2026-08-15

### 修复
- 批量并行（≥2）在打包 exe 下只弹额外主窗口：入口增加 `multiprocessing.freeze_support()`；`--selftest` 新增进程池可用性验证
- 单文件导出与批量处理增加帧级进度（第 X/Y 帧 + 百分比 + 速率 + 预计剩余时间），批量并行经 Manager 队列跨进程回传

### 注
- v0.2.0-rc 为预发布版本

## [v0.1.3] - 2026-08-15

### 新增
- GPU 硬件加速（NVENC/QSV/AMF/MF 自动探测 + 回退 + 硬解）与并行帧流水线提速（串行/并行字节级一致）

## [v0.1.2] - 2026-08-15

### 新增
- 输入/输出视频「打开位置」按钮（资源管理器定位文件）；应用图标 `icon.ico`（多尺寸）

## [v0.1.1] - 2026-08-15

### 修复
- 转换后丢失音频：编码后用内置 ffmpeg 无损合并原音频流（`-c:a copy`），容器不兼容时回退 AAC

## [v0.1.0] - 2026-08-15

### 新增
- 首个可用版本（Windows 64 位单文件版）：全屏平铺文字/图片水印（角度/多行）、移动水印（6 种轨迹）、实时预览、批量处理、命令行入口、独立 exe 打包

[Unreleased]: https://github.com/illagerCPR/video-watermark/compare/v0.3.2...HEAD
[v0.3.2]: https://github.com/illagerCPR/video-watermark/compare/v0.3.0...v0.3.2
[v0.3.0]: https://github.com/illagerCPR/video-watermark/compare/v0.2.2...v0.3.0
[v0.2.2]: https://github.com/illagerCPR/video-watermark/compare/v0.2.1...v0.2.2
[v0.2.1]: https://github.com/illagerCPR/video-watermark/compare/v0.2.0...v0.2.1
[v0.2.0]: https://github.com/illagerCPR/video-watermark/compare/v0.2.0-rc...v0.2.0
[v0.2.0-rc]: https://github.com/illagerCPR/video-watermark/releases/tag/v0.2.0-rc
[v0.1.3]: https://github.com/illagerCPR/video-watermark/compare/v0.1.2...v0.1.3
[v0.1.2]: https://github.com/illagerCPR/video-watermark/compare/v0.1.1...v0.1.2
[v0.1.1]: https://github.com/illagerCPR/video-watermark/compare/v0.1.0...v0.1.1
[v0.1.0]: https://github.com/illagerCPR/video-watermark/releases/tag/v0.1.0
