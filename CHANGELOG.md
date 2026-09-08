# 更新日志

本项目所有显著变更记录于此。格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本（`vX.Y.Z`，发版即打 tag，不覆盖旧标签）。

## [v0.5.7] - 2026-09-08

### 变更
- **批量完成消息标注实际编码器**（GUI/TUI 批量日志共用）：`完成：xxx.mp4（h264_nvenc）`，每个文件用了硬件还是 CPU 回退一目了然；并行模式由子进程回传 stats（`_run_one` 返回 `process()` 结果）
- **显式硬件编码器不可用的报错附当前二进制及来源**：报错末尾新增"当前 ffmpeg：…（来源）"——来源=内置（Linux 内置版无硬件编码器）或自定义路径指错文件时，一眼定位是"来源挡死"而非机器没 GPU

### 修复
- **硬件编码器探测缓存（`hw_encoders.json`）健壮性**（偶发"检测不到编码器"的嫌疑根因）：
  - 改**原子写**（tmp + `os.replace`）：批量并行的多个子进程此前会各自完整探测并并发覆盖写同一文件，可能交错损坏（虽可自愈但白跑探测）
  - **空探测结果不再落盘**：瞬时探测失败（如 NVENC 会话偶发建不起来）若被持久化，会在此后所有会话持续表现为"未检测到硬件编码器"（缓存键含二进制指纹，不升级就一直命中）；空结果只留在会话内存 lru，下次会话自动重测

### 文档
- README/FAQ 补充：GUI 来源=内置时 Linux 无硬件编码器的说明与排查指引

## [v0.5.6] - 2026-09-07

### 新增（TUI）
- **批量处理（F8）**：主表单新增「批量处理 (F8)」按钮/按键，打开 `BatchScreen`——多视频共用打开时的表单水印/编码参数快照：
  - 文件来源支持**单文件或目录**（目录递归扫描视频扩展名，自动去重）；列表可选中移除/清空；输出目录留空默认首个文件旁的 `水印输出/`；输出格式 MP4/MOV/MKV/AVI；**批量并行数**（0=自动，多进程同时处理多个视频）
  - 进度：文件级 + 当前文件帧级（滑动窗口速率 + ETA，与 GUI 批量同款平滑）；RichLog 逐文件结果日志
  - 取消：运行中 Esc/「取消」→ 串行中断当前文件；并行停止提交后续任务（在途文件处理完，界面上已注明）；取消后可再次开始
- **`app/core/batch.py`（GUI/TUI 共用批量后端）**：`scan_videos`（文件/目录递归展开）、`plan_jobs`（`原名_水印.扩展名` 命名）、`run_batch`（串行/进程池并行统一入口；并行帧进度经 `Manager().Queue` 回传转发线程；进程池**有界提交**，取消后不再提交后续）；GUI `BatchWorker` 迁移至同一实现（行为不变，`step4_batch_test` 回归通过）

### 文档
- README 全面核对修正：简介补 TUI/命令行入口；「一键检测」更正为 GUI/TUI；移除过时的 TUI 字段计数；轨迹数 6→7（界面说明表/项目结构）；项目结构补 `tui.py`/`tui_preview.py`/`tui_shim.py`/`core/subproc.py`/`启动-tui.bat`；FAQ「首次使用联网下载 ffmpeg」更正为**随 imageio-ffmpeg 自带、无需联网**；CLI 参数重复行/快速开始重复提示块清理；打包产物补 TUI 垫片（≈8MB）并更新体积

### 测试
- 新增 `scripts/tui_batch_test.py`（第 12 套）：core 层 `scan_videos`/`plan_jobs`/`run_batch` 取消语义 + Pilot 端到端（串行/并行/取消/布局回归），并行含 Manager 队列帧进度与关停断言

## [v0.5.5] - 2026-09-06

### 新增
- **移动轨迹新预设 `infinity`（∞ 形，横向双环）**：李萨如曲线 x=sin(a)、y=sin(2a)，与既有竖向 8 字形（`figure8`）取向互补；GUI/TUI 下拉与 CLI `--trajectory infinity` 同步可用。`TRAJECTORY_LABELS` 为 8 字形补充"（竖向）"标注以区分
- 新增 `PROJ_INFO.md`：项目结构/依赖/功能/测试/发布信息快照（随版本维护）

### 变更
- `smoke_test` 轨迹覆盖 7 种，并为 ∞ 形增加横向取向与中心自交专检

## [v0.5.4] - 2026-09-06

