# VideoWatermark 项目信息（PROJ_INFO）

> 本文件为项目结构与能力快照，随版本维护；最新变更见 `CHANGELOG.md`。
> 当前版本：**v0.5.7** · 仓库：<https://github.com/illagerCPR/video-watermark> · 许可：Unlicense

## 一、项目定位

跨平台（Windows + Linux）**桌面视频水印工具**，一个引擎三种入口：图形界面（PySide6）、命令行（argparse，可脚本化/批量）、终端交互界面（Textual TUI）。核心卖点是**零系统依赖**：内置静态 ffmpeg，开箱即用；在有 GPU/系统 ffmpeg 的环境下又能自动升级为硬件编解码。

主语言 Python：应用层 `app/` 约 4900 行 + 测试脚本 `scripts/` 约 2000 行（合计约 6900 行）。

## 二、功能全景

### 1. 水印能力（单配置模型 `WatermarkConfig`，25 字段）

| 类别 | 内容 |
|---|---|
| 水印来源 | 文字（多行、字体自动选择、字号、RGB 颜色、不透明度、描边宽/色）或图片（缩放、不透明度、圆角） |
| 模式 | **平铺水印**（角度、水平/垂直间距、水平/垂直偏移）与**移动水印**（7 种轨迹，见下；速度、幅度、不透明度、随时间自转） |
| 时间范围 | 出现起始/结束秒（结束留空 = 直到结尾） |

**移动轨迹（7 种，`app/core/motion.py`）**：

| id | 名称 | 曲线 |
|---|---|---|
| `horizontal` | 水平往返 | 三角波 |
| `vertical` | 垂直往返 | 三角波 |
| `diagonal` | 对角线往返 | 三角波 |
| `circle` | 圆周运动 | 圆参数方程 |
| `figure8` | 8 字形（竖向） | 李萨如 x=sin(2a), y=sin(a) |
| `infinity` | ∞ 形（横向双环） | 李萨如 x=sin(a), y=sin(2a)（v0.5.5 起） |
| `sine` | 正弦波漂移 | 水平往返 + 纵向正弦 |

### 2. 编码与硬件加速

- 输出 MP4（推荐）/MKV/AVI；质量 CRF（0~51）、编码预设（ultrafast~veryslow）、分辨率缩放（0.1~2.0）
- 硬件**编码**：auto/none/NVENC/QSV/AMF/D3D12VA/MediaFoundation，H.264/HEVC；每个候选编码器做**极短样片实测**（不是只看名单），结果按二进制指纹缓存（`%APPDATA%` 或 `~/.config/VideoWatermark/hw_encoders.json`）
- 硬件**解码**：`-hwaccel auto` 自动协商，失败自动回退软解
- **并行帧流水线**：主线程读帧 → N worker 并行合成 → 保序写线程喂 ffmpeg（有界队列背压），串行/并行输出字节级一致
- **音频保留**：编码后从原视频无损合并音轨（`-c:a copy`，不兼容回退 AAC 192k）
- 导出过程：帧级进度、速率/ETA、**取消**（`ProcessCancelled`，临时文件零残留）；进度旁显示实际使用的编码器与解码方式（TUI 导出屏 / GUI 进度条，v0.5.4 起）

### 3. 三种入口

| 入口 | 启动方式 | 特点 |
|---|---|---|
| GUI | `启动.bat` / `启动.sh` / `python -m app.main` | 全功能表单 + 实时预览（帧/轨迹示意）+ 批量处理 + ffmpeg 二进制来源设置（QSettings）+ 「检测」按钮（编码器实测 + 解码器报告 + 当前二进制） |
| CLI | `python -m app.cli --input … --output … [--set k=v] [--print-config] …` | 全参数脚本化；`--set` 覆盖任意配置字段；启动时打印实际选用的 ffmpeg 及理由 |
| TUI | `python -m app.tui` / `--tui` / `启动-tui.bat` / `VideoWatermarkTUI.exe`（Win）/ `./启动.sh --tui` | Textual 全屏：字段标签表单、配置 JSON 加载/保存（Ctrl+S）、终端内半块像素预览（F5/F6）、检测硬件按钮、导出进度/取消（F7）、批量处理（F8，v0.5.6 起：文件/目录入队+并行数+帧级进度+取消）；Windows 打包版经控制台垫片独占键盘 |

