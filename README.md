# 视频水印工具

一款桌面图形界面的视频水印软件：支持**全屏平铺水印**（文字/图片，可旋转角度）与**移动水印**（6 种预设轨迹），并提供预览、批量处理与输出编码控制。

## ✨ 功能总览

### 1. 全屏平铺水印（静态，铺满整个画面）
- **文字水印**：多行文本（支持换行与自动换行）、字体（自动枚举系统中文字体）、字号、颜色、透明度、描边
- **图片水印**：缩放比例、透明度、圆角遮罩
- **角度控制**：整幅瓦片旋转 -180°~180°（如 30°/45° 斜铺防盗水印）
- **平铺参数**：横/纵向间距、整体偏移

### 2. 移动水印（动态轨迹）
- 6 种预设轨迹：**水平往返 / 垂直往返 / 对角线往返 / 圆周运动 / 8 字形 / 正弦波漂移**
- 可调：速度、水印大小、透明度、随时间自转
- 支持文字与图片两种水印源

### 3. 增强功能
- **出现时间范围**：只在指定时间段显示水印
- **实时预览**：预览任意时刻的水印效果 + 移动轨迹示意图
- **批量处理**：多视频一次生成，逐文件进度
- **详细帧级进度（v0.2.0 起）**：单文件导出与批量处理均显示逐帧进度（第 X/Y 帧 + 百分比 + 处理速度 + 预计剩余时间）
- **平滑帧速率（v0.2.2 起）**：单文件导出与批量处理均以滑动窗口平滑显示处理速率与预计剩余时间，不再闪烁跳变
- **界面增强（v0.2.2 起）**：左侧参数面板加宽（不再出现横向滚动条）；窗口标题栏与任务栏显示软件图标（打包 exe 同样生效）
- **输出编码**：格式（MP4/MOV/MKV/AVI）、质量 CRF、编码预设、分辨率缩放
- **保留原音频**：输出视频完整保留原始音轨（无损复制；容器不兼容时自动转为 AAC）
- **一键定位**：输入/输出视频旁的「打开位置」按钮，直接在资源管理器打开并选中文件

### 4. 🚀 GPU 硬件加速（v0.2.0-rc 起）
- **硬件编码**：自动探测并使用 NVIDIA NVENC / Intel QSV / AMD AMF / MediaFoundation / D3D12VA，无可用 GPU 时自动回退 CPU 编码（libx264）
- **双编码格式**：H.264 / HEVC（H.265）
- **硬件解码**：启用 `-hwaccel auto` 加速解码，驱动不兼容时自动回退软件解码
- **一键检测**：GUI 内可实时探测当前机器的可用硬件编码器
- 编码器/解码能力**零新增依赖**（复用内置静态 ffmpeg），打包体积不变
- **Linux GPU 支持（v0.3.1 起）**：Linux 版内置 ffmpeg 不含硬件编码器，程序会**自动检测系统 ffmpeg**（如 `apt install ffmpeg`），若其具备硬件编码器则自动切换使用（NVIDIA/Intel 显卡开箱即得 GPU 加速）；也可用 `--ffmpeg` 手动指定任意二进制（如 BtbN 构建）。无系统 ffmpeg 或无 GPU 时仍回退 CPU，零依赖不受影响

### 5. ⚡ 并行帧流水线（v0.2.0-rc 起）
- **单视频导出提速**：读帧 / 合成 / 写入三阶段多线程解耦，1080p 实测约 **2.2 倍**提速
- **批量并行**：多个视频多进程同时处理，可设置并行数，批量吞吐大幅提升
- 并行输出与串行输出**字节级一致**，水印渲染效果完全不变

### 6. 🐧 跨平台支持（v0.3.0 起）
- **Windows 与 Linux 双平台支持**：核心引擎（渲染 / 合成 / 编码 / 音频）行为一致
- **字体自动适配**：Windows 使用微软雅黑 / 黑体 / 宋体等；Linux 自动递归枚举系统字体（含子目录），默认选用思源黑体（Noto Sans CJK）/ 文泉驿等常见中文字体
- **一键启动脚本**：Windows `启动.bat`、Linux/macOS `启动.sh`（自动建 venv、装依赖、缺库提示）
- **CI 双平台构建**：GitHub Actions 自动构建 Windows exe 与 Linux 单文件可执行文件（推 tag 即发布）
- **ffmpeg 二进制解析层（v0.3.1 起）**：优先用内置二进制（零依赖）；Linux 上内置版无硬件编码器时自动探测并切换到带硬件编码器的系统 ffmpeg；支持 `--ffmpeg` 显式指定与环境变量 `VIDEO_WATERMARK_FFMPEG` 覆盖

