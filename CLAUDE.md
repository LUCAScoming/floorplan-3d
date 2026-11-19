# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

纯前端户型装修设计工具：`index.html` 单文件承载全部 2D（SVG）/ 3D（Three.js）逻辑，无框架、无构建、无 npm；`app.py` 是 Python **标准库** HTTP 服务器，负责托管页面与方案 JSON 存取。仓库同时是飞牛 fnOS 原生应用（`.fpk`）及 Windows / Linux / macOS 桌面包的发布工程。

## 常用命令

运行 / 开发：

- `python app.py` — 启动本地服务器（默认 8765，自动打开浏览器）；可选参数 `--port`、`--data-dir`、`--no-browser`
- Windows 双击 `启动服务器.bat`（首次会 `pip install -r requirements.txt`，但该依赖清单已过期，见「文档与代码的已知出入」）
- `python -m http.server 8000` — 纯静态预览；此时无 `/api/plans`，方案保存 / 打开不可用

打包 / 发布（产物 `floorplan3d-<版本>-*`）：

- `python pack_fpk.py [版本]` — 飞牛 fnOS x86 + arm；**会删除并重建 `app/`，同时重写 `manifest`、`cmd/`、`config/`、`wizard/`、`ICON.PNG`、`ICON_256.PNG`、`floorplan3d.sc`**
- `python pack_win.py [版本]` / `python pack_linux.py [版本]` / `python pack_mac.py [版本]`
- `python release.py [版本]` — 全流程：四个构建脚本 → 打 tag 并推送 → 创建 GitHub Release 并上传 5 个产物 → `manifest` 与页面 `APP_VER` 的 patch 位 +1 → `CHANGELOG.md` 标发布日期并预留下一版本区块 → 自动提交并推送
- `python push.py "提交说明"` / `python pull.py` — 从 `.env` 读取 `GITHUB_TOKEN` / `GITHUB_REPO_URL`（`.env` 已被 `.gitignore` 排除）

没有测试框架、lint、前端构建步骤。验证按项目规则在浏览器中实测 2D / 3D / 漫游，确认无控制台报错；Python 侧可用 `python -m py_compile app.py pack_fpk.py pack_win.py pack_linux.py pack_mac.py release.py push.py pull.py` 做语法自检。

## 架构

### index.html（约 1.37 万行 / 1 MB）分两段脚本

1. 经典 `<script>`：多语言与常量、内置户型数据表、2D SVG 渲染、全部指针 / 键盘交互、方案服务器 API
2. 末尾 `<script type="module">`：Three.js 3D 场景。模块与经典脚本共享全局词法作用域，所以 3D 直接读 `state` / `ui`；反向桥接靠 `window.View3D`（`enter` / `exit` / `sync` / `pick` / `flyToRoom` 等）与 `window.drawAt3D` / `window.cancelDraw3D`

代码以 `/* ====== 分区名 ====== */` 注释分块（状态 / 历史、几何工具、颜色 / 材质图案、渲染、右侧面板、操作、视图、吸附、画墙、指针交互、键盘、家具库、导入导出、2D/3D 切换、对象列表、服务器方案；3D 侧：初始化、材质、几何小工具、家具模型、建筑、日照 / 夜景、相机动画、选择 / 拾取、漫游、主循环）。定位功能先搜这些分区标题。

### 状态模型（改代码前必读）

- `state`：方案数据，唯一数据源，2D / 3D 共用；字段见 `defaultState()`（`furniture`、`rooms`、`walls`、`openings`、`deletedWalls`、`demolished`、`removedB`、`dims`、`rails`、`beams`、`slabs`、`parapets`、`canopies`、`lifts`、`balconies`、`axes`、`roofs`、`pools`、`decks`、`pergolas`、`gates`、`extras` 等）
- `ui`：界面状态（`ui.tool` = `select | preview | measure | draw`，二级子工具在 `ui.drawTool`、选中 `sel` / `multi`、图层开关 `layers`、绘制中间态 `mA` / `mCur` 等），**不写入方案 JSON**（`layers` 在保存时单独挂到 JSON 上，打开时由 `applyLayers()` 剥离还原）
- 所有修改统一走 `mutate(fn)`：快照 → 执行 → 压入 `undoStack`（上限 150）→ `markDirty()` → `renderAll()`。绕过 `mutate` 直接改 `state` 会丢失撤销、脏标记与自动保存
- `renderAll()` 末尾调用 `window.View3D?.sync()`；3D 侧 `sync()` 对架构 / 家具 / 标签做 JSON 签名比对，只重建变化部分
- 启动是 `blankState()`：内置墙、房间、门窗全部移出（`deletedWalls` / `removedB`）。`WALLS` / `WINS` / `DOORS` / `ROOMS` / `MATS` / `LIB` 是可恢复的“原始户型”数据表
- 坐标单位 mm，原点 = 左上外墙内皮；矩形类构件统一存「中心点 + 宽深」，线性构件存两点

