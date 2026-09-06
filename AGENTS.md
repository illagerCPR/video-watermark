# AGENTS.md

## 项目定位

跨平台桌面**视频水印**软件（v0.3.0 起 Windows + Linux，PySide6 GUI + 命令行双入口）。核心引擎：Pillow 渲染水印瓦片/单元格，imageio-ffmpeg 内置静态 ffmpeg 逐帧解码/编码，无需系统安装 ffmpeg。用户主要面向中文，沟通用中文。

## 环境与安装

- 唯一可用的 Python 环境：项目根目录 `.venv/`。**勿创建新 venv 或全局 pip 安装**。
- 依赖见 `requirements.txt`：Pillow、imageio-ffmpeg、PySide6。
- pip 直连官方源在部分环境会挂（如 PySide6_Addons 大包），安装失败时用清华镜像：
  `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`。
- ffmpeg 二进制经 `app/core/ffbin.py` 统一解析（默认内置静态二进制，Linux 可自动/显式切换系统 ffmpeg，见核心架构）；打包时内置二进制通过 `collect_data_files("imageio_ffmpeg")` 一并内置，自检的 `ffbin.bundled_exe()` 独立验证打包完整性。
- **Linux 适配（v0.3.0）**：Linux 上若缺 ensurepip，`启动.sh` 会自动回退 `--without-pip` + `get-pip.py` 引导；字体层已支持 Linux（递归枚举 + 思源黑体/文泉驿候选，见 `watermark.py`）；GUI 缺 xcb 库时报错须提示装系统库（`libxcb-cursor0` 等）。

## 入口

- GUI：项目根目录 `python -m app.main`（Windows 双击 `启动.bat`、Linux/macOS 运行 `./启动.sh`，均会自动建 venv+装依赖）。
- **TUI（v0.5.0）**：`python -m app.tui`、`python -m app.cli --tui`、`./启动.sh --tui`（Linux）、`启动-tui.bat`（Windows）。Textual 全屏界面：全字段表单 + 配置 JSON 往返 + 半块像素预览（F5/F6）+ 导出进度/取消（F7）。按键 F5/F6/F7/Ctrl+S/Esc/Ctrl+Q。Windows 打包版 TUI 入口（v0.5.2）：**`VideoWatermarkTUI.exe`**（控制台子系统垫片，拉起同目录 `VideoWatermark.exe --tui` 并等待）——cmd/PowerShell 不等待 GUI 程序、shell 会继续读控制台输入与 TUI 抢键，垫片使 shell 阻塞等待、TUI 独占键盘；`VideoWatermark.exe --tui` 仍可直接运行（祖先链 `AttachConsole` 附加宿主终端），但按键会与 shell 抢。`_setup_tui_console()` 沿祖先链逐个 `AttachConsole(pid)`（`ATTACH_PARENT_PROCESS` 会打到 PyInstaller onefile 的无控制台引导器上，必然失败），成功后 `SetStdHandle` 三件套并重绑 `sys.stdout/__stdout__/stderr/__stderr__/stdin/__stdin__`；无可附加控制台（双击启动）弹提示后退出码 2。设 `VIDEO_WATERMARK_TUI_DEBUG=1` 把判定过程追加到 `%TEMP%\video_watermark_tui_debug.log`。
- 命令行：`python -m app.cli --input in.mp4 --output out.mp4 [--mode tiled|motion] [--kind text|image] [--text|--image] [--angle] [--trajectory] [--set k=v] [--crf --preset --scale] [--hw-encoder auto|none|nvenc|qsv|amf|d3d12va|mf] [--hw-codec h264|hevc] [--no-hw-decode] [--ffmpeg PATH|internal]`。
  - `--set k=v` 覆盖 `WatermarkConfig` 任意字段（可重复）；`--print-config` 打印完整配置 JSON。
  - `--hw-encoder` 默认 `auto`（自动选可用硬件编码器，无 GPU 回退 libx264）；`--hw-codec` 仅硬件编码时生效；`--no-hw-decode` 禁用硬件解码（默认开 `-hwaccel auto`，失败自动回退软解）。
  - `--ffmpeg`（v0.3.2）：指定 ffmpeg 可执行文件路径（Linux 上可用系统 ffmpeg / BtbN 构建获得硬件编码）或 `internal` 强制内置；亦可设环境变量 `VIDEO_WATERMARK_FFMPEG`。CLI 启动会打印实际选用的二进制与理由。