## 🚀 快速开始

### 方式一：双击启动（推荐）

- **Windows**：双击项目根目录的 **`启动.bat`**
- **Linux / macOS**：终端运行 **`./启动.sh`**（或双击执行）

首次运行会自动创建虚拟环境并安装依赖（官方源失败自动换国内镜像），之后每次启动直接打开图形界面。

> 要求：本机已安装 **Python 3.10 或更高版本**。
> Linux GUI 需要系统图形库（多数桌面发行版自带）；若报 "could not load the Qt platform plugin xcb"，按启动脚本的提示安装 `libxcb-cursor0` 等库即可。
> Windows 若启动失败，查看项目根目录 `gui_error.log` 定位原因。

### 方式二：命令行
```bat
.venv\Scripts\python.exe -m app.main
```
```bash
# Linux / macOS
.venv/bin/python -m app.main
```

### 方式三：命令行无界面（脚本化 / 批量）
```bat
rem 平铺文字水印（30° 斜铺、多行）
.venv\Scripts\python.exe -m app.cli --input in.mp4 --output out.mp4 ^
    --mode tiled --text "机密文件\n请勿外传" --angle 30

rem 移动图片水印（8 字形轨迹 + 自转）
.venv\Scripts\python.exe -m app.cli --input in.mp4 --output out.mp4 ^
    --mode motion --kind image --image logo.png --trajectory figure8 ^
    --set motion_rotate=true

rem 通用参数覆盖与编码控制
.venv\Scripts\python.exe -m app.cli --input in.mp4 --output out.mp4 ^
    --set start_sec=1.5 --set end_sec=10 --crf 20 --preset slow --scale 0.5

rem GPU 硬件加速（默认 auto 自动选可用硬件编码器，无 GPU 回退 CPU）
.venv\Scripts\python.exe -m app.cli --input in.mp4 --output out.mp4 ^
    --mode tiled --text "机密" --hw-encoder auto --hw-codec h264
.venv\Scripts\python.exe -m app.cli --input in.mp4 --output out.mp4 ^
    --hw-encoder nvenc --hw-codec hevc          rem 指定 NVIDIA + HEVC
.venv\Scripts\python.exe -m app.cli --input in.mp4 --output out.mp4 ^
    --hw-encoder none --no-hw-decode           rem 强制纯 CPU / 关闭硬解
.venv\Scripts\python.exe -m app.cli --input in.mp4 --output out.mp4 ^
    --parallel 4                               rem 并行流水线 worker 数
```
> Linux / macOS 下将 `.venv\Scripts\python.exe` 换为 `.venv/bin/python`，行继续符 `^` 换为 `\`，注释 `rem` 换为 `#`。

可用参数与默认值见 `app/models.py` 中的 `WatermarkConfig`；`--print-config` 可打印完整配置 JSON。
GPU 相关：`--hw-encoder auto|none|nvenc|qsv|amf|d3d12va|mf`、`--hw-codec h264|hevc`、`--no-hw-decode`、`--parallel N`。
ffmpeg 二进制：`--ffmpeg PATH|internal`（Linux 上内置版无硬件编码器时默认自动探测系统 ffmpeg；`PATH` 显式指定任意二进制，`internal` 强制用内置版；也可设环境变量 `VIDEO_WATERMARK_FFMPEG`，GUI 用户可用后者）。
GPU 相关：`--hw-encoder auto|none|nvenc|qsv|amf|d3d12va|mf`、`--hw-codec h264|hevc`、`--no-hw-decode`、`--parallel N`。

## 🖱 界面使用说明

