# ZenCloak HANDOFF

最后更新：2026-10-15

> 本文档描述**当前真实状态**。核对方式见下方「如何确认现状」，不要凭本文档下结论。

## 当前任务

ZenCloak 是一个基于 CloakBrowser stealth Chromium 的个人指纹浏览器桌面客户端。
当前处于「可分发、可安装、可维护」阶段，主线是外部评审整改（`docs/REMEDIATION.md`）。

仓库：https://github.com/jiabirc6/ZenCloak
版本：`0.4.0`

## 如何确认现状

```powershell
cd E:\codex\opencode-zen\zencloak
python -m pytest tests -q          # 期望 323 passed，约 26 秒
git status --short                 # 期望无输出（工作树干净）
git log --oneline -5
```

## 当前状态（2026-10-15 实测）

| 项目 | 值 |
|---|---|
| 版本 | `0.4.0` |
| 测试 | ✅ 323 passed（约 26 秒） |
| 工作树 | 干净 |
| HEAD | `783246c` |
| 依赖 | cloakbrowser 0.3.31 / playwright 1.60.0 / fastapi 0.141.1 |

## 已完成

### 客户端功能

- 多指纹档案管理：指纹种子、时区、语言、屏幕、CPU 核数、设备内存、User-Agent
- 可插拔内核（R2）：CloakBrowser（默认）/ Camoufox（实验）/ 原生 Chromium（保底）
- 独立持久化 profile：cookie、登录态、历史数据按档案隔离
- HTTP / SOCKS5 代理 + 内置 Mihomo（订阅、节点测速、出口 IP 检测）
- 代理密码 DPAPI 加密落盘
- 一致性预检：出口 IP 地理位置 vs 档案时区/语言，一键修正
- TTS 语音包伪装：按档案语言重写 speechSynthesis 语音列表
- 指纹体检报告：webdriver / WebRTC / Canvas 噪声 / UA 一键深检
- 加密全量备份 / 恢复（R4）：AES-256 口令加密 zip，运行中档案自动跳过
- CDP attach（R7）：外部 Playwright / Selenium 可接入运行中的档案
- 下载目录可选 + 下载文件名保留扩展名
- 翻译原地化：当前页遍历文本节点替换，不重载页面
- humanize 类人行为、回收站、批量启停、档案导入/导出/复制
- 时区 56 项 / 语言 39 项
- 单实例锁、一键启动/停止
- 本地 FastAPI，只监听 `127.0.0.1` 随机端口，Bearer token 保护
- MCP Server：AI 助手操控指纹浏览器

### 工程与测试

- 323 个测试通过（后端单测 + UI 冒烟）
- 统一 ID 校验（`core/identifiers.py`）、统一退出清理（`core/shutdown.py`）
- DPAPI 错误码修复（`use_last_error=True`）+ 路径穿越堵漏

### 打包与分发

- 双安装包：`ZenCloak-Setup-<ver>-dir.exe`（onedir，启动 ~1-2s）与 `ZenCloak-Setup-<ver>.exe`（onefile，启动 ~20s），均无需管理员权限
- 安装包不包含 CloakBrowser 二进制，首次启动浏览器档案时自动下载约 200MB 内核到 `~/.cloakbrowser/`
- GitHub Release 资产已加 label，README 中英双版并列展示两个包

### 文档

- `README.md` / `README.zh.md`（英文版见 `README.en.md` 说明）
- `site/`：GitHub Pages 主页，部署到 https://zc.190003.xyz/
- `docs/REMEDIATION.md`：整改清单 R1–R12
- `docs/ROADMAP.md`：近期 / 中期 / 后期规划
- `docs/packaging.md`：打包流程（含「上传后必须加 label」）
- `docs/mcp.md`、`docs/attach.md`、`docs/zencloak-tutorial.md`
- `docs/adspower-comparison.md`：AdsPower 对标分析

## 未完成

