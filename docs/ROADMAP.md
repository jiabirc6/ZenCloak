# ZenCloak Roadmap

按阶段排列，仅作规划，不承诺时间。完整对标分析见 [adspower-comparison.md](adspower-comparison.md)。

> 最后更新：2026-10-15。已完成项见「已实现」；当前未完成项汇总见 [HANDOFF.md](../HANDOFF.md)。

## 已实现

### 档案与指纹

- 本地指纹档案管理：指纹种子、时区（56 项）、语言（39 项）、屏幕、CPU 核数、设备内存、User-Agent
- 独立持久化浏览器 profile，cookie / 登录态 / 历史按档案隔离
- 可插拔内核：CloakBrowser（默认）、Camoufox（实验性 Firefox stealth）、原生 Chromium（保底）
- TTS 语音包伪装：按档案语言重写 speechSynthesis 语音列表，修复「语音包国家 ↔ IP 国家」异常
- 指纹体检报告（面板内一键深检）：webdriver、WebRTC 泄露、Canvas 噪声、UA、已应用设置

### 代理

- HTTP / SOCKS5 代理，密码使用 Windows DPAPI 加密落盘
- 内置 Mihomo 代理：订阅导入 / 刷新 / 删除、机场节点展开、并发真实延迟测速、出口 IP 检测
- 代理 / 指纹一致性预检 + 一键修正时区

### 会话与自动化

- 一键启动 / 停止，批量启停，humanize 类人行为
- 面板直接打开网址；新标签页静态空白页 + Service Worker 跳转
- 回收站 / 档案导入导出复制（JSON）
- Local API：页面内容读取、截图（只监听 `127.0.0.1` 随机端口，Bearer token 保护）
- MCP Server：AI 助手（ZCode / Claude Desktop / Cursor）操控指纹浏览器
- CDP attach 模式：外部 Playwright / Selenium 脚本接入运行中的档案（`docs/attach.md`）
- 下载目录可选 + 下载文件名保留扩展名
- 页面原地翻译（不重载，保留表单与滚动位置）

### 数据安全

- 加密全量备份 / 恢复：档案 + 登录态打包为 AES-256 口令加密 zip
- 单实例锁
- 统一 ID 校验与安全路径拼接（`core/identifiers.py`）
- 统一退出清理（`core/shutdown.py`）

### 分发

- 双安装包（onedir / onefile），均无需管理员权限
- 中英双版 README、GitHub Pages 主页
- 首次启动自动下载 CloakBrowser 内核

## 近期候选

> 竞品对照与难度依据见下方「竞品功能调研」。以下三项经核对为低风险，建议优先。

- **档案搜索 / 筛选**：按名称、备注、指纹种子过滤档案列表（纯前端）
- **档案标签 / 分组**：给档案打标签并按标签分组、筛选
- **Cookie 导入 / 导出**：在档案之间搬运登录态，兼容常见 Cookie 格式
- **时区自动跟随代理**：启动时按出口 IP 自动对齐时区（`consistency.py` 已能检测）
- **批量指纹更新**：一次给多个档案换 seed
- **代理池管理**：集中保存、绑定档案、连通性测试、出口 IP 显示
  （注：现有 Mihomo 是**订阅式**的，与「手动集中管理一批代理」不是同一件事）
- **扩展指纹参数 UI**：WebRTC、Canvas / WebGL / WebGPU 噪声、GPU
  （注：`core/models.py` 目前无相关字段；移动端指纹另见下方难度说明）

## 中期候选

- **同步器**：多档案主控 / 被控输入同步（品类核心差异点，但工程量中等偏大）
- RPA 模板与定时任务：自动登录、批量操作、每日任务
- 档案导入迁移：Dolphin{anty}、GoLogin、Multilogin

## 后期候选

- 团队协作：成员、分组、权限、分享
- 操作日志：登录、启动、配置变更、异常提醒
- 云端可选同步（端到端加密）
- 云手机能力

