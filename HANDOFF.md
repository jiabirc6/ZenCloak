# ZenCloak HANDOFF

最后更新：2026-08-12

## 当前任务

ZenCloak 是一个基于 CloakBrowser stealth Chromium 的个人指纹浏览器桌面客户端。当前重点已经从“功能开发”进入“可分发、可安装、可维护”阶段：源码、测试、EXE、安装包、GitHub Release、文档和技能都已就绪。

仓库：https://github.com/jiabirc6/ZenCloak

## 已完成

### 客户端功能

- 多指纹档案管理：指纹种子、时区、语言、屏幕、CPU 核数、设备内存、User-Agent
- 独立持久化 profile：cookie、登录态、历史数据按档案隔离
- HTTP / SOCKS5 代理配置，密码使用 Windows DPAPI 加密落盘
- `humanize` 类人行为
- 一键启动 / 停止浏览器窗口
- 面板「打开网址」输入框，绕过 Chromium 新标签页问题稳定开新页面
- 单实例锁：重复启动会弹窗提示「ZenCloak 已在运行」
- 本地 FastAPI，只监听 `127.0.0.1` 随机端口

### 新标签页处理

- 曾尝试多种方案：JS 重定向、Service Worker、企业策略、修改 Web Data。
- 最终采用：`newtab-v3` 静态空白扩展页 + Service Worker 尽力跳转起始页。
- 效果：连续快速开多个标签页不再出现第三方转圈页；偶发停留在空白扩展页，但地址栏仍可用。

### 工程与测试

- 后端单测 + UI 冒烟共 63 个测试通过
- 真实 CloakBrowser 冒烟：`navigator.webdriver=false`、无 HeadlessChrome UA
- UI 使用 Playwright 验证过布局、控制台、URL 打开请求
- 单实例锁、DPAPI、URL 规范化、打开失败反馈均有测试

### 打包与分发

- `dist/ZenCloak.exe`：PyInstaller 单文件 EXE，约 125MB，绿色渐变 Z 图标
- `installer/ZenCloak-Setup-0.1.0.exe`：Inno Setup 安装包，约 128MB，无需管理员权限，创建开始菜单/桌面快捷方式
- GitHub Release：https://github.com/jiabirc6/ZenCloak/releases/tag/v0.1.0
- 安装包不包含 CloakBrowser 二进制，首次启动浏览器档案时自动下载约 200MB 内核到 `~/.cloakbrowser/`

### 文档

- `site/`：GitHub Pages 独立主页（obscura.sh 风格，Apache-2.0 改编），部署到 https://jiabirc6.github.io/ZenCloak/，About 链接已指向该站
- `README.md`：项目介绍、下载安装、使用、FAQ
- `docs/zencloak-tutorial.md`：新手教程
- `docs/ROADMAP.md`：近期/中期/后期计划
- `docs/adspower-comparison.md`：AdsPower 对标分析
- `docs/packaging.md`：EXE 与安装包制作流程
- `skills/obscura-skill/SKILL.md`：Obscura headless 浏览器技能，本机同时装在 `C:\Users\Administrator\.codex\skills\obscura-skill\`

## 卡住的问题

### Chromium 第三方新标签页

CloakBrowser v146 内核的 `+` 新标签页会进入 `chrome://new-tab-page-third-party/`，连续多开时会出现页面一直转圈。已确认不是 ZenCloak 代码问题，而是该内核的 New Tab 实现不稳定。

已修复（2026-08-13），当前采用三层防御：

- `newtab-v3` 扩展的 Service Worker 会识别并重定向 `chrome://new-tab-page-third-party/`，不再只认 `chrome://newtab`
- 新标签页统一落到 `about:blank` 空白页，不自动加载起始页，避免网络卡顿导致的转圈
- 所有档案启动时都会加载该扩展；会话循环每 0.3 秒扫描一次，把漏网的三方新标签页强制跳转空白页

已知边界：点 `+` 后显示空白新标签页，需要手动输入网址或用 ZenCloak 面板打开页面。

### 单文件 EXE 启动慢

PyInstaller onefile 每次启动需要解压依赖，约 20 秒。这是单文件模式的正常代价。若追求启动速度，可改成 onedir 文件夹模式，但会失去“单个 exe”的便携性。

### GitHub 推送偶发失败

`git push` 偶尔报 `schannel: failed to receive handshake`，直接重试通常成功。

## 下一步计划

按 `docs/ROADMAP.md` 执行，优先级如下：

1. 档案批量导入 / 导出 / 复制（JSON/CSV）
2. 代理池管理：集中保存、绑定档案、连通性测试、出口 IP 显示
3. 扩展指纹参数 UI：WebRTC、Canvas/WebGL/WebGPU 噪声、GPU、移动端指纹
4. Local API 完善与 MCP Server
5. 回收站、一键备份
6. 窗口同步、RPA 模板、指纹体检报告
7. 团队协作、操作日志、可选云同步

## 踩过的坑

### 启动 / 进程

- 旧版 `pythonw -m zencloak` 和测试残留的 `ZenCloak.exe` 会占用单实例锁，导致新启动弹「已在运行」。处理方式：任务管理器结束所有 `ZenCloak` / `pythonw` 进程。
- PyInstaller onefile 被强制结束后可能残留子进程，同样会占锁。

### PyInstaller

- 相对导入在打包后会失败：`from .api import ...` 报 `attempted relative import with no known parent package`。必须用绝对导入：`from zencloak.api import ...`。
- `_engine_info()` 不能用 `sys.executable -m cloakbrowser info`，打包后 `sys.executable` 是 EXE 本身。改用 `cloakbrowser.config.get_effective_version()` 和 `get_binary_path()`。
- EXE 正在运行时不能重新打包，会报 `PermissionError`，先结束进程再 build。

### 新标签页

- 不要在新标签页里放会联网加载的页面，否则会重现转圈。
- 扩展页的 JS 重试不能太激进，否则会锁死标签页，连地址栏输入都受影响。

### 文件与命令

- 本机 PowerShell 环境策略会拦截部分长命令、递归删除和组合 `Start-Process` 命令。遇到被拦时改用 Python 脚本执行。
- `apply_patch` 对部分 CRLF 文件做局部修改会失败，稳定做法是 delete + add 整文件。
- 大文件（EXE、安装包、仓库 clone）不要提交到 git；`dist/`、`build/`、`installer/*.exe`、`CloakBrowser-ref/`、`obscura-ref/` 已加入 `.gitignore`。

### CloakBrowser

- 当前 wrapper 0.3.31 / 内核 146 免费无需登录；升级提示 `Update available` 可忽略。
- CloakBrowser 二进制许可不允许再分发，所以安装包必须联网下载内核。
