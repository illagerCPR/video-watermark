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
- 命令行：`python -m app.cli --input in.mp4 --output out.mp4 [--mode tiled|motion] [--kind text|image] [--text|--image] [--angle] [--trajectory] [--set k=v] [--crf --preset --scale] [--hw-encoder auto|none|nvenc|qsv|amf|d3d12va|mf] [--hw-codec h264|hevc] [--no-hw-decode]`。
  - `--set k=v` 覆盖 `WatermarkConfig` 任意字段（可重复）；`--print-config` 打印完整配置 JSON。
  - `--hw-encoder` 默认 `auto`（自动选可用硬件编码器，无 GPU 回退 libx264）；`--hw-codec` 仅硬件编码时生效；`--no-hw-decode` 禁用硬件解码（默认开 `-hwaccel auto`，失败自动回退软解）。
- 打包自检：`dist\VideoWatermark.exe --selftest`（离屏建窗+编码验证，退出码 0 = 正常）。

## 核心架构（数据流）

- `app/models.py` — `WatermarkConfig` 单一配置 dataclass，所有参数在此定义；`config_to_json`/`json_to_config` 序列化。
- `app/core/watermark.py` — 渲染文字/图片单元格、旋转、平铺瓦片、字体枚举。
- `app/core/motion.py` — 6 种轨迹（horizontal/vertical/diagonal/circle/figure8/sine），`position_at()` 返回帧时刻水印左上角坐标。
- `app/core/compositor.py` — `WatermarkCompositor` 逐帧 `apply(frame_rgb, t)`，含时间范围门控、自转。
- `app/core/encoder.py` — `probe()` 解析分辨率/帧率/时长/是否有音频；`process()` 读帧→合成→编码输出→**合并音频**。`process()` 支持**并行帧流水线**（`parallel` 参数：0=自动按 CPU 核数 2~4、1=串行、N=指定）：`_run_serial` 串行、`_run_pipelined` 多线程（主线程读帧 → N 个 worker 线程并行合成 → 独立写线程按帧序号保序喂给 ffmpeg，有界队列背压）。串行与并行输出**字节级一致**（合成逻辑相同、仅交付方式不同）。
- `app/core/preview.py` — 单帧预览渲染、轨迹示意图。
- `app/ui/` — `main_window.py`（主窗口+RenderWorker QThread）、`batch_dialog.py`（批量处理）。

## 编码器关键陷阱（改这里必读）

- `imageio_ffmpeg.read_frames(path, pix_fmt="rgb24")` 产出为**生成器**，且**第一个产出是元数据 dict**，必须先 `next(gen)` 跳过再迭代帧字节。
- `write_frames(path, (w,h), pix_fmt_in=..., pix_fmt_out=..., fps=..., codec=..., macro_block_size=1, output_params=[...])` 返回**生成器**，必须先 `writer.send(None)` 启动，帧用 `writer.send(frame_bytes)`，结束 `writer.close()`（放 try/finally）。
- `macro_block_size=1` **必须保留**：默认 16 对齐会导致输出被内部二次缩放（如 640x360 → 368）拉伸变形。
- 输出尺寸只对齐到偶数（yuv420p 要求），不要强行 16 对齐。
- **音频保留**：`process()` 编码出的临时视频无音轨，之后用内置 ffmpeg `-map 0:v:0 -map 1:a:0 -c:a copy -shortest` 从原视频无损合并；容器不兼容时回退 `-c:a aac -b:a 192k`。输入无音频则直接改名收尾。修改此流程后务必跑 `scripts/verify_audio.py`。

## GPU 硬件加速（改这里必读）

- `app/core/hwaccel.py` 统一负责硬件编码：`detect_encoders()`（对每个候选做极短样片实测编码，结果 `lru_cache`）、`resolve_encode()`（统一 CRF/预设 → 各家参数，回退 libx264）、`build_decode_input_params()`。
- 内置 ffmpeg v7.1 自带 `h264/hevc/av1_nvenc`、`h264/hevc_qsv`、`h264/hevc_amf`、`hevc_d3d12va`、`h264/hevc_mf`，**零新增依赖/二进制**；打包不受影响。
- `process(...)` 新增参数：`hw_encoder="auto"`（auto/none/nvenc/qsv/amf/d3d12va/mf）、`hw_codec="h264"`、`hw_decode=True`（`-hwaccel auto`，头部解析失败自动回退软解）。返回 dict 新增 `codec` 键。
- `write_frames(...)` 必须传 `quality=None`：否则非 libx264 编码器会被追加 `-qscale:v`（旧代码隐式叠加 `-crf 25` 只是被后置参数覆盖）。
- 显式指定不可用编码器会 `raise RuntimeError`（不静默回退）；`auto` 才静默回退 libx264。
- 本机（RTX 4050 + Intel UHD）实测：`nvenc(h264/hevc/av1)`、`qsv(h264/hevc)`、`mf(h264)` 可用；QSV 会提示 `yuv420p→nv12` 自动选择，属无害信息。
- **确定性像素测试（`step1_demo.py`/`step4_acceptance.py`/`verify_audio.py`）固定 `hw_encoder="none", hw_decode=False`**，否则压缩噪声变化会让阈值判定不稳；GPU 路径由 `scripts/verify_hw.py` 专项覆盖。

## 验证与测试（9 套，全过再交付）

统一运行方式（PowerShell）：
`$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe scripts\<name>.py`

- `smoke_test.py` 轨迹坐标/文字图片渲染逻辑；`verify_step1.py` 像素级成品验证（水印差异 + 轨迹质心 vs `position_at`）；`gui_smoke.py` GUI 离屏冒烟；`gui_export_test.py`/`step3_export_test.py`/`step4_batch_test.py` 端到端导出/编码参数/批量；`verify_time_range.py` 时间范围；`verify_audio.py` 音频保留；`verify_hw.py` 硬件加速专项（探测 + 各硬件编码器实跑 + 回退 + 硬解 + 音频）；`verify_pipeline.py` 并行流水线专项（串行/并行字节级一致 + GPU/移动/硬解组合）；`step1_demo.py` 生成样例输出到 `outputs/`。

测试怪癖：
- GUI 测试须设 `QT_QPA_PLATFORM=offscreen`，且 `win.show()` 后才能 `isVisible()` 为真。
- 像素验证比较用 `read_frames` 按**精确帧索引**读取（勿用 `-ss` 抽帧，会错位）；阈值：水印信号用 40，时间范围"无水印"判定用 120（重编码噪声 ~2000px 会干扰）。
- 文字水印白底看不见——验收/演示须设 `stroke_width>=2` 描边。
- PowerShell 下 Qt 字体警告写 stderr 会被当 exit code 1，**属误报**，看脚本内打印的 "全部通过" 判定。
- **批量并行用 `ProcessPoolExecutor`（Windows spawn）**：任何会被进程池子进程导入的脚本/入口必须带 `if __name__ == "__main__":` 保护，否则子进程会重执行顶层代码递归（`step4_batch_test.py` 已按此改造）。

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
- **每个功能完成后必须同步更新 `README.md`**：新增/变更的功能点、CLI 参数、GUI 控件、测试清单、常见问题都要反映到文档，再交付（提交/发布）。README 与实现脱节视为未完成。
