# ZenCloak 0.4.0

基于 CloakBrowser stealth 内核的个人指纹浏览器，本轮新增内核可插拔、加密备份、CDP attach、TTS 语音伪装等能力。完整变更见 [CHANGELOG.md](CHANGELOG.md)。

## 新增功能

- **内核可插拔**：档案可选 CloakBrowser（默认）/ Camoufox（实验性 Firefox stealth）/ 标准 Chromium（保底），指纹页内核下拉 + 可用性检测
- **加密全量备份/恢复**：档案 + 登录态打包为 AES-256 口令加密 zip（排除缓存），运行中档案自动跳过，恢复带路径穿越防护；侧栏「备份 / 恢复」
- **TTS 语音包伪装**：按档案语言重写 speechSynthesis 语音列表（40 个 locale 真实 Windows SAPI 语音表），消除「语音包国家 ↔ IP 国家」检测异常
- **CDP attach 模式**：档案开关暴露本地调试端口，外部 Playwright/Selenium 可 `connect_over_cdp` 接入已配好指纹与代理的浏览器（见 docs/attach.md）
- **时区 8→56 / 语言 7→39**：全主流地区分组，含 zh-TW/zh-HK 繁体与 zh-SG 简体，选项带中文标注
- **UI 全新设计**：设计 token 体系 + 工具栏「更多」菜单 + 检测站点图标组一行

## 安全与隐身修复

- 移除翻译按钮的固定 DOM 注入（原先每个网页都有 `#zencloakTranslateBtn`，可被用来关联全部档案）；默认不注入，开启时 seed 派生 id + Shadow DOM
- 修复 rAF 帧间隔异常：禁用原生窗口遮挡检测，窗口被盖住不再降帧
- 修复 mihomo 强杀后的孤儿进程残留（PID 文件 + 启动清扫，防 PID 复用误杀）
- 修复 list_pages MCP 校验错误
- 一致性预检改用 ISO 国家码比较

## 安装

下载 `ZenCloak-Setup-0.4.0.exe` 双击安装，无需管理员权限。首次启动档案时自动下载约 200MB CloakBrowser 内核到 `~/.cloakbrowser/`；也可以安装时勾选「安装后立即下载内核」。

## 环境要求

Windows 10 / 11（x64）

## 已知边界

- Camoufox 为实验性内核（上游维护断档过一年），Firefox 登录态数据与 Chromium 不互通、无 CDP attach；现有 Chromium 档案不建议迁移
- 机场 IDC 节点仍会被 IP 风控站标记，属节点属性，非软件可解