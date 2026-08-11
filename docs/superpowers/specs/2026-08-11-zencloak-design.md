# ZenCloak 专属指纹浏览器 — 设计规格

## 目标

在 CloakBrowser（stealth Chromium 二进制 + Playwright 包装层）之上，构建一个 Windows 桌面客户端，让本机用户以“指纹档案”为单位管理、启动、停止多个持久化浏览器身份。

## 架构

```
pywebview (Edge WebView2 窗口)
        │
        ▼
FastAPI + uvicorn (127.0.0.1 随机端口)
        │
        ├── core/profiles  档案 JSON 存储 (~/.zencloak/profiles)
        ├── core/fingerprint  指纹参数生成与规范化
        └── core/sessions  CloakBrowser launch_persistent_context 会话管理
```

- 所有数据只存在本机 `~/.zencloak/`，不依赖外部账号。
- 桌面窗口通过 pywebview 加载本地 UI；无窗口模式（`--headless-ui`）供测试。
- 会话在后台线程中持有 Playwright BrowserContext，UI 不阻塞。

## 数据模型

`Profile` 字段：

- `id`: 12 位十六进制 ID
- `name`, `color`, `notes`
- `seed`: 10000-99999 固定指纹种子
- `timezone`: IANA 时区，默认 `Asia/Shanghai`
- `locale`: 默认 `zh-CN`
- `platform`: 固定 `windows`
- `screen_width`, `screen_height`: 默认 1920x1080
- `hardware_concurrency`: 2/4/8/12/16
- `device_memory`: 4/8/16/32
- `user_agent`: 可空，空则交给 CloakBrowser
- `proxy`: `{type, host, port, username, password}` 或 null
- `humanize`: bool，默认 false
- `human_preset`: `default` | `careful` | `quick`
- `start_url`: 可空
- `headless`: 恒为 false（桌面使用）
- `created_at`, `updated_at`

## API

- `GET /api/health`
- `GET /api/profiles`
- `POST /api/profiles`
- `GET /api/profiles/{id}`
- `PUT /api/profiles/{id}`
- `DELETE /api/profiles/{id}`
- `GET /api/sessions`
- `POST /api/sessions/{profile_id}/launch`
- `POST /api/sessions/{profile_id}/stop`
- `GET /api/engine`

## 会话状态机

`stopped -> launching -> running -> stopping -> stopped`，异常进入 `error` 并保留错误信息。同一档案同时只允许一个会话。应用退出时自动停止全部会话。

## 安全

- API 只监听 `127.0.0.1`，随机端口。
- 代理密码先按明文保存在用户目录 JSON；后续可选 Windows DPAPI 加密。
- 不写任何日志文件，错误仅返回给 UI。

## 测试策略

- `core/fingerprint`、`core/profiles`、`core/sessions`：pytest 单测，sessions 注入 fake launcher。
- API：FastAPI TestClient。
- 集成：真实 CloakBrowser 冒烟测试（临时 profile，headless，验证 `navigator.webdriver === false`）。
- UI：启动本地服务后用 Playwright/Chrome 截图与交互检查。