### 持久化

- 前端：`PUT/GET/DELETE /api/plans/{name}`。改动后 2 秒防抖 `autoSave()`，未命名方案写入「自动保存」槽位；手动保存额外生成 480 宽 PNG 缩略图，`PUT /api/plans/{name}/thumbnail`
- 后端 `app.py`：`ThreadingHTTPServer` + `DualStackServer`（关闭 `IPV6_V6ONLY`，无 IPv6 时回退 IPv4）；方案名做路径穿越校验；JSON / PNG 均“临时文件 + 原子替换”；静态资源只服务根 `index.html` 与 `/libs/`
- 网页目录规则：脚本同级存在 `index.html` 就用同级，否则用 `www/`（fnOS 包内布局）

### 多语言

三语（`zh` / `zht` / `en`）：动态文案用 `tr(简体, English)`；静态 DOM 用 `data-en` / `data-en-title`；简→繁由 `s2t()` 查表转换。新增 UI 文案必须三语齐全，繁中走同一份简体原文转换，不要手写繁中副本。

## 项目约定

来源：`.trae/rules/project_rules.md` 与 `.codebuddy/rules/floorplan-3d/RULE.mdc`（两份内容一致）。

- **每次功能改动 / 修复必须同步更新根目录 `CHANGELOG.md`**，无需用户提醒。条目固定分类「新增 / 优化 / 修复」，只写用户可感知的“改了什么 + 效果”，不写内部重构流水账；当前开发版本放在最上方「（开发中）」区块
- **新增建筑工具必须覆盖完整链路**：除 2D 符号、3D 构件、属性面板、放置逻辑外，还要有直角 / 自由约束（统一复用 `axisLock`，Shift 临时锁轴）、框选与组操作（整组拖动、Ctrl+D、Delete）、橙色虚线选中框 + 对应手柄、矩形四角缩放 / 线性两端伸缩、细线与镂空构件补透明命中带
- **几何语义一致**：渲染、选中框、手柄、拖动必须使用同一套「中心 + 宽深」语义；长度可编辑的线性构件改长度时起点不动、终点沿原方向延伸
- 旋转为 CAD 命令式流程（选对象 → 点基点 → 拖动预览或输入角度，默认 15° 吸附，Shift 自由，Esc / 右键取消）
- 侧栏为顶部选项夹：左侧「建筑 / 家具库」，右侧「对象列表 / 属性」；「直角 / 自由」在画板上方居中，仅 2D 设计模式显示
- 不要手改生成物：`app/`、`manifest`、`cmd/`、`config/`、`wizard/` 由 `pack_fpk.py` 重建，改源文件后重新打包
- 版本号两处联动：`index.html` 的 `APP_VER` 与 `manifest` 的 `version`（`release.py` 发布后自动 patch +1）
- 界面文案与代码注释均为中文，内部风格是紧凑单行函数 + 分区注释；新增代码应与既有风格一致，不做无关重构

## 文档与代码的已知出入

- README 与 `requirements.txt` 写 FastAPI / Uvicorn，但 `app.py` 实际只 import 标准库（`http.server`），打包版说明也是“纯标准库、无第三方依赖”。以 `app.py` 为准
- `app/www/index.html` 是上次 `pack_fpk.py` 的构建副本，与根 `index.html` 存在少量版本差异；源码以根 `index.html` 为准，不要编辑 `app/www/`

## 新增功能入口速查

- 数据：`defaultState()` / `fixState()`（方案字段与兼容迁移）、`LIB`（家具库）、`MATS`（地面材料）、`WALLS` / `WINS` / `DOORS` / `ROOMS`（内置户型）
- 2D 渲染：`renderAll()` 及其展开的 `renderWalls` / `renderFurn` / `renderOpenings` / `renderPanel` / `renderDims` 等
- 3D 建模：`buildArch()`（墙 / 门窗 / 建筑构件）、`buildFurn()`（家具）、`buildFurniture()`（单件家具模型）
- 交互分发：指针在「指针交互」「画墙」分区，快捷键在「键盘」分区；2D 模式切换 `setTool()`、2D/3D 切换 `setView()`、3D 视角模式 `setMode()`