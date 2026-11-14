# ZenCloak HANDOFF

最后更新：2026-11-14

> 本文档描述**当前真实状态**。核对方式见下方「如何确认现状」，不要凭本文档下结论。

## 当前任务

ZenCloak 是一个基于 CloakBrowser stealth Chromium 的个人指纹浏览器桌面客户端。
当前处于「可分发、可安装、可维护」阶段，主线是外部评审整改（`docs/REMEDIATION.md`）。

仓库：https://github.com/jiabirc6/ZenCloak
版本：`0.4.0`

> **开发收尾约定（所有 AI 会话适用）**：完成开发后须 ① 刷新本文件「当前状态 / 已完成 / 未完成」并随代码提交推送 ② 在 Obsidian `E:\obsidian\J-zencloak项目\开发日志.md` 追加本次开发记录（日期 / HEAD / 完成内容 / 测试状态）。

## 如何确认现状

```powershell
cd E:\codex\opencode-zen\zencloak
python -m pytest tests -q          # 期望 425 passed，约 45 秒
git status --short                 # 期望无输出（工作树干净）
git log --oneline -5
```

## 当前状态（2026-11-14 实测）

| 项目 | 值 |
|---|---|
| 版本 | `0.4.0` |
| 测试 | ✅ 422 passed（约 70 秒） |
| 工作树 | 干净 |
| HEAD | `0a31900` |
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
- 导出文件由后端写盘，保存位置按档案可选（`7742bb7` / `ef2b422`）
- 翻译原地化：当前页遍历文本节点替换，不重载页面
- 外观主题：浅色（默认）/ 深色 / 跟随系统，设置面板切换，localStorage 持久化
- humanize 类人行为、回收站、批量启停、档案导入/导出/复制
- 档案搜索、标签、cookie 导入导出、时区跟随（`1a7d409`）
- **内置代理分流（cn_direct，默认开）**：mihomo 改 rule 模式——69 条国内域名
  后缀（手写清单，不依赖 GeoIP 下载）+ 私网 CIDR 直连，其余走 GLOBAL 组选的
  节点；档案编辑代理页有「国内网站直连」开关，关掉回到全局模式。实测淘宝
  全家 DIRECT、muse.ai 走美国节点（`0a31900`）
- **窗口最大化**：启动参数加 `--start-maximized`（`488f822`）
- **每档案扩展管理**：UI 导入未打包目录/.crx（可选填商店链接或 ID）、列表/删除、
  启动时合并进 `--load-extension`；CRX 导入可固定官方商店 ID（manifest `key`），
  解决 muse.ai 这类按商店 ID 做 CSP `frame-ancestors` 白名单的站点
  （`7decd36` / `c923888`）
- 时区 56 项 / 语言 39 项
- 单实例锁、一键启动/停止
- 本地 FastAPI，只监听 `127.0.0.1` 随机端口，Bearer token 保护
- MCP Server：AI 助手操控指纹浏览器

### 工程与测试

- 336 个测试通过（后端单测 + UI 冒烟）
- 统一 ID 校验（`core/identifiers.py`）、统一退出清理（`core/shutdown.py`）
- DPAPI 错误码修复（`use_last_error=True`）+ 路径穿越堵漏
- 全部配色收敛为 CSS token（`styles.css` 顶部两套主题变量），
  两套主题各自完整；新增色值请走 token，硬编码会跟着不换主题。
- 修复节点延迟测速核心误经档案 ID 校验（`3f85659`）

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
| **R8 app.js 拆分** | REMEDIATION | `src/zencloak/ui/app.js` 已约 1670 行（2026-11-14 实测 1669）。原计划要求在 R1/R2/R4 的 UI 改动**之前**做，但三项均已完成，**窗口已错过**，现在做难度更高。纯重构，无用户可见收益 |
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
- **⚠️ stop/launch 会话 = 杀用户正在用的浏览器窗口（2026-11-14 事故）**：cookie/登录态不丢（持久化档案），但打开的标签页会没。改会话级配置（cdp_attach、内核等）前**必须先确认用户没在用**；万一关了，上一轮标签页可从
  `Default/Sessions/Tabs_*`（SNSS）提取 URL 重开，或让用户按 Ctrl+Shift+T。

#### 「点退出没反应」的挂起 —— 已修复（`3c8fe14`）

**现象**：点退出没反应；窗口关掉后 `pythonw.exe -m zencloak` 仍存活
（`Responding=False`），只能强杀。`/api/shutdown` 一样卡。

**根因：`sessions.py` 的 `stop()` 在持有锁时调用了 `status()`，
而 `status()` 自己也要拿同一把锁。**

```python
def stop(self, profile_id):
    with self._lock:                                    # ← 拿锁
        session = self._sessions.get(profile_id)
        if not session or session["status"] not in {"launching", "running"}:
            return self.status(profile_id)              # ← 持锁时再调 status()
        ...
def status(self, profile_id=None):
    with self._lock:                                    # ← 同一线程二次获取 → 死锁
```

`threading.Lock` **不可重入**，同一线程二次获取 = 永久卡死。

**为什么影响这么大**：`stop_all()` 遍历每一个会话，**只要有一个**档案
不处于 `launching`/`running`（比如已停止的）就撞进这个分支 →
整个退出流程卡住。而托盘退出和 `/api/shutdown` 走的是同一条路
（`stop_everything`），所以两条都废。清理走不完，mihomo 就变成孤儿。