| 区域 | 说明 |
|------|------|
| 视频文件 | 选择输入/输出，自动读取分辨率/帧率/时长 |
| 模式 | 平铺水印 / 移动水印（自动切换参数面板） |
| 来源 | 文字 / 图片（自动切换设置区） |
| 文字设置 | 多行内容、字体、字号、颜色、透明度、描边 |
| 图片设置 | 图片路径、缩放、透明度、圆角 |
| 平铺参数 | 角度、行/列间距、偏移 |
| 移动参数 | 6 种轨迹、速度、大小、透明度、自转 |
| 时间范围 | 水印出现/消失时间 |
| 输出设置 | 格式、质量 CRF、编码预设、分辨率缩放、**硬件编码/视频编码/硬件解码**（含「检测」按钮） |
| 预览 | 「预览帧」看效果、「轨迹示意」看移动路径 |
| 生成视频 | 单文件导出（后台线程，进度条显示**帧数/百分比/平滑速率/剩余时间**，自动并行流水线） |
| 批量处理 | 多文件队列 + **并行数**设置，统一参数批量生成；文件进度条 + **当前文件帧级进度（含速率/剩余时间）** |

## 📁 项目结构

```
app/
├─ main.py               # 程序入口（GUI）
├─ cli.py                # 命令行入口
├─ models.py             # 水印配置数据类（参数定义）
├─ ui/
│  ├─ main_window.py     # 主窗口
│  └─ batch_dialog.py    # 批量处理对话框
└─ core/
   ├─ watermark.py       # 文字/图片渲染、平铺瓦片
   ├─ motion.py          # 6 种轨迹计算
   ├─ compositor.py      # 逐帧合成（含时间范围、自转）
   ├─ hwaccel.py         # GPU 硬件编码器探测、参数映射、硬件解码
   ├─ encoder.py         # ffmpeg 读写与编码（含并行帧流水线）
   └─ preview.py         # 预览帧渲染、轨迹示意图
scripts/                 # 演示与测试脚本
outputs/                 # 生成的样例视频（可作验收）
启动.bat                 # Windows 双击启动器
启动.sh                  # Linux/macOS 启动器
.github/workflows/       # CI：双平台自动构建与发布
requirements.txt         # 依赖清单
```

## 📦 打包为独立可执行文件（可选）

无需 Python 环境、双击即用的单文件版本：

```bat
rem Windows
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
.venv\Scripts\pyinstaller.exe "video_watermark.spec" --noconfirm
```
```bash
# Linux / macOS
.venv/bin/pip install pyinstaller
.venv/bin/pyinstaller "video_watermark.spec" --noconfirm
```

- 产物：Windows `dist\VideoWatermark.exe` / Linux `dist/VideoWatermark`（单文件，约 86~108MB，已内置 ffmpeg 离线可用）
- 自检：运行产物加 `--selftest`，退出码 0 表示打包正常；自检包含**打包环境下进程池可用性验证**（批量并行的子进程不会重新弹窗、能正常执行）
- 首次启动解压较慢属正常现象（单文件模式）
- **批量并行 ≥2 在打包 exe 下正常**：入口已加 `multiprocessing.freeze_support()`（v0.2.0 修复，此前子进程会重复弹出主窗口）
- **处理过程不再闪命令窗（v0.2.1）**：所有 ffmpeg / explorer 子进程统一走隐藏窗口封装（`CREATE_NO_WINDOW`）
- **CI 自动构建（v0.3.0 起）**：推送 `v*` 标签或手动触发后，GitHub Actions 自动构建 Windows 与 Linux 双平台产物并发布 Release（见 `.github/workflows/build.yml`）

## 🧪 测试与验证（9 套）