## 三、架构（`app/` 模块与职责）

| 模块 | 行数 | 职责 |
|---|---|---|
| `ui/main_window.py` | ~950 | GUI 主窗口 + 后台导出线程（QThread）+ ffmpeg 来源设置 |
| `tui.py` | ~1010 | TUI 应用（带标签表单/校验/预览屏/导出屏/批量屏/硬件检测） |
| `ui/batch_dialog.py` | 361 | 批量处理 UI + Qt 信号桥接（执行逻辑在 core/batch.py，v0.5.6 起） |
| `core/batch.py` | 176 | **批量核心（GUI/TUI 共用，v0.5.6）**：scan_videos/plan_jobs/run_batch（串行+进程池有界并行+Manager 队列帧进度+取消） |
| `core/encoder.py` | 422 | probe/process：读帧→合成→编码→合并音频；并行流水线；取消 |
| `core/hwaccel.py` | ~450 | 编码器实测探测、编码参数映射、解码参数、解码器报告 |
| `main.py` | ~400 | 入口分发（GUI/TUI/selftest）、Windows 控制台附加、冻结环境清理 |
| `core/watermark.py` | 353 | 文字/图片单元格渲染、旋转、平铺瓦片、跨平台字体枚举 |
| `core/ffbin.py` | ~200 | **ffmpeg 二进制解析层**：显式指定 > 用户 IMAGEIO 覆写 > 自动（内置缺硬编时探测系统 ffmpeg 切换） |
| `cli.py` / `models.py` | 156/138 | 命令行分发 / 单一配置模型 + JSON 序列化 |
| `core/motion.py` | ~100 | 7 种轨迹 `position_at()` + 自转角度 |
| 其他 | — | `compositor.py`（逐帧合成+时间门控）、`preview.py`、`subproc.py`（隐藏窗口封装）、`tui_preview.py`（半块像素渲染）、`tui_shim.py`（Windows TUI 控制台垫片） |

## 四、外部依赖

### Python 运行依赖（`requirements.txt`，仅 4 个）

| 包 | 版本要求 | 用途 |
|---|---|---|
| Pillow | ≥12.0 | 图像渲染（文字/图片/旋转/透明度/合成） |
| imageio-ffmpeg | ≥0.6 | 随包静态 ffmpeg（解码+编码），免系统安装 |
| PySide6 | ≥6.11 | 桌面 GUI |
| textual | ≥8.0 | TUI 交互模式 |

### 运行时环境

- **Python ≥ 3.10**（源码运行；`启动.*` 自动建 venv 装依赖，Linux 缺 ensurepip 自动引导）
- **系统 ffmpeg（可选）**：不装也全功能可用（内置二进制）；装了且带硬件编码器则**自动切换**启用 GPU 编码
- **GPU 驱动（可选）**：NVIDIA（WSL2 需驱动直通）、Intel QSV、AMD AMF(Windows)
- **Linux GUI 系统库**：xcb 系（多数桌面自带）；**中文字体**（Noto CJK/文泉驿等，自动枚举）
- 首次安装依赖需联网（pip 拉取 Pillow/PySide6 等）；ffmpeg 静态二进制**随 imageio-ffmpeg 包自带**，运行阶段无需联网

### 构建 / 发布工具链

- **PyInstaller**（onefile 双产物：`VideoWatermark` GUI + `VideoWatermarkTUI` 控制台垫片）
- **appimagetool**（AppImage；无 FUSE 自动解包运行）
- **GitHub Actions**（windows-latest + ubuntu-22.04 矩阵；tag 触发自动构建 + 双平台 selftest + 发布）

### 运行时外部服务

无（不联网、无遥测、无更新检查）。

## 五、数据与目录约定