- 打包自检：`dist\VideoWatermark.exe --selftest`（Windows）/ `dist/VideoWatermark --selftest`（Linux）（离屏建窗+编码验证，退出码 0 = 正常）。

## 核心架构（数据流）

- `app/models.py` — `WatermarkConfig` 单一配置 dataclass，所有参数在此定义；`config_to_json`/`json_to_config` 序列化。
- `app/core/watermark.py` — 渲染文字/图片单元格、旋转、平铺瓦片、字体枚举。
- `app/core/motion.py` — 6 种轨迹（horizontal/vertical/diagonal/circle/figure8/sine），`position_at()` 返回帧时刻水印左上角坐标。
- `app/core/compositor.py` — `WatermarkCompositor` 逐帧 `apply(frame_rgb, t)`，含时间范围门控、自转。
- `app/core/encoder.py` — `probe()` 解析分辨率/帧率/时长/是否有音频；`process()` 读帧→合成→编码输出→**合并音频**。`process()` 支持**并行帧流水线**（`parallel` 参数：0=自动按 CPU 核数 2~4、1=串行、N=指定）：`_run_serial` 串行、`_run_pipelined` 多线程（主线程读帧 → N 个 worker 线程并行合成 → 独立写线程按帧序号保序喂给 ffmpeg，有界队列背压）。串行与并行输出**字节级一致**（合成逻辑相同、仅交付方式不同）。
- `app/core/preview.py` — 单帧预览渲染、轨迹示意图。
- **`app/tui.py`（TUI，v0.5.0）**：Textual 全屏应用——全字段表单（collect_config 抛 ConfigError 带[字段名]）、fill_from_config 回填、collect_export_params（crf/preset/scale/hw_*/parallel）、ExportScreen（ProgressBar+取消）、PreviewScreen（半块像素）。**布局陷阱：`#form` 必须 `height: 1fr`（滚动视口），用 auto 会溢出屏幕且无法滚动**。**行容器陷阱（v0.5.1）**：滚动容器内 `Horizontal` 默认 `height: 1fr` 会塌缩成 1 行（按钮 3 行画不下→滚到底也看不到最后一行），必须显式 `#form Horizontal { height: auto }`；`Input` 默认 `width: 100%`，与按钮同处一行会把按钮挤出 `overflow: hidden` 的行外，行内须改 `width: 1fr`。
- **`app/tui_preview.py`（v0.5.0）**：PIL 图像 → `▀` 半块字符 + 24bit RGB style 的 rich.text.Text（image_to_half_blocks，宽度自适应）；抽帧/轨迹复用 app/core/preview.py。
- `app/core/encoder.py` 新增 `ProcessCancelled`（v0.5.0）：`process(..., cancel_event=threading.Event)` 置位后中断并抛出；临时文件在 **writer.close() 之后**删除（close 会让 ffmpeg 重写空文件，先删会被复活）；并行路径取消走 state["error"] 机制，跳出读帧循环后仍需收尾队列排空在途帧。
- `app/core/ffbin.py` — **ffmpeg 二进制解析层（v0.3.2）**：统一决定全项目用哪个 ffmpeg，经 imageio-ffmpeg 官方覆写点 `IMAGEIO_FFMPEG_EXE` 生效（编码/探测调用零改动）。优先级：显式指定（CLI `--ffmpeg` / 环境变量 `VIDEO_WATERMARK_FFMPEG`，`internal`=强制内置，路径无效直接报错不回退；须压过子进程继承的镜像值，故先于下一项判断）> 用户已设 IMAGEIO_FFMPEG_EXE > 自动选择（内置缺硬件编码器时，探测系统 ffmpeg 若带 nvenc/qsv/amf/mf/d3d12va 则切换；否则维持内置）。决策进程内缓存，详情 `ffbin.info()`；`ffbin.reset()` 供 GUI 设置切换后清缓存（须连同 `hwaccel.detect_encoders.cache_clear()`）；自动分支异常一律回退内置，绝不影响启动。
- **GUI ffmpeg 二进制设置（v0.4.0）**：主窗口输出设置区三模式（自动/内置/自定义路径），QSettings（org=app="VideoWatermark"，键 `ffmpeg/mode`、`ffmpeg/path`）持久化；启动顺序为 QApplication → `load_ffmpeg_setting()` → `apply_ffmpeg_setting_to_env()` → `ffbin.get_ffmpeg_exe()`；selftest 路径不读设置。
- `app/ui/` — `main_window.py`（主窗口+RenderWorker QThread）、`batch_dialog.py`（批量处理）。

