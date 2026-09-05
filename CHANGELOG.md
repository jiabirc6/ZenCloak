# ZenCloak 更新日志

## v0.4.0（2026-09-05）

自 v0.3.0 以来的 34 个提交。本轮主线：外部评审驱动的整改（REMEDIATION.md）+ 指纹可信度打磨 + 内核可插拔。

### 新增功能

- **内核可插拔（R2）**：档案可选浏览器内核——CloakBrowser（默认）、Camoufox（实验性·Firefox stealth，`pip install "zencloak[camoufox]"` + `python -m camoufox fetch`）、标准 Chromium（无隐身·保底）。指纹页内核下拉自动置灰不可用项并给安装指引
- **加密全量备份/恢复（R4）**：档案 + 登录态打包为 AES-256 口令加密 zip（排除缓存目录），运行中档案自动跳过，恢复带路径穿越防护与覆盖开关，侧栏「备份 / 恢复」入口
- **TTS 语音包伪装**：按档案语言重写 speechSynthesis 语音列表（40 个 locale 的真实 Windows SAPI 语音表），修复「语音包国家 ↔ IP 国家」检测异常；行为页可关
- **CDP attach 模式（R7）**：档案开关暴露 127.0.0.1 随机调试端口，外部 Playwright/Selenium 一行 `connect_over_cdp` 接入已配好指纹代理的浏览器，断开不影响会话
- **时区/语言全量扩充**：时区 8→56（6 大区分组）、语言 7→39（含 zh-TW/zh-HK 繁体、zh-SG 简体），选项带中文地区标注
- **UI 全新设计**：设计 token 体系重写样式；工具栏收敛为「停止/启动/保存 + 更多菜单」；检测站点改图标组与 URL 栏同一行
- **英文 README**（README.en.md）+ 中英互链

### 修复

- **消除翻译按钮自我指纹泄露**（安全）：原所有档案向每个网页注入固定 `#zencloakTranslateBtn`，一行 JS 即可关联全部档案；现默认不注入（右键菜单/快捷键保留），开启时宿主元素 id 按 seed 派生 + closed Shadow DOM，页面零产品名字面量
- **rAF 帧间隔异常**：禁用 Chromium 原生窗口遮挡检测（CalculateNativeWinOcclusion），窗口被盖住不再降帧到非标准刷新率（67ms 类检测项消失）
- **mihomo 孤儿进程残留**：PID 文件 + 托盘退出同步清理 + 启动时按进程镜像名校验清扫（防 PID 复用误杀）
- **list_pages MCP 校验错误**：返回 JSON 字符串与 `list[dict]` 注解不符导致 Pydantic 报错
- **出口国家比较**：一致性预检按 ISO 码比较（此前全名比较误报）
- **新标签页转圈**：CDP 层清扫全部三方 NTP 变体、修复双标签与崩溃恢复下的失控建页
- **手动代理校验**：启用无 host/port 时的友好提示
- **打包/依赖 pin**：cloakbrowser<0.4、playwright 1.60.x 上界

### 工程与文档

- 系统要求放宽为 Windows 10/11（DPAPI 两者可用）
- 外部评审整改计划（docs/REMEDIATION.md，12 项中已完成 9 项）
- 打包指南按 0.3.0 线重写（post-install 下载内核 + 内置内核内部构建）

### 已知边界

- Camoufox 为实验性内核：上游维护断档过一年；Firefox 登录态数据与 Chromium 不互通；无 CDP attach
- 现有 Chromium 指纹档案不建议迁移到 Camoufox（指纹突变对账号风控风险高）
- 机场 IDC 节点仍会被 IP 风控站标记（节点属性，非软件可解）