```bat
rem Windows（PowerShell）
.venv\Scripts\python.exe scripts\smoke_test.py          rem 轨迹/渲染逻辑
.venv\Scripts\python.exe scripts\verify_step1.py        rem 像素级成品验证
.venv\Scripts\python.exe scripts\verify_hw.py           rem GPU 硬件加速专项
.venv\Scripts\python.exe scripts\verify_pipeline.py     rem 并行流水线专项
.venv\Scripts\python.exe scripts\verify_time_range.py   rem 时间范围验证
.venv\Scripts\python.exe scripts\verify_audio.py        rem 音频保留验证
.venv\Scripts\python.exe scripts\gui_smoke.py           rem GUI 离屏冒烟
.venv\Scripts\python.exe scripts\gui_export_test.py     rem GUI 导出端到端（含帧级进度断言）
.venv\Scripts\python.exe scripts\step3_export_test.py   rem 编码参数端到端
.venv\Scripts\python.exe scripts\step4_batch_test.py    rem 批量端到端（并行+串行，含帧级进度断言）
.venv\Scripts\python.exe scripts\step1_demo.py          rem 生成 4 种样例输出
```
```bash
# Linux / macOS
.venv/bin/python scripts/smoke_test.py
.venv/bin/python scripts/verify_step1.py
.venv/bin/python scripts/verify_hw.py
.venv/bin/python scripts/verify_pipeline.py
.venv/bin/python scripts/verify_time_range.py
.venv/bin/python scripts/verify_audio.py
.venv/bin/python scripts/gui_smoke.py            # 需 QT_QPA_PLATFORM=offscreen（无显示环境时）
.venv/bin/python scripts/gui_export_test.py      # 同上
.venv/bin/python scripts/step3_export_test.py    # 同上
.venv/bin/python scripts/step4_batch_test.py     # 同上
.venv/bin/python scripts/step1_demo.py
```

> GPU 硬件加速说明：`verify_hw.py` 会实测本机可用编码器（NVENC/QSV/AMF/MF）逐一编码验证；无 GPU 的机器会自动跳过并回退 CPU 路径，不影响功能。Linux 上内置 ffmpeg 无硬件编码器，`verify_hw.py` / `verify_pipeline.py` 中涉及 GPU 编码的断言会失败，属平台预期（其余路径全部通过）。

## ❓ 常见问题

- **首次处理较慢 / 报 ffmpeg 相关错误**：程序首次使用会自动下载内置 ffmpeg 静态二进制（约 30MB，需联网一次），之后缓存于用户目录。
- **生成视频时会一闪而过黑色命令窗**：v0.2.1 起已修复——所有 ffmpeg/explorer 子进程统一以隐藏窗口方式启动，处理全程不再弹命令窗。
- **中文字体不显示**：确保系统装有中文字体（Windows 自带微软雅黑/黑体/宋体等），软件会自动选择。
- **输出尺寸与原视频不同**：为保证编码兼容性，奇数尺寸会取整到偶数；一般视频不受影响。
- **移动水印在亮背景上看不见**：建议给文字水印加描边（GUI「文字设置 → 描边宽度」），或选择与背景对比强的颜色。
- **硬件编码没有更快？**：本软件瓶颈在 CPU 侧帧合成/管道而非编码器，GPU 编码主要用于**降低 CPU 负载**与 HEVC 输出；真正的墙钟提速来自内置的并行帧流水线（默认已启用）。若希望更快的单文件导出，可确认「硬件编码」为自动并适当调高 `--parallel`。
- **提示"硬件编码器不可用"**：说明当前机器无对应 GPU 或驱动缺失，软件已自动回退 CPU 编码（libx264），不影响使用；可在「输出设置 → 检测」查看可用编码器。
- **Linux 报 "could not load the Qt platform plugin xcb"**：缺系统图形库。Debian/Ubuntu：`sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1`；Fedora：`sudo dnf install xcb-util-cursor libxkbcommon-x11`。无显示环境（服务器）可用 `QT_QPA_PLATFORM=offscreen` 跑 CLI / 自检。
- **Linux 如何启用 GPU 硬件编码（v0.3.1 起）**：安装系统 ffmpeg（`sudo apt install ffmpeg`，发行版默认含 NVENC/QSV 编译支持），程序检测到其具备硬件编码器后会**自动切换**使用；WSL2 同样适用（需 NVIDIA 驱动直通）。也可 `--ffmpeg /路径/ffmpeg` 指定任意二进制（如 [BtbN 构建](https://github.com/BtbN/FFmpeg-Builds/releases)，内置 NVENC/QSV/VAAPI）。AMD 显卡在 Linux 上需 VAAPI 滤镜链，暂未支持，会回退 CPU。
- **Linux 下没有系统 ffmpeg 会怎样**：继续使用内置静态二进制，全部功能正常（零依赖），仅无 GPU 硬件编码（回退 libx264）。
- **Linux 字体下拉为空 / 中文变方框**：确保安装了中文字体（如 `fonts-noto-cjk`、`fonts-wqy-microhei`），软件会自动递归枚举并默认选用可用的中文字体。

## 📄 许可

本项目基于 [Unlicense](LICENSE) 发布，可自由使用与分发。