## 编码器关键陷阱（改这里必读）

- `imageio_ffmpeg.read_frames(path, pix_fmt="rgb24")` 产出为**生成器**，且**第一个产出是元数据 dict**，必须先 `next(gen)` 跳过再迭代帧字节。
- `write_frames(path, (w,h), pix_fmt_in=..., pix_fmt_out=..., fps=..., codec=..., macro_block_size=1, output_params=[...])` 返回**生成器**，必须先 `writer.send(None)` 启动，帧用 `writer.send(frame_bytes)`，结束 `writer.close()`（放 try/finally）。
- `macro_block_size=1` **必须保留**：默认 16 对齐会导致输出被内部二次缩放（如 640x360 → 368）拉伸变形。
- 输出尺寸只对齐到偶数（yuv420p 要求），不要强行 16 对齐。
- **音频保留**：`process()` 编码出的临时视频无音轨，之后用内置 ffmpeg `-map 0:v:0 -map 1:a:0 -c:a copy -shortest` 从原视频无损合并；容器不兼容时回退 `-c:a aac -b:a 192k`。输入无音频则直接改名收尾。修改此流程后务必跑 `scripts/verify_audio.py`。
- **子进程启动一律隐藏窗口**：GUI 无控制台（pythonw/打包 exe）下，直接 `subprocess.run/Popen` 拉 ffmpeg/explorer 会**一闪而过命令窗**。任何新的 ffmpeg/外部命令调用必须走 `app/core/subproc.py` 的 `run()/popen()`（Windows 自动附加 `CREATE_NO_WINDOW`），不得再裸用 `subprocess.run/Popen`。imageio-ffmpeg 内部已自带窗口隐藏，勿经此封装。修改后跑 `verify_hw.py`/`verify_audio.py` 确认子进程路径正常。

## GPU 硬件加速（改这里必读）

- `app/core/hwaccel.py` 统一负责硬件编码：`detect_encoders()`（对每个候选做极短样片实测编码，结果 `lru_cache`）、`resolve_encode()`（统一 CRF/预设 → 各家参数，回退 libx264）、`build_decode_input_params()`。
- 内置 ffmpeg v7.1（Windows 版）自带 `h264/hevc/av1_nvenc`、`h264/hevc_qsv`、`h264/hevc_amf`、`hevc_d3d12va`、`h264/hevc_mf`，**零新增依赖/二进制**；打包不受影响。
- **Linux 版内置 ffmpeg 未编译任何硬件编码器**（`-encoders` 中无 `*_nvenc/_qsv/_amf/_d3d12va/_mf`，v0.3.0 实测）：v0.3.2 起 `ffbin.py` 会在此场景**自动探测系统 ffmpeg**，若其带硬件编码器则切换使用（探测缓存键含二进制路径，切换自动失效重测）；无系统 ffmpeg 或其也无硬件编码器时维持内置，`auto` 回退 libx264。
- 探测结果缓存路径：Windows `%APPDATA%/VideoWatermark/`；Linux/macOS `~/.config/VideoWatermark/`（XDG_CONFIG_HOME 优先）。
- `process(...)` 新增参数：`hw_encoder="auto"`（auto/none/nvenc/qsv/amf/d3d12va/mf）、`hw_codec="h264"`、`hw_decode=True`（`-hwaccel auto`，头部解析失败自动回退软解）。返回 dict 新增 `codec` 键。
- `write_frames(...)` 必须传 `quality=None`：否则非 libx264 编码器会被追加 `-qscale:v`（旧代码隐式叠加 `-crf 25` 只是被后置参数覆盖）。
- 显式指定不可用编码器会 `raise RuntimeError`（不静默回退）；`auto` 才静默回退 libx264。
- 本机（RTX 4050 + Intel UHD）实测：`nvenc(h264/hevc/av1)`、`qsv(h264/hevc)`、`mf(h264)` 可用；QSV 会提示 `yuv420p→nv12` 自动选择，属无害信息。
- **确定性像素测试（`step1_demo.py`/`step4_acceptance.py`/`verify_audio.py`）固定 `hw_encoder="none", hw_decode=False`**，否则压缩噪声变化会让阈值判定不稳；GPU 路径由 `scripts/verify_hw.py` 专项覆盖。

