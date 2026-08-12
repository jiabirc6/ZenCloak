# ZenCloak Roadmap

按阶段排列，仅作规划，不承诺时间。完整对标分析见 [adspower-comparison.md](adspower-comparison.md)。

## 已实现

- 本地指纹档案管理
- 独立持久化浏览器 profile
- HTTP/SOCKS5 代理
- humanize 类人行为
- 面板直接打开网址
- 单实例锁
- 代理密码 DPAPI 加密
- 新标签页静态空白页 + Service Worker 跳转

## 近期候选

- 档案批量导入 / 导出 / 复制（JSON/CSV）
- 代理池管理：集中保存、绑定档案、连通性测试、出口 IP 显示
- 扩展指纹参数 UI：WebRTC、Canvas/WebGL/WebGPU 噪声、GPU、移动端指纹
- Local API 完善：统一 REST 接口、启动/停止/打开 URL、AI Agent 对接
- 删除档案进回收站，支持恢复
- 一键备份全部档案到本地压缩包

## 中期候选

- MCP Server：让 Claude/Cursor 等 AI 直接操控指纹浏览器
- 窗口同步：多档案主控/被控输入同步
- RPA 模板与定时任务：自动登录、批量操作、每日任务
- 内置指纹体检报告：一键展示 BrowserScan / FingerprintJS 结果
- 档案导入迁移：Dolphin{anty}、GoLogin、Multilogin

## 后期候选

- 团队协作：成员、分组、权限、分享
- 操作日志：登录、启动、配置变更、异常提醒
- 云端可选同步（端到端加密）
- 双内核支持（Chrome/Firefox）
- 云手机能力
