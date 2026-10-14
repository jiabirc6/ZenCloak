# ZenCloak

[![主页](https://img.shields.io/badge/主页-GitHub%20Pages-black)](https://zc.190003.xyz/)

English documentation: [README.md](README.md)

基于 stealth Chromium 内核构建的个人指纹浏览器桌面客户端。

> 新手请先看：[ZenCloak 新手使用教程](docs/zencloak-tutorial.md)

主页：<https://zc.190003.xyz/>（源码在 [`site/`](site/)）

ZenCloak 以「指纹档案」为单位管理多个浏览器身份：每个档案拥有独立的指纹种子、代理、持久化会话和类人行为设置，一键启动真实浏览器窗口。

## 📦 版本亮点

**v0.4.0**
- 浏览器内核可插拔：CloakBrowser（默认）之外，可选实验性 Firefox stealth 内核 Camoufox（`pip install "zencloak[camoufox]"`），以及无隐身的标准 Chromium 保底
- 加密全量备份 / 恢复：档案 + 登录态打包为 AES-256 口令加密压缩包，运行中档案自动跳过
- TTS 语音包伪装：按档案语言重写语音列表，消除「语音包国家 ↔ IP 国家」检测异常
- CDP attach：外部 Playwright / Selenium 脚本可直接接入运行中的档案浏览器
- 时区扩充至 56 个、语言 39 种（含 zh-TW / zh-HK 繁体），UI 全新设计

**v0.3.0**
- 内置 Mihomo 代理：订阅导入 / 刷新 / 删除、机场节点自动展开、并发真实延迟测速、出口 IP 检测
- 指纹体检报告：一键深检 webdriver、WebRTC 泄漏、Canvas 噪声、UA 与配置生效
- 出口 IP 一致性预检：时区 / 语言与 IP 归属地不符时警告并一键修正
- MCP Server：AI 助手（ZCode / Claude Desktop / Cursor）直接操控指纹浏览器
- 回收站、批量启停、档案导入导出复制

完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 下载安装

最新版本：[ZenCloak Setup](https://github.com/jiabirc6/ZenCloak/releases/latest)

每个版本都提供**两个安装包**，装出来的程序完全一样，都无需管理员权限，区别只在打包方式：

| 文件 | 启动速度 | 打包形式 | 适合场景 |
|---|---|---|---|
| `ZenCloak-Setup-<版本>-dir.exe` | **约 1–2 秒** | 文件夹 | 日常使用 |
| `ZenCloak-Setup-<版本>.exe` | 约 20 秒 | 单个文件 | 拷到 U 盘携带 |

单文件版每次启动都要先把内部依赖解压到临时目录，多出的约 18 秒就花在这里；文件夹版依赖已在磁盘上就位，启动即开。**拿不准就随便选一个** —— 以后想换，装另一个即可。

首次启动浏览器档案时，若本机没有 CloakBrowser 内核，ZenCloak 会自动下载约 200MB 的 stealth Chromium 二进制并缓存在 `~/.cloakbrowser/`。

## 特性

- 多指纹档案：指纹种子、时区、语言、屏幕、CPU 核数、设备内存、User-Agent
- 可插拔浏览器内核：CloakBrowser（默认）、实验性 Camoufox（Firefox stealth）、标准 Chromium 保底降级
- 内置 Mihomo 代理：订阅导入 / 刷新 / 删除、机场节点自动展开、按地区筛选、并发测速（真实代理延迟）、出口 IP 检测
- HTTP / SOCKS5 手动代理，支持用户名密码；密码使用 Windows DPAPI 加密落盘
- 一致性预检：启动后自动比对出口 IP 归属地与档案时区 / 语言，不一致时警告并支持一键修正
- TTS 语音包伪装：按档案语言重写 speechSynthesis 语音列表，修复「语音包国家 ↔ IP 国家」异常
- 指纹体检报告：一键深检 webdriver 痕迹、WebRTC 泄漏、Canvas 噪声、UA、配置生效情况
- 类人鼠标、键盘、滚动行为（`humanize`）
- 独立持久化 profile：cookie、登录态、历史数据按档案隔离
- 一键启动 / 停止浏览器窗口，支持批量启停、回收站、档案导入导出复制
- 加密全量备份：全部档案 + 登录态打包为口令保护的 AES-256 压缩包
- 内置 BrowserScan、FingerprintJS、BrowserLeaks、Incolumitas 检测站点入口
- MCP Server：ZCode / Claude Desktop / Cursor 等 AI 助手直接操控指纹浏览器（见 [docs/mcp.md](docs/mcp.md)）
- CDP attach 模式：外部 Playwright / Selenium 脚本可直接接入运行中的档案（见 [docs/attach.md](docs/attach.md)）
- 本地 API 只监听 `127.0.0.1` 随机端口，Bearer 令牌鉴权
- 首次启动自动创建「本地档案」，默认匹配本机 Windows / Asia/Shanghai / zh-CN

## 环境要求

- Windows 10 / 11（x64）
- Python 3.12（仅开发模式需要）
- Node.js 不需要，但本机需要可用的 CloakBrowser binary

## 安装

```powershell
python -m pip install -e .
python -m cloakbrowser install   # 下载 stealth Chromium 二进制
```

## 启动

安装包用户：从开始菜单快捷方式启动即可（无控制台窗口）。

开发模式可以在 PowerShell 中启动：

```powershell
python -m zencloak
```

> 注意：`python -m zencloak` 运行期间不要关闭 PowerShell 窗口，否则应用会退出。

两个安装包的启动速度差别见[下载安装](#下载安装)。若想自行构建安装包（含快速启动的 onedir 版本），见 [docs/packaging.md](docs/packaging.md)。

## 使用

1. 首次启动后，左侧默认出现「本地档案」。
2. 点击「新建档案」创建新身份，按需配置指纹、代理和行为参数。
3. 点击「保存」写入 `~/.zencloak/profiles/`。
4. 点击「启动」打开该档案对应的 CloakBrowser 窗口，浏览器数据写入 `~/.zencloak/data/<档案ID>/`。
5. 档案运行中可点击检测站点按钮，直接在指纹浏览器里打开对应检测页面。

## 数据目录

```
~/.zencloak/
├── profiles/          # 指纹档案 JSON
└── data/              # 每个档案的持久化浏览器数据
```

## 项目结构

```
src/zencloak/
├── app.py             # 桌面入口：uvicorn + pywebview
├── api.py             # 本地 FastAPI 接口
├── mcp.py             # MCP Server：AI 助手操控指纹浏览器
├── core/
│   ├── fingerprint.py # 指纹参数与默认档案
│   ├── models.py      # 档案数据模型与校验
│   ├── profiles.py    # 档案 JSON 存储
│   ├── sessions.py    # CloakBrowser 会话管理
│   ├── mihomo.py      # 内置 Mihomo 代理与真实延迟测速
│   ├── subscriptions.py # 订阅导入 / 机场节点展开 / 刷新
│   ├── consistency.py # 出口 IP 与指纹一致性预检
│   ├── health.py      # 指纹体检探测脚本与报告
│   └── secrets.py     # DPAPI 加密存储
└── ui/                # 桌面 UI（HTML / CSS / JS）
```

## AI 助手集成（MCP）

ZenCloak 内置 MCP Server，让 ZCode / Claude Desktop / Cursor 等 AI 助手直接操控指纹浏览器：启动停止档案、打开网址、读取页面、截图、跑指纹体检。配置方法与工具列表见 [docs/mcp.md](docs/mcp.md)。

## 测试

```powershell
python -m pytest
```

包含真实 CloakBrowser 冒烟测试，会验证 `navigator.webdriver=false`、UA 无 Headless 痕迹、插件列表正常。

## 常见问题

**为什么直接打开 `src/zencloak/ui/index.html` 是坏的？**

UI 需要本地 API 才能读取档案。请始终通过安装后的 ZenCloak 程序或 `python -m zencloak` 启动；直接打开 HTML 会显示未连接提示。

**启动时出现 `Update available: cloakbrowser ...` 是什么？**

这是 CloakBrowser 的升级提示，不影响运行。当前 v146 内核免费且无需登录；升级最新内核可能需要 CloakBrowser 账号或授权，按需决定即可。

**代理密码存在哪里？**

已使用 Windows DPAPI 加密后保存在档案 JSON 中，仅本机当前用户可解密。请勿把 `~/.zencloak/` 或项目内档案文件提交到公开仓库。

## 许可

本项目包装与客户端代码采用 MIT 许可，见 [LICENSE](LICENSE)。CloakBrowser 二进制使用其自身许可，详情见 [CloakBrowser BINARY-LICENSE](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md)。请仅将本工具用于合法、已获授权的场景。
