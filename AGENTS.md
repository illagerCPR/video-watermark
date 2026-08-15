# AGENTS.md

## 项目定位

Windows 桌面**视频水印**软件（PySide6 GUI + 命令行双入口）。核心引擎：Pillow 渲染水印瓦片/单元格，imageio-ffmpeg 内置静态 ffmpeg 逐帧解码/编码，无需系统安装 ffmpeg。用户主要面向中文，沟通用中文。

## 环境与安装

- 唯一可用的 Python 环境：项目根目录 `.venv/`（Python 3.14）。**勿创建新 venv 或全局 pip 安装**。
- 依赖见 `requirements.txt`：Pillow、imageio-ffmpeg、PySide6。
- pip 直连官方源在部分环境会挂（如 PySide6_Addons 大包），安装失败时用清华镜像：
  `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
- 本机**没有**系统 ffmpeg；一切 ffmpeg 调用必须经 `imageio_ffmpeg.get_ffmpeg_exe()` 获取内置二进制路径（打包时通过 `collect_data_files("imageio_ffmpeg")` 一并内置）。

## 入口

- GUI：项目根目录 `python -m app.main`（或双击 `启动.bat`，会自动建 venv+装依赖）。
- 命令行：`python -m app.cli --input in.mp4 --output out.mp4 [--mode tiled|motion] [--kind text|image] [--text|--image] [--angle] [--trajectory] [--set k=v] [--crf --preset --scale]`。
  - `--set k=v` 覆盖 `WatermarkConfig` 任意字段（可重复）；`--print-config` 打印完整配置 JSON。
- 打包自检：`dist\VideoWatermark.exe --selftest`（离屏建窗+编码验证，退出码 0 = 正常）。

## 核心架构（数据流）

- `app/models.py` — `WatermarkConfig` 单一配置 dataclass，所有参数在此定义；`config_to_json`/`json_to_config` 序列化。
- `app/core/watermark.py` — 渲染文字/图片单元格、旋转、平铺瓦片、字体枚举。
- `app/core/motion.py` — 6 种轨迹（horizontal/vertical/diagonal/circle/figure8/sine），`position_at()` 返回帧时刻水印左上角坐标。
- `app/core/compositor.py` — `WatermarkCompositor` 逐帧 `apply(frame_rgb, t)`，含时间范围门控、自转。
- `app/core/encoder.py` — `probe()` 解析分辨率/帧率/时长/是否有音频；`process()` 读帧→合成→编码输出→**合并音频**。
- `app/core/preview.py` — 单帧预览渲染、轨迹示意图。
- `app/ui/` — `main_window.py`（主窗口+RenderWorker QThread）、`batch_dialog.py`（批量处理）。

## 编码器关键陷阱（改这里必读）

- `imageio_ffmpeg.read_frames(path, pix_fmt="rgb24")` 产出为**生成器**，且**第一个产出是元数据 dict**，必须先 `next(gen)` 跳过再迭代帧字节。
- `write_frames(path, (w,h), pix_fmt_in=..., pix_fmt_out=..., fps=..., codec=..., macro_block_size=1, output_params=[...])` 返回**生成器**，必须先 `writer.send(None)` 启动，帧用 `writer.send(frame_bytes)`，结束 `writer.close()`（放 try/finally）。
- `macro_block_size=1` **必须保留**：默认 16 对齐会导致输出被内部二次缩放（如 640x360 → 368）拉伸变形。
- 输出尺寸只对齐到偶数（yuv420p 要求），不要强行 16 对齐。
- **音频保留**：`process()` 编码出的临时视频无音轨，之后用内置 ffmpeg `-map 0:v:0 -map 1:a:0 -c:a copy -shortest` 从原视频无损合并；容器不兼容时回退 `-c:a aac -b:a 192k`。输入无音频则直接改名收尾。修改此流程后务必跑 `scripts/verify_audio.py`。

## 验证与测试（7 套，全过再交付）

统一运行方式（PowerShell）：
`$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe scripts\<name>.py`

- `smoke_test.py` 轨迹坐标/文字图片渲染逻辑；`verify_step1.py` 像素级成品验证（水印差异 + 轨迹质心 vs `position_at`）；`gui_smoke.py` GUI 离屏冒烟；`gui_export_test.py`/`step3_export_test.py`/`step4_batch_test.py` 端到端导出/编码参数/批量；`verify_time_range.py` 时间范围；`verify_audio.py` 音频保留；`step1_demo.py` 生成样例输出到 `outputs/`。

测试怪癖：
- GUI 测试须设 `QT_QPA_PLATFORM=offscreen`，且 `win.show()` 后才能 `isVisible()` 为真。
- 像素验证比较用 `read_frames` 按**精确帧索引**读取（勿用 `-ss` 抽帧，会错位）；阈值：水印信号用 40，时间范围"无水印"判定用 120（重编码噪声 ~2000px 会干扰）。
- 文字水印白底看不见——验收/演示须设 `stroke_width>=2` 描边。
- PowerShell 下 Qt 字体警告写 stderr 会被当 exit code 1，**属误报**，看脚本内打印的 "全部通过" 判定。

## 打包与发布

- 构建：`.venv\Scripts\pyinstaller.exe video_watermark.spec --noconfirm`（onefile，产物 `dist\VideoWatermark.exe`，约 86MB）。**spec 文件已从中文名改名 `video_watermark.spec`，产物名固定英文 `VideoWatermark`，勿改回。**
- 重建前先 `Stop-Process -Name VideoWatermark -Force`（残留的 onefile 引导进程会锁 exe 导致 PermissionError）。
- GUI 子系统 exe 退出码：PowerShell 须用 `Start-Process -Wait -PassThru` 读 `$p.ExitCode`，`&`/`$LASTEXITCODE` 会得到空值。
- **构建产物与媒体不入库**：`dist/`、`build/`、`outputs/`、`*.mp4`、`*.png` 等均在 `.gitignore`。exe 通过 GitHub Releases 分发。
- 发布：`gh release create vX.Y.Z "dist\VideoWatermark.exe" --title "VideoWatermark vX.Y.Z" --notes "<说明>" --repo illagerCPR/video-watermark`。每次用户要求上传即新开一个递增版本号（不覆盖旧标签）。

## 协作约定

- 用户偏好**分步执行 + 每步确认**（"开始"/"继续"驱动）；涉及用户操作 GUI 的验证先说明步骤。
- 目标平台 Windows；保持双击启动可用（`启动.bat`）。
- 改动核心渲染/编码后，先跑 `smoke_test.py` + `verify_step1.py`，再做 GUI 冒烟与端到端；最后按需重建 exe + selftest + 提交推送。