---

## 竞品功能调研（2026-10-15）

来源：`TheGP/untidetect-tools`（2.0k★，30+ 厂商清单）、
`zhaotoday/fingerprint-browser`（741★，中文市场整理与定价），
以及 Dolphin{anty} / GoLogin / Multilogin / Undetectable / 比特浏览器的官网功能页。

### 竞品普遍有、而本项目缺的

按出现频率排列，并标注实现难度（难度依据为对 `src/zencloak/` 的实际核对）：

| 功能 | 谁有 | 难度 | 依据 |
|---|---|---|---|
| **档案搜索 / 筛选** | GoLogin、Dolphin | 极小 | 档案已在前端 `state.profiles`，过滤 `renderProfileList()` 即可，**无需后端改动** |
| **标签 / 分组 / 状态** | Dolphin、GoLogin、比特 | 小 | 加一个字段即可，改动面与现有 `notes` 相同（5 处） |
| **Cookie 导入 / 导出** | GoLogin、Undetectable（Cookies Converter） | 小 | 数据目录本就按档案隔离，`backup.py` 已在处理 Cookies 文件 |
| **批量指纹更新** | Dolphin | 小 | 已有 `batch-launch` / `batch-stop` 端点可照抄，只改 seed |
| **时区自动跟随代理** | 普遍（一致性预检） | 小 | `consistency.py` 的 `check_consistency()` 已能检测，只差启动时自动应用 |
| **同步器**（主控→多档案广播输入） | Dolphin、Undetectable、GoLogin、比特 | **中偏大** | 需捕获主档案输入并经 CDP 广播到多会话，涉及时序与防回环。**品类核心差异点，值得单独一轮** |
| **移动端指纹**（iOS/Android） | Dolphin、Multilogin、Kameleo、Wade | **大** | 需内核支持对应 persona，CloakBrowser 未必提供。**须先验证，同 R5** |
| **代理池管理** | 几乎所有 | 中 | 见上「近期候选」 |
| **RPA / 自动化脚本** | AdsPower、Dolphin、NSTBrowser | 大 | 见「中期候选」 |
| **团队协作 / 权限** | 全部商业版 | 大 | 见「后期候选」 |

### 本项目已具备、而多数竞品缺或不强的

- 指纹体检报告（`health.py`，多数厂商只做外链跳转）
- CDP attach（少见）
- MCP server（竞品中仅 Undetectable 提供）
- 加密全量备份（免费档中少见）
- 可插拔内核（CloakBrowser / Camoufox / Chromium）

> 结论：技术深度已不弱，缺口集中在**日常运营效率**类功能 ——
> 搜索、标签、Cookie 管理这些用户每天都要用的东西。

### 建议的下一步（按性价比）

1. **档案搜索 + 标签分组** —— 档案一多就找不到，纯前端 + 一个字段，风险最低
2. **时区自动跟随代理** —— 复用现有 `consistency.py`，消除每次手动修正的重复劳动
3. **Cookie 导入导出** —— 多账号运营高频需求，实现路径明确

三者合计工作量约等于一次主题改造。**同步器**虽为核心差异点，但因工程量与风险，建议单独立项。

---

## 整改清单交叉引用

外部评审整改项（R1–R12）见 [REMEDIATION.md](REMEDIATION.md)。当前未完成：

| 项 | 状态 |
|---|---|
| R6 指纹克隆（从本机采集生成档案） | 待做 |
| R8 `app.js` 模块化拆分（约 1300 行） | 待做，窗口已错过 |
| R5 第二步（Linux 内核可用性） | 已调查，**待定** —— 见 HANDOFF.md |

> 已从本 Roadmap 移除的原候选：批量导入/导出/复制（已实现，见「会话与自动化」）、
> 一键备份全部档案（已实现，即 R4）、双内核支持（已实现，即 R2）。