### 修复
- **Linux AppImage 检测不到硬件编码器而拒绝硬件加速**（CI 构建版复现、根因定位）：PyInstaller onefile 引导器把 `LD_LIBRARY_PATH` 指向运行时解包目录 `_MEIxxx` 并被所有子进程继承；旧工具链（ubuntu-22.04）构建的包在该目录带有**旧版 `libstdc++.so.6`**，系统 ffmpeg 因 `GLIBCXX_3.4.32 not found` 拒绝启动 → ffbin 自动切换与硬件探测全部静默回退内置。修复：冻结启动时从环境变量剥离指向 `_MEIPASS` 的条目（应用自身库已映射完毕，只影响子进程）。已验证：AppImage 内自动切换系统 ffmpeg ✓、强制系统 ffmpeg 走真实编码 ✓（修复前该路径必崩）

### 新增（TUI）
- **字段用途标签**：全部数值/选择参数行内显示用途（字号 / 颜色RGB / 水平间距 / 质量CRF…），预填值的输入框不再需要猜含义
- **「检测硬件」按钮**（与 GUI「检测」同源）：后台线程实测候选硬件编码器并输出编码器/解码器报告与当前 ffmpeg 二进制，结果就地显示
- **导出屏显示实际使用的编码器与解码方式**：进度条旁新增 `编码器：h264_nvenc · 解码：硬件优先（失败自动回退软解）`；GUI 进度条旁同步显示

## [v0.5.3] - 2026-09-06

### 修复
- **Linux「检测」不报告硬件解码器**：检测输出此前只包含硬件**编码器**（实测），用户装好系统 ffmpeg 后仍看不到任何解码器信息。现「检测」结果新增**硬件解码器**报告。

### 新增
- `hwaccel.hw_decoder_names()` / `hw_decoder_summary()`：解析当前二进制的 `-decoders` 具名硬件解码器（`*_cuvid`/`*_qsv`/`*_mf`/`*_d3d11va`/`*_d3d12va`）并合并 `-hwaccels` 硬件加速方法（VAAPI/CUDA/VideoToolbox/VDPAU 无具名解码器，不解析会漏报 AMD/Intel）；按族归并显示（如 "NVIDIA NVDEC（av1/h264/hevc…）、Intel QSV（…）、VAAPI"）。只报告已编译项、不逐个实测——硬解由导出时 `-hwaccel auto` 自动协商，失败自动回退软件解码
- Linux 未检测到硬件编码器时的提示补充说明 VAAPI 编码暂不支持
- GUI 切换 ffmpeg 二进制来源时同步失效解码器探测缓存

## [v0.5.2] - 2026-09-06

### 修复
- **Windows 运行 `VideoWatermark.exe --tui` 进得去 TUI 但按键无响应**：cmd/PowerShell 启动 GUI 子系统程序时**不等待其退出**并继续读取控制台输入（实测 PowerShell ~0.3s、cmd 批处理 ~0.6s 即返回提示符），用户按键被 shell 提示符抢走。经验证 TUI 自身输入读取路径完好（向运行中的 TUI 注入 Ctrl+Q 按键记录可正常退出）。

### 新增
- **`VideoWatermarkTUI.exe`（Windows，控制台子系统垫片）**：shell 会等待控制台程序退出——垫片拉起同目录 `VideoWatermark.exe --tui` 并等待，期间 TUI 独占键盘输入；双击垫片也会打开终端窗口运行 TUI。现为本机 TUI 的**推荐启动方式**（`python -m app.tui` / `启动-tui.bat` 不受影响）。CI 产物新增 `VideoWatermarkTUI-windows-x86_64.exe`
- `VideoWatermark.exe --tui` 非垫片启动时在控制台打印抢键提示（垫片经环境变量 `VIDEO_WATERMARK_TUI_PARENT_SHIM=1` 标记，不重复提示）

### 变更
- `video_watermark.spec` 拆为双产物：主程序（GUI 子系统，不变）+ TUI 垫片（仅 Windows，无 Qt/ffmpeg 依赖）

## [v0.5.1] - 2026-09-06