## 验证与测试（11 套，全过再交付）

统一运行方式：

- Windows（PowerShell）：`$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe scripts\<name>.py`
- Linux/macOS：`PYTHONIOENCODING=utf-8 .venv/bin/python scripts/<name>.py`（GUI 测试另加 `QT_QPA_PLATFORM=offscreen`）

- `smoke_test.py` 轨迹坐标/文字图片渲染逻辑；`verify_ffbin.py` ffbin 解析层专项（internal/显式路径/环境变量优先级/联动，v0.3.2 起）；`tui_test.py` TUI 全流程专项（Pilot 无终端自动化：表单往返/校验/配置预载保存/预览屏/导出取消，v0.5.0 起；第 9 节布局回归：横向溢出/行内越界/底部按钮可达，v0.5.1 起）；`verify_step1.py` 像素级成品验证（水印差异 + 轨迹质心 vs `position_at`）；`gui_smoke.py` GUI 离屏冒烟（第 8 节长路径检测布局回归，v0.5.1 起）；`gui_export_test.py`/`step3_export_test.py`/`step4_batch_test.py` 端到端导出/编码参数/批量；`verify_time_range.py` 时间范围；`verify_audio.py` 音频保留；`verify_hw.py` 硬件加速专项（探测 + 各硬件编码器实跑 + 回退 + 硬解 + 音频，无硬件编码器时 GPU 项自动 SKIP）；`verify_pipeline.py` 并行流水线专项（串行/并行字节级一致 + GPU/移动/硬解组合，GPU 断言同样环境感知）；`step1_demo.py` 生成样例输出到 `outputs/`。

测试怪癖：
- GUI 测试须设 `QT_QPA_PLATFORM=offscreen`，且 `win.show()` 后才能 `isVisible()` 为真。
- 像素验证比较用 `read_frames` 按**精确帧索引**读取（勿用 `-ss` 抽帧，会错位）；阈值：水印信号用 40，时间范围"无水印"判定用 120（重编码噪声 ~2000px 会干扰）。
- 文字水印白底看不见——验收/演示须设 `stroke_width>=2` 描边。
- PowerShell 下 Qt 字体警告写 stderr 会被当 exit code 1，**属误报**，看脚本内打印的 "全部通过" 判定。
- **批量并行用 `ProcessPoolExecutor`（Windows spawn）**：任何会被进程池子进程导入的脚本/入口必须带 `if __name__ == "__main__":` 保护，否则子进程会重执行顶层代码递归（`step4_batch_test.py` 已按此改造）。Python 3.14 在 Linux 默认启动方式为 forkserver（Windows 仍 spawn），保护要求同样满足（v0.3.0 Linux 实测通过）。
- **Linux 硬件编码可用性随环境而变（v0.3.2 起）**：`verify_hw.py`/`verify_pipeline.py` 的 GPU 断言结果取决于 ffbin 最终选定的二进制——有带硬件编码器的系统 ffmpeg（或 `--ffmpeg`/`VIDEO_WATERMARK_FFMPEG` 指定）+ GPU 驱动时全过（WSL2 + RTX 4050 + 系统 ffmpeg 4.4 实测 nvenc 全过）；纯内置二进制的 Linux 则 GPU 断言 FAIL（其余路径应通过），属预期。