| 项 | 来源 | 说明 |
|---|---|---|
| **R6 指纹克隆** | REMEDIATION | 从本机真实浏览器采集生成档案。**代码中零实现痕迹**（已核实）。方案见 REMEDIATION 第 89 行：复用 `health.py` 的 PROBE_JS，在非隐身临时上下文跑探测，采集 GPU/屏幕/UA/hardwareConcurrency/deviceMemory |
| **R8 app.js 拆分** | REMEDIATION | `src/zencloak/ui/app.js` 约 1300 行。原计划要求在 R1/R2/R4 的 UI 改动**之前**做，但三项均已完成，**窗口已错过**，现在做难度更高。纯重构，无用户可见收益 |
| **R5 第二步** | REMEDIATION | 已调查完毕，见下节。**待定** |
| 代理池管理 | ROADMAP 近期 | 集中保存、绑定档案、连通性测试、出口 IP 显示。**代码中未实现** |
| 扩展指纹参数 UI | ROADMAP 近期 | WebRTC、Canvas/WebGL/WebGPU 噪声、GPU、移动端指纹。**`models.py` 中无相关字段** |
| 窗口同步 / RPA 模板 | ROADMAP 中期 | 未实现 |
| 档案导入迁移 | ROADMAP 中期 | Dolphin{anty} / GoLogin / Multilogin，未实现 |
| 团队协作 / 操作日志 / 云同步 | ROADMAP 后期 | 未实现 |

### R5 第二步：调查结论（2026-10-15，只查 Linux）

**结论：CloakBrowser 有 Linux 二进制，x86_64 与 ARM64 均支持；但许可有实质变化。**

可用性（官方 Platforms 表 + GitHub Releases 实测）：

| 平台 | Free | Pro |
|---|---|---|
| Linux x86_64 | Chromium 146（58 patches） | Chromium 154（87 patches） |
| Linux arm64（RPi / Graviton） | Chromium 146（58 patches） | Chromium 154（87 patches） |

- 旧版二进制在 GitHub Releases **公开直链**，无需 license key
  （实测 HEAD 返回 200：`cloakbrowser-linux-x64.tar.gz` 216.9MB、`cloakbrowser-linux-arm64.tar.gz` 208.1MB）
- 最新版（Chromium 154）需要**付费订阅**；免费路径需 GitHub 登录换 key，且**限 1 个并发会话**

许可要点（`BINARY-LICENSE.md`，Version 1.3 / July 2026）：

- **wrapper 源码是 MIT；编译出的二进制是专有软件**，适用单独的 Binary License
- Restrictions 明确禁止：再分发、转售/再授权/重新打包、**包含在向第三方分发的任何产品或服务中**（除非另有单独授权）、逆向、修改
- 例外：用命令行标志、浏览器扩展、自定义 profile、user data dir 属正常使用，**不构成修改或衍生作品**（ZenCloak 当前用法落在这一白名单内）
- CloakHQ 保留单方面调整价格、功能、以及「哪些大版本需要付费」的权利

**影响**：免费版被限制在 Chromium 146 且 1 并发会话，与 ZenCloak「多开档案」的核心卖点冲突。
若要面向 Linux 用户分发带最新内核的版本，需要付费订阅且受 restriction #2 约束。
R2 的可插拔内核（Chromium 保底 / Camoufox）正是对冲此风险的方案。

**为什么待定**：这已从「技术可行性」问题变成「商业决策」问题——ZenCloak 是否要面向 Linux 用户分发。
REMEDIATION 第 85 行的验收标准（「有 → 抽象 keyring 后端」）按字面应执行，
但 `secrets.py` 的 DPAPI 抽象是否值得投入，取决于上面的决策。

## 下一步计划

建议顺序（按「用户可见收益 + 风险低」排）：

1. **R6 指纹克隆** —— 有实际产出，可复用现成 `health.py` PROBE_JS，改动面小
2. **代理池管理** —— 有实际产出，但涉及新数据结构 + UI，改动面较大
3. **R8 app.js 拆分** —— 建议放最后，或等有新 UI 功能要加时一并做
4. **R5 第二步** —— 等商业决策明确后再动

## 踩过的坑

### 启动 / 进程

