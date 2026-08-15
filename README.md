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
- **输出编码**：格式（MP4/MOV/MKV/AVI）、质量 CRF、编码预设、分辨率缩放
- **保留原音频**：输出视频完整保留原始音轨（无损复制；容器不兼容时自动转为 AAC）
- **一键定位**：输入/输出视频旁的「打开位置」按钮，直接在资源管理器打开并选中文件

### 4. 🚀 GPU 硬件加速（v0.1.3 起）
- **硬件编码**：自动探测并使用 NVIDIA NVENC / Intel QSV / AMD AMF / MediaFoundation / D3D12VA，无可用 GPU 时自动回退 CPU 编码（libx264）
- **双编码格式**：H.264 / HEVC（H.265）
- **硬件解码**：启用 `-hwaccel auto` 加速解码，驱动不兼容时自动回退软件解码
- **一键检测**：GUI 内可实时探测当前机器的可用硬件编码器
- 编码器/解码能力**零新增依赖**（复用内置静态 ffmpeg），打包体积不变

### 5. ⚡ 并行帧流水线（v0.1.3 起）
- **单视频导出提速**：读帧 / 合成 / 写入三阶段多线程解耦，1080p 实测约 **2.2 倍**提速
- **批量并行**：多个视频多进程同时处理，可设置并行数，批量吞吐大幅提升
- 并行输出与串行输出**字节级一致**，水印渲染效果完全不变

## 🚀 快速开始

### 方式一：双击启动（推荐）
双击项目根目录的 **`启动.bat`**：

- 首次运行会自动创建虚拟环境并安装依赖（含国内镜像自动重试）；
- 之后每次双击直接打开图形界面。

> 要求：本机已安装 **Python 3.10 或更高版本**，并已加入 PATH。
> 若启动失败，查看项目根目录 `gui_error.log` 定位原因。

### 方式二：命令行
```bat
.venv\Scripts\python.exe -m app.main
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
可用参数与默认值见 `app/models.py` 中的 `WatermarkConfig`；`--print-config` 可打印完整配置 JSON。
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
| 生成视频 | 单文件导出（后台线程，带进度条，自动并行流水线） |
| 批量处理 | 多文件队列 + **并行数**设置，统一参数批量生成 |

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
启动.bat                 # 双击启动器
requirements.txt         # 依赖清单
```

## 📦 打包为独立 exe（可选）

无需 Python 环境、双击即用的单文件版本：

```bat
.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
.venv\Scripts\pyinstaller.exe "video_watermark.spec" --noconfirm
```

- 产物：`dist\VideoWatermark.exe`（单文件、无控制台，约 86MB，已内置 ffmpeg 离线可用，含 GPU 硬件加速）
- 自检：运行 `dist\VideoWatermark.exe --selftest`，退出码 0 表示打包正常
- 首次启动解压较慢属正常现象（单文件模式）

## 🧪 测试与验证（9 套）

```bat
.venv\Scripts\python.exe scripts\smoke_test.py          rem 轨迹/渲染逻辑
.venv\Scripts\python.exe scripts\verify_step1.py        rem 像素级成品验证
.venv\Scripts\python.exe scripts\verify_hw.py           rem GPU 硬件加速专项
.venv\Scripts\python.exe scripts\verify_pipeline.py     rem 并行流水线专项
.venv\Scripts\python.exe scripts\verify_time_range.py   rem 时间范围验证
.venv\Scripts\python.exe scripts\verify_audio.py        rem 音频保留验证
.venv\Scripts\python.exe scripts\gui_smoke.py           rem GUI 离屏冒烟
.venv\Scripts\python.exe scripts\gui_export_test.py     rem GUI 导出端到端
.venv\Scripts\python.exe scripts\step3_export_test.py   rem 编码参数端到端
.venv\Scripts\python.exe scripts\step4_batch_test.py    rem 批量端到端（含并行）
.venv\Scripts\python.exe scripts\step1_demo.py          rem 生成 4 种样例输出
```

> GPU 硬件加速说明：`verify_hw.py` 会实测本机可用编码器（NVENC/QSV/AMF/MF）逐一编码验证；无 GPU 的机器会自动跳过并回退 CPU 路径，不影响功能。

## ❓ 常见问题

- **首次处理较慢 / 报 ffmpeg 相关错误**：程序首次使用会自动下载内置 ffmpeg 静态二进制（约 30MB，需联网一次），之后缓存于用户目录。
- **中文字体不显示**：确保系统装有中文字体（Windows 自带微软雅黑/黑体/宋体等），软件会自动选择。
- **输出尺寸与原视频不同**：为保证编码兼容性，奇数尺寸会取整到偶数；一般视频不受影响。
- **移动水印在亮背景上看不见**：建议给文字水印加描边（GUI「文字设置 → 描边宽度」），或选择与背景对比强的颜色。
- **硬件编码没有更快？**：本软件瓶颈在 CPU 侧帧合成/管道而非编码器，GPU 编码主要用于**降低 CPU 负载**与 HEVC 输出；真正的墙钟提速来自内置的并行帧流水线（默认已启用）。若希望更快的单文件导出，可确认「硬件编码」为自动并适当调高 `--parallel`。
- **提示"硬件编码器不可用"**：说明当前机器无对应 GPU 或驱动缺失，软件已自动回退 CPU 编码（libx264），不影响使用；可在「输出设置 → 检测」查看可用编码器。

## 📄 许可

本项目基于 [Unlicense](LICENSE) 发布，可自由使用与分发。