- **TUI 测试怪癖（v0.5.0）**：`pilot.click` 后须 `await pilot.pause(0.5)`（按钮按压动画周期，短 pause 会丢 Pressed 消息）；长表单中按钮可能在滚动视口外，先 `scroll_visible(animate=False)` 或改用按键（`pilot.press("f5")` 无坐标依赖）；跨线程回调（call_from_thread 里的 screen 访问）必须 try/except `ScreenStackError`（app 关闭竞态）。
- **Qt 布局怪癖（v0.5.1）**：与按钮同处 `QHBoxLayout` 的 wordWrap `QLabel` 动态 `setText` 成多行后，行高不按 `heightForWidth` 撑开（sizePolicy 默认不带该标志），长 ffmpeg 路径换行会压到相邻控件——动态多行信息放**独立整行**标签（如 `hw_detail_label`），并对其调 `_wrap_grow()`（main_window.py）。
- **Windows 控制台怪癖（v0.5.1/0.5.2）**：ConPTY（Windows Terminal）下 `GetConsoleWindow()` 恒为 0（控制台程序也是如此），判断"有无控制台"要用 `GetStdHandle+GetConsoleMode` 或把 `AttachConsole` 报 `ERROR_ACCESS_DENIED` 视为"已有"；GUI exe 无 stdio 时 Textual 输出走 `sys.__stdout__`、输入走 `GetStdHandle(STD_INPUT_HANDLE)`，附加控制台后必须 `SetStdHandle` 三件套并重绑 `__stdout__/__stderr__/__stdin__`（缺 `__stdin__` 会在 `enable_application_mode` 崩，且 bell 断言会掩掉原始异常）。**cmd/PowerShell 启动 GUI 子系统程序不等待且继续读控制台输入**——GUI exe 的 TUI 会与 shell 抢键，TUI 入口必须是控制台子系统程序（`VideoWatermarkTUI.exe` 垫片）或控制台 python（bat）。

## 打包与发布

- 构建：`.venv\Scripts\pyinstaller.exe video_watermark.spec --noconfirm`（Windows onefile，产物 `dist\VideoWatermark.exe` 约 86MB + `dist\VideoWatermarkTUI.exe` 控制台垫片约 10MB；Linux 同一 spec 直接 `pyinstaller video_watermark.spec --noconfirm`，产物 `dist/VideoWatermark` ELF，约 108MB，v0.3.0 实测 selftest 通过）。**spec 文件已从中文名改名 `video_watermark.spec`，产物名固定英文 `VideoWatermark`，勿改回。**
- 重建前先 `Stop-Process -Name VideoWatermark -Force`（残留的 onefile 引导进程会锁 exe 导致 PermissionError）。
- GUI 子系统 exe 退出码：PowerShell 须用 `Start-Process -Wait -PassThru` 读 `$p.ExitCode`，`&`/`$LASTEXITCODE` 会得到空值。
- **构建产物与媒体不入库**：`dist/`、`build/`、`outputs/`、`*.mp4`、`*.png` 等均在 `.gitignore`。产物通过 GitHub Releases 分发。
- **CI 双平台构建（v0.3.0）**：`.github/workflows/build.yml`，矩阵 `windows-latest` / `ubuntu-22.04`，推 `v*` 标签或手动触发（workflow_dispatch）；构建后跑 `--selftest` 自检，tag 触发时自动创建 Release 附双平台产物。改动 workflow 后须先在分支验证跑通再合并。
- 发布：`gh release create vX.Y.Z <产物文件> --title "VideoWatermark vX.Y.Z" --notes "<说明>" --repo illagerCPR/video-watermark`（v0.3.0 起产物含 Windows exe + Linux tar.gz；CI tag 触发时自动发布）。每次用户要求上传即新开一个递增版本号（不覆盖旧标签）。

## 协作约定

- 用户偏好**分步执行 + 每步确认**（"开始"/"继续"驱动）；涉及用户操作 GUI 的验证先说明步骤。
- 目标平台 Windows + Linux（v0.3.0 起）；保持双击启动可用（Windows `启动.bat`、Linux `启动.sh`）。
- 改动核心渲染/编码后，先跑 `smoke_test.py` + `verify_step1.py`，再做 GUI 冒烟与端到端；最后按需重建 exe + selftest + 提交推送。
- **每个功能完成后必须同步更新 `README.md`**：新增/变更的功能点、CLI 参数、GUI 控件、测试清单、常见问题都要反映到文档，再交付（提交/发布）。README 与实现脱节视为未完成。
