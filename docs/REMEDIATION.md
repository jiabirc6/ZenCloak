# ZenCloak 整改方案（REMEDIATION）

> 来源：2026-09-02 外部评审 + 本会话代码核实。评审中两处幻觉引用（`validateArchiveMemberName`、`OpenBrowser 50325`）与一条过时断言（"没有 Translate 测试"——实际 `tests/test_sessions.py:233-241` 已有）已剔除，不列入整改。
> 原则：每项先定义可验证的验收标准再动手；P0/P1 完成前不启动 P2 新功能。

## 优先级总览

| 级别 | 项 | 一句话 | 工作量 | 状态 |
|---|---|---|---|---|
| P0 | R1 翻译按钮 DOM 泄露 | 所有档案注入同一个 `#zencloakTranslateBtn`，一行 JS 即可识别 ZenCloak 并关联全部档案 | 小 | ✅ 已修（60cecd5） |
| P1 | R2 内核可插拔 | CloakBrowser 闭源+商业条款风险，launcher 注入点已有，补第二后端 | 中 | ⏸ 用户待定 |
| P1 | R3 Playwright 漂移加固 | Translate hack 已有测试断言，补版本 pin | 极小 | ✅ 已修（741be57） |
| P2 | R4 加密备份 | 登录态是全产品最贵资产，备份从"近期候选"提级 | 中 | ✅ 已完成（8038da4 + UI E2E 通过） |
| P2 | R5 跨平台解锁 | 第一步放宽 Win10 已完成；macOS/Linux 需先验证内核可用性 | 小→大 | 第一步 ✅（5ece8ab） |
| P2 | R6 指纹克隆 | 从本机真实浏览器采集生成档案 | 中 | 待做 |
| P2 | R7 CDP attach 模式 | 给外部 Playwright/Selenium 脚本暴露调试端口 | 小 | ✅ 已完成（E2E 通过） |
| P3 | R8 app.js 拆分 | 1209 行单文件，新功能进来前先模块化 | 中 | 待做 |
| P3 | R9 英文 README | 零成本海外流量 | 极小 | ✅ 已完成（1aa5291） |
| P3 | R10 onedir 默认发布 | 20s 启动劝退问题 | 小 | 待做 |
| 快赢 | R11 list_pages MCP 校验 bug | 今天实测发现：返回 JSON 字符串导致 Pydantic 报错 | 极小 | ✅ 已修（63cb4d9） |
| 快赢 | R12 mihomo 强杀残留 | 托盘退出 os._exit 路径留孤儿进程 | 小 | ✅ 已修（af9d05b） |

---

## P0

### R1：消除翻译按钮的自我指纹泄露

**问题（已核实）**：`core/extensions.py` 的 content.js 在每个 http/https 页面注入 `id="zencloakTranslateBtn"` 的浮动按钮（`document.documentElement.appendChild`），所有档案完全一致。任何网站 `document.getElementById('zencloakTranslateBtn')` 即可确认"这是 ZenCloak"，跨档案关联成立。
（评审说的"扩展 ID 一致"不成立：扩展目录是 per-profile 路径，ID 按路径派生本就不同；且网页无法枚举扩展。泄露面只有注入的 DOM。）

**方案**：
1. 档案新增字段 `translate_button: bool`（默认 **false**）。默认状态下 content.js **完全不注入任何 DOM**——翻译功能保留右键菜单「ZenCloak 翻译本页」和快捷键 Alt+Shift+T（这两者不触碰页面 DOM，网页不可观测）。
2. 用户显式开启浮动按钮时：按钮 id 由 seed 派生（如 `zc-<sha1(seed+profile_id)[:8]>`），按钮放入 **Shadow DOM**，页面侧只能看到一个无属性的随机 id 宿主元素；content.js 源码中不出现 "zencloak"/"ZenCloak" 字面量。
3. `models.py` 加字段校验；UI「行为」页加开关；`test_extensions.py` 更新断言。

**验收标准**：
- 默认档案访问任意页面，`document.documentElement.outerHTML` 不含 `zencloak`（不区分大小写）；
- 开启按钮后，页面 DOM 中不存在固定字符串 `zencloakTranslateBtn`，宿主元素 id 随 seed 变化；
- 右键菜单与快捷键翻译功能回归测试通过；155 测试全绿。

**涉及文件**：`core/extensions.py`、`core/models.py`、`ui/app.js`、`ui/index.html`、`tests/test_extensions.py`

---

## P1

### R2：内核可插拔（launcher 协议化）

**问题（已核实）**：核心价值 100% 押在 CloakBrowser 闭源二进制上（README FAQ 自述"升级最新内核可能需要账号或授权"）。`sessions.py:69` 已有 `launcher: Callable = launch_persistent_context` 注入点，但只有 CloakBrowser 一个实现。

**方案**：
1. 新建 `core/launchers.py`：`KernelAdapter` 协议（`launch(profile, user_data_dir, proxy, args) -> context` + `name` + `stealth_level`）；
   - `CloakBrowserAdapter`（现状封装，默认）
   - `CamoufoxAdapter`（Firefox 系 stealth，MIT 开源；作为可选 extra `zencloak[camoufox]`，懒加载，未安装时给出明确提示）
   - `VanillaChromiumAdapter`（playwright chromium，保底降级模式，UI 标注"隐身能力弱"）