**定位手段**：`9173a8b` 加的 `shutdown.log` 追踪直接把范围缩到一行 ——

```
修复前：  sessions.stop_all begin        ← 卡死，永远没有下一行
修复后：  sessions.stop_all begin
          sessions.stop_all done
          proxy_manager.stop_all done
          stop_everything done
          calling os._exit(0)
```

**修法**：早退分支不再在锁内调 `status()`，锁释放后统一调一次。

**为什么以前测不出来**：现有测试**只停 `running` 状态的会话**，走的是
另一个 `return`（那把锁已经释放）。这个分支从没被覆盖。
新增 2 个测试（`test_stop_does_not_deadlock_on_a_session_that_is_not_running`、
`test_stop_all_survives_a_mix_of_session_states`），已验证在旧代码上失败、
在新代码上通过。

**当次观察到的其他事实**（保留作为线索）：`Responding=False`、
33 线程 / 1534 句柄、CPU 30 秒内只涨 0.5s（不是在自旋）、
`/api/profiles` 0.01s 正常而 `/api/sessions` 挂死。

**应急处置顺序**（若将来再遇到类似的退出卡死 —— 先杀宿主，再收孤儿）：

```powershell
Stop-Process -Id <pythonw的PID> -Force    # 1. 先杀 ZenCloak 宿主
# 此时 cloakbrowser 的 chrome 会随之退出
Stop-Process -Id <mihomo的PID> -Force     # 2. 再杀 mihomo 孤儿（父进程已死，不会自动回收）
```

**验证干净的标志**：`zencloak.lock` 可读（未被占用）、无 `mihomo` 进程、
无 `cloakbrowser` 路径下的 `chrome.exe`、无 `pythonw -m zencloak`。

**若同类问题复发，先看 `~/.zencloak/shutdown.log`** —— 它逐行记录退出的
每一步，最后一行就指明卡在哪。实在需要线程栈再用 `pip install py-spy` +
`py-spy dump --pid <PID>`。

> **本节曾经有过一次误判**（2026-10-15）：当时凭 `sessions.py` 里
> `thread.join(timeout=5)` 的存在，就推断「清理路径被堵死」，未经任何验证
> 写进了本文档，还据此提出要改 `shutdown.py`。后来对照实验推翻了这个说法
> （干净实例和带浏览器会话的实例都 0.5~0.6s 正常退出），真因在另一处。
> 教训：**报根因前必须能指出验证它的那条命令**；指不出来，就只能报
> 「观察到 X」，不能报「因为 Y」。这一条已写进全局 AGENTS.md 第五条。


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

### 扩展加载（2026-11-14 排查 Muse from Meta 全记录）

三层坑叠加，逐层剥出来的：

1. **cloakbrowser 的 `extension_paths` kwarg 会同时发
   `--disable-extensions-except`**，把开发者模式加载的扩展静默禁用
   （toast 显示 Extension loaded、Secure Preferences 有注册条目，但
   chrome://extensions 不显示、SW 不跑）。修法：不走该 kwarg，改手动
   `--load-extension`。
2. **Playwright 默认参数带 `--disable-extensions`**，同样必须过滤——已加进
   sessions.py 的 IGNORE_DEFAULT_ARGS 补丁。
3. **未打包扩展的 ID = 路径哈希，不在任何白名单里**。muse.ai 的 CSP
   `frame-ancestors` 只放行商店官方 ID `jnakhh...`，面板 iframe 被 CSP 掐死
   → 拿不到凭据 → `wss://hatch.metaaivm.com` 401 → "Couldn't connect"。
   修法：CRX 导入时按商店 ID（外部信息，**CRX 文件里不存自己的 ID**——
   Chromium 用外部 ID 匹配 header 里多个 proof 公钥）选对应的 key 写进
   manifest `key` 字段，未打包副本即获得官方 ID。

**调试手段（下次直接用）**：CDP attach 后用裸 WebSocket 挂到
`/json/list` 的 service_worker target 上（Playwright connectOverCDP 在这个
内核上会挂死，别用），`Runtime.evaluate` + `awaitPromise` 直接在 SW 上下文
跑探针；`Network.enable` 能抓到浏览器视角的真实握手错误（401/451 等）。
注意 CDP 面板 target 的 Log.entryAdded 一次性抓到了 CSP 报错，是定位
第 3 层坑的关键证据。

**Muse from Meta 背景知识**：Meta 2026-11-13 发布的浏览器 Agent 扩展，
`agent.meta.ai` 重定向到 muse.ai——它就是 muse.ai 的伴生扩展；后端
`wss://hatch.metaaivm.com/v1/noise`。Binance/echo 的 WS 测试失败是端点
自身的地区拦截（451）等红鲱鱼，与内核无关。

### CloakBrowser

- 当前 wrapper 0.3.31 / 内核 146 免费无需登录；升级提示 `Update available` 可忽略。
- CloakBrowser 二进制许可不允许再分发，所以安装包必须联网下载内核。
- 最新（Chromium 154）需付费订阅；免费路径需 GitHub 登录且限 1 并发。详见上文「R5 第二步」。
