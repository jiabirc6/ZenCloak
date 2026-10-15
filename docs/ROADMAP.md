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

- **代理池管理**：集中保存、绑定档案、连通性测试、出口 IP 显示
  （注：现有 Mihomo 是**订阅式**的，与「手动集中管理一批代理」不是同一件事）
- **扩展指纹参数 UI**：WebRTC、Canvas / WebGL / WebGPU 噪声、GPU、移动端指纹
  （注：`core/models.py` 目前无相关字段）

## 中期候选

- 窗口同步：多档案主控 / 被控输入同步
- RPA 模板与定时任务：自动登录、批量操作、每日任务
- 档案导入迁移：Dolphin{anty}、GoLogin、Multilogin

## 后期候选

- 团队协作：成员、分组、权限、分享
- 操作日志：登录、启动、配置变更、异常提醒
- 云端可选同步（端到端加密）
- 云手机能力

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