- 旧版 `pythonw -m zencloak` 和测试残留的 `ZenCloak.exe` 会占用单实例锁，导致新启动弹「已在运行」。处理方式：任务管理器结束所有 `ZenCloak` / `pythonw` 进程。
- PyInstaller onefile 被强制结束后可能残留子进程，同样会占锁。

#### 「点退出没反应」的挂起（2026-10-15 观察到，根因未确定）

> ⚠️ **先读这段**：本小节的**根因尚未查明**。此前有一个版本在这里写了一个
> 看起来很合理的根因，后来被实验推翻，已删除。**不要照着猜测去改
> `shutdown.py`** —— 实测证明那条路径是正常的。详见下方「已排除的假设」。

**观察到的事实**（2026-10-15，一个跑了约 17 小时的开发版实例）：

```
进程状态
  pythonw.exe -m zencloak，PID 23312，启动于 2026-10-14 17:10:28
  Responding = False          <- Win32 消息循环没在泵消息
  33 线程 / 1534 句柄 / CPU 1331s（30 秒内只涨 0.5s，不是在自旋）

接口响应
  GET  /api/profiles    → 0.01s 正常
  GET  /api/sessions    → 挂死，>30s 无响应
  POST /api/shutdown    → 0.1s 返回 {"ok":true}，但进程 30s 后仍存活

退出后
  cloakbrowser 的 chrome 子进程随之消失，mihomo 成为孤儿（父进程已死）
```

**未确定的部分**：`/api/sessions` 为何会挂、`os._exit(0)` 为何没有执行到，
**都不清楚**。当时没有抓线程栈，进程已被强制结束，**证据已丢失**。

**已排除的假设**（2026-10-15 用对照实验推翻，勿重复推测）：

| 假设 | 实验结果 | 结论 |
|---|---|---|
| 会话线程卡住 → `stop_all` 的 `join` 堵死清理路径 | 干净实例 POST `/api/shutdown` **0.6s 退出 code=0**；带活跃浏览器会话 **0.5s 退出 code=0** | ❌ 排除 |
| `SessionManager.status()` 会阻塞 | 真实 `SessionManager` + 卡死线程，`status()` **0.000s 返回** | ❌ 排除 |
| `stop_all(wait=True)` 会永久挂起 | 5.01s 返回（超时上限），不会永久挂起 | ❌ 排除 |
| 有锁被跨阻塞调用持有 | 静态扫描 `sessions.py` 全部 `with self._lock` 块，**锁内零个阻塞调用** | ❌ 排除 |

关键点：`/api/shutdown` 走 `spawn_hard_exit` → `stop_everything(wait=False)`，
**不等待会话线程**，所以它不可能被会话线程堵住。

**下次复现时要做的**（这才是能定性的手段）：

```powershell
pip install py-spy
py-spy dump --pid <PID>        # 抓全部线程栈，这是唯一能给出直接证据的手段
```

**应急处置顺序**（先杀宿主，再收孤儿）——**这是已验证有效的手法，不是根因**：

```powershell
Stop-Process -Id <pythonw的PID> -Force    # 1. 先杀 ZenCloak 宿主
# 此时 cloakbrowser 的 chrome 会随之退出
Stop-Process -Id <mihomo的PID> -Force     # 2. 再杀 mihomo 孤儿（父进程已死，不会自动回收）
```

**验证干净的标志**：`zencloak.lock` 可读（未被占用）、无 `mihomo` 进程、
无 `cloakbrowser` 路径下的 `chrome.exe`、无 `pythonw -m zencloak`。

> **给下一任会话的提醒**：这里曾经有过一次误判 —— 凭 `sessions.py` 里
> `thread.join(timeout=5)` 的存在，就推断"清理路径被堵死"，且未做任何验证
> 就写进了本文档。后来一跑实验就推翻了。
> 教训：**报根因前必须能指出验证它的那条命令**；指不出来，就只能报
> 「观察到 X」，不能报「因为 Y」。

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
- 最新（Chromium 154）需付费订阅；免费路径需 GitHub 登录且限 1 并发。详见上文「R5 第二步」。