2. 档案新增 `kernel: "cloak"|"camoufox"|"chromium"`（默认 cloak）；UI「指纹」页加内核下拉；体检报告头部显示当前内核与 stealth 等级。
3. 注意：Camoufox 的指纹参数体系与 CloakBrowser 不同（不是 `--fingerprint=<seed>`），适配器内做参数映射，映射不了的字段在 UI 标注"该内核不支持"。

**验收标准**：`kernel=chromium` 的档案能完整走通 launch→open_url→read_page→screenshot→stop；`kernel=camoufox` 在装了 extra 的环境同上，未装时启动报友好错误；CloakBrowser 路径行为零变化（现有 155 测试全绿）。

**涉及文件**：`core/sessions.py`、`core/launchers.py`（新）、`core/models.py`、`api.py`、`ui/`、`pyproject.toml`

### R3：Playwright Translate hack 加固

**问题**：`sessions.py` 顶部 `_PLAYWRIGHT_DEFAULT_DISABLE_FEATURES` 与安装的 Playwright 版本需人工同步（注释自述）。测试断言已有（评审说没有是错的），缺的是版本约束。

**方案**：`pyproject.toml` 给 cloakbrowser/playwright 加版本上界 pin；`docs/packaging.md` 增加"升级 Playwright 后必查此列表"检查项。

**验收标准**：`pip install -U playwright` 越界版本时安装即告警（或 CI 测试红）。

---

## P2

### R4：一键加密备份/恢复

**方案**：`core/backup.py`——全部档案 JSON + 可选浏览器数据目录 → AES-256 加密 zip（`pyzipper`，口令派生密钥）。UI 侧栏「备份全部」按钮 + 恢复入口。恢复时代理密码 DPAPI 重新加密为本机密文。
**验收标准**：备份包无口令打不开；恢复到新机器后档案可启动、登录态保留（数据目录模式）；导出包不含明文密码。
**涉及文件**：`core/backup.py`（新）、`api.py`、`ui/`

### R5：跨平台解锁（分两步，先验证再写码）

1. **立即做**：README「环境要求 Windows 11」放宽为 Windows 10/11（DPAPI 在 Win10 可用，纯文档改动）。
2. **先验证**：CloakBrowser 是否提供 macOS/Linux 二进制（查其 releases）。有 → `secrets.py` 抽象为 keyring 后端（Windows 仍 DPAPI），解锁跨平台；没有 → 维持 Windows-only，README 说明原因。**不验证不动代码。**

### R6：指纹克隆（从本机采集）

**方案**：复用 `health.py` 的 PROBE_JS，新增「从本机浏览器采集」入口：在**非隐身**临时上下文跑一次探测，采集真实 GPU/屏幕/UA/hardwareConcurrency/deviceMemory，生成档案草稿（现有"本地档案"自动创建的通用化）。
**验收标准**：采集生成的档案体检 11 项全 pass 且 webgl/screen 与本机真实值一致。

### R7：CDP attach 模式

**方案**：档案开关「暴露 CDP 端口」→ 启动时加 `--remote-debugging-port`（仅 127.0.0.1，随机端口），会话状态返回 endpoint；`docs/mcp.md` 旁新增 `docs/attach.md` 给 Playwright `connect_over_cdp` 示例。UI 明确警告：本机任意进程可完全控制该浏览器。
**验收标准**：外部脚本 `chromium.connect_over_cdp(endpoint)` 能 attach 并读取页面；默认关闭时端口不存在。

---

## P3

### R8：app.js 模块化拆分
按功能拆 `ui/modules/`：`state.js`、`profiles.js`、`proxy.js`、`sessions.js`、`health.js`、`menu.js`，`<script type="module">` 加载，无构建步骤。**DOM ID 契约不变**（`$()` 语义保留）。在 R1/R2/R4 的 UI 改动**之前**做，避免在旧结构上叠新功能。

### R9：英文 README
`README.en.md` + 顶部语言切换链接；`site/` 加英文首页。

### R10：onedir 为默认发布
Release 同时提供 onedir zip（推荐，1-2s 启动）与 onefile exe（便携）；README 安装指引改推 onedir。

---

## 快赢（顺手修）

### R11：list_pages MCP 校验 bug（今天实测复现）
`mcp.py` 的 `list_pages` 返回 JSON 字符串，FastMCP 输出模型期望 list → Pydantic 报错（内容本身正确）。修复：该工具返回结构化 list 而非 `_json_text` 包装。
**验收**：MCP `list_pages` 直接返回数组。

### R12：mihomo 强杀残留
托盘退出/`os._exit` 路径不跑 `ProxyManager.stop_all`。修复：`atexit` 注册 mihomo 清理 + 启动时扫描 `runtime/` 下已死会话的残留进程（按 PID 存活检测）补杀。
**验收**：托盘退出后 `tasklist` 无 mihomo.exe 残留。

---

## 明确不做（本轮）

- 团队协作/云同步/双内核自研维护——ROADMAP 后期项，不在本方案范围
- 给 CloakBrowser 做完整参数透传 UI——等 R2 适配器层稳定后再谈
- 扩展 ID 扰动——已核实非泄露面，不做

## 执行顺序建议

R1 → R11/R12（快赢）→ R3 → R8（拆模块）→ R2 → R4 → R5 第一步 → R9/R10 → R6/R7 → R5 第二步（视 CloakBrowser 二进制验证结果）