### 修复
- **GUI「检测」后文字布局错乱**：检测结果与「检测」按钮同处一个 `QHBoxLayout` 时，换行 `QLabel` 的行高不随长文本（打包后 `_MEI` 长 ffmpeg 路径）换行撑开，文字压到相邻控件。修复：多行结果移入独立整行的详情标签，动态换行标签统一启用 `heightForWidth` 尺寸策略
- **TUI 表单滚到底仍看不到底部按钮**（加载配置/保存配置）：滚动容器内 `Horizontal` 行的默认 `height: 1fr` 塌缩成 1 行（按钮 3 行画不下），虚拟内容高度比实际矮 2 行。修复：`#form Horizontal { height: auto }`
- **TUI 预览区按钮不可见**（预览帧/轨迹示意被推出行右缘）：`Input` 默认 `width: 100%` 占满整行，同行按钮被 `overflow: hidden` 裁掉。修复：行内 `Input` 改 `width: 1fr`
- **Windows Terminal 下 `exe --tui` 误弹"请从命令行启动"**（退出码 2）：ConPTY 环境下 `GetConsoleWindow()` 恒为 0，且 `ATTACH_PARENT_PROCESS` 附加到的是 PyInstaller onefile 的无控制台引导器，附加必然失败。重写 `_setup_tui_console`：改用 `GetStdHandle+GetConsoleMode` 判定 + 沿祖先链 `AttachConsole(pid)`；接好 `SetStdHandle` 三件套并重绑 `sys.stdout/__stdout__/stderr/__stderr__/stdin/__stdin__`（Textual Windows 驱动依赖，缺 `__stdin__` 会在 `enable_application_mode` 崩溃）。实测 Windows Terminal 标签页内 TUI 正常运行
- TUI 标题版本号改由 `app/__init__.py` 单一来源（此前硬编码 `v0.5.0-dev`）；`__version__` 同步升至 0.5.1

### 变更
- 测试：`tui_test.py` 新增第 9 节布局回归（三种窗口尺寸下断言无横向溢出、行内子件不越界、滚到底可见底部按钮，含 resize 往返）；`gui_smoke.py` 新增第 8 节（模拟长 ffmpeg 路径断言检测信息布局不重叠）
- 新增环境变量 `VIDEO_WATERMARK_TUI_DEBUG=1`：exe `--tui` 控制台附加判定过程写入 `%TEMP%\video_watermark_tui_debug.log`
- README 清理过期「Linux 暂无 AppImage」条目（v0.4.0 起已提供）

## [v0.5.0] - 2026-09-06

### 新增
- **TUI 交互模式**：Textual 全屏终端界面（`app/tui.py`），像 GUI 一样交互式配置全部 22 个水印字段 + 编码参数，无需记忆命令行
- **半块像素预览**（`app/tui_preview.py`）：任意时间点的水印合成帧 + 6 种轨迹示意图，直接渲染在终端内（`▀` 字符 + 24bit 颜色，宽度自适应）
- **交互式导出**：帧进度 + 平滑速率 + ETA + 一键取消；引擎 `process()` 新增 `cancel_event` 取消支持（`ProcessCancelled`，临时文件彻底清理）
- **配置文件**：`--config` 预载 / 界面内加载保存（`Ctrl+S`），与 GUI/CLI 的 JSON 完全互通
- **双入口**：`python -m app.tui`、`python -m app.cli --tui`、Linux `./启动.sh --tui`、Windows `启动-tui.bat`
- **Windows exe 双模式**（实验性）：`VideoWatermark.exe --tui` 自动附加父控制台进入 TUI；双击启动（无控制台）弹提示后转 GUI
- **测试**：新增 `tui_test.py`（Textual Pilot 无终端自动化，8 段断言），测试体系增至 **11 套**

### 变更
- 导出按键/表单校验：非法值提示带字段名与允许范围

## [v0.4.0] - 2026-09-06

### 新增
- **GUI ffmpeg 二进制来源设置**：输出设置区可选「自动（推荐）/ 内置二进制 / 自定义路径」，QSettings 持久化；切换即时生效于下次生成/检测
- **「检测」结果增强**：同时显示当前实际使用的 ffmpeg 二进制与来源；Linux 未检测到硬件编码器时提示安装系统 ffmpeg
- **Linux AppImage 产物**：`scripts/build_appimage.sh`（AppDir/AppRun/desktop/图标），CI 自动打包并以 `--selftest` 验证，无 FUSE 环境自动解包运行；Release 产物扩为 exe / tar.gz / AppImage 三件套

### 变更
- CI actions 升级（checkout v7 / setup-python v7 / artifact v7、v8），消除 Node 20 弃用警告
- 新增 `CHANGELOG.md`；README 新增「已知限制」（VAAPI 暂不支持等）

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

[Unreleased]: https://github.com/illagerCPR/video-watermark/compare/v0.5.0...HEAD
[v0.5.0]: https://github.com/illagerCPR/video-watermark/compare/v0.4.0...v0.5.0
[v0.4.0]: https://github.com/illagerCPR/video-watermark/compare/v0.3.2...v0.4.0
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