| 数据 | 路径 |
|---|---|
| 硬件探测缓存 | Windows `%APPDATA%/VideoWatermark/hw_encoders.json`；Linux `~/.config/VideoWatermark/`（键含二进制路径+大小+mtime，自动失效） |
| GUI 偏好 | QSettings（org/app = `VideoWatermark`；ffmpeg 来源模式与路径） |
| 启动错误日志 | 项目根 `gui_error.log` |
| 调试开关 | `VIDEO_WATERMARK_TUI_DEBUG=1`（TUI 控制台附加判定）、`VIDEO_WATERMARK_FFBIN_DEBUG=1`（ffmpeg 决策过程 → `/tmp/video_watermark_ffbin_debug.log`） |

## 六、质量保障（测试 12 套 + CI）

- `smoke_test`（7 种轨迹含 ∞ 横向取向专检 / 渲染）、`verify_ffbin`（二进制解析层）、`tui_test`（Pilot 无终端自动化，11 节：表单往返/校验/配置/预览屏/导出取消/布局回归/检测按钮/导出编码器显示）、`tui_batch_test`（TUI 批量专项，v0.5.6：core 层 scan_videos/plan_jobs/run_batch 取消语义 + Pilot 端到端串行/并行/取消/布局回归）、`verify_step1`（**像素级**成品验证：水印差异 + 轨迹质心对照）、`gui_smoke`（含检测布局回归）、`gui_export_test`/`step3_export_test`/`step4_batch_test`（端到端导出/编码参数/批量）、`verify_time_range`、`verify_audio`（音频保留）、`verify_hw`（GPU 专项，环境感知 SKIP）、`verify_pipeline`（串并字节级一致）
- CI：双平台构建后各跑 `--selftest`（离屏建窗 + 真实编码 + 进程池可用性），tag 触发自动发布

## 七、发布产物（v0.5.7）

| 产物 | 大小 | 说明 |
|---|---|---|
| `VideoWatermark-windows-x86_64.exe` | ~93MB | GUI/CLI/TUI 三合一（onefile，内置 ffmpeg） |
| `VideoWatermarkTUI-windows-x86_64.exe` | ~8MB | TUI 控制台垫片（与主程序同目录；解决 shell 不等待 GUI 程序抢键问题） |
| `VideoWatermark-linux-x86_64.tar.gz` | ~122MB | ELF 单文件 |
| `VideoWatermark-linux-x86_64.AppImage` | ~123MB | 免安装，无 FUSE 自动解包 |

**版本历史**（18 个发布）：v0.1.0~0.1.2（核心引擎与像素验证）→ v0.2.x（GUI、批量、进程池修复）→ v0.3.0（Linux 跨平台 + CI 双平台）→ v0.3.2（ffbin 解析层，Linux GPU 编码）→ v0.4.0（ffmpeg 来源设置、AppImage）→ v0.5.0（TUI 模式）→ v0.5.1（GUI/TUI 布局修复、Windows Terminal 支持）→ v0.5.2（TUI 键盘独占垫片）→ v0.5.3（解码器检测）→ v0.5.4（AppImage 库污染修复、TUI 字段标签/检测按钮/编码器显示）→ v0.5.5（∞ 形轨迹预设）→ v0.5.6（TUI 批量处理 F8、批量核心抽离 core/batch.py、README 全面核对）→ v0.5.7（批量完成消息带实际编码器、探测缓存原子写/空结果不落盘、报错附当前二进制来源）。

## 八、已知限制

1. **VAAPI 编码暂不支持**（AMD/Intel Linux）——回退 CPU 编码；硬件**解码**不受影响
2. Linux 硬解收益有限（管线为"解码后读回软件帧"，多数自动回退软解）；硬解加速主要在 Windows 生效
3. Windows 直接运行 `VideoWatermark.exe --tui` 会与终端抢键（GUI 程序不被 shell 等待）——须用 `VideoWatermarkTUI.exe` / `start /wait` / bat
4. TUI 建议终端宽度 ≥ 90 列；硬件探测结果依赖驱动安装（检测报告只列已编译项，实际以导出时自动协商为准）
