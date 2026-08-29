# ZenCloak MCP Server

ZenCloak 内置 MCP（Model Context Protocol）服务器，让支持 MCP 的 AI 助手（ZCode、Claude Desktop、Cursor 等）直接操控你的指纹浏览器档案。

## 工作原理

```
AI 助手 (MCP 客户端)
   │  stdio
   ▼
zencloak-mcp 进程（本模块）
   │  HTTP + Bearer token（自动发现）
   ▼
ZenCloak 桌面应用（本地 FastAPI）
   │  会话队列
   ▼
CloakBrowser 指纹浏览器窗口
```

- MCP 服务器以 stdio 方式由 AI 客户端按需拉起，是一个独立的轻量进程。
- 它通过 `~/.zencloak/runtime/api.json` 自动发现正在运行的 ZenCloak（应用启动时写入 `base_url` + `token`，退出时删除）。**必须先启动 ZenCloak 桌面应用，MCP 工具才能工作。**
- 所有请求只访问 `127.0.0.1`，token 不出本机。

## 客户端配置

前提：`pip install -e .`（或安装包含新版的包）。

### ZCode

在 MCP 配置中添加：

```json
{
  "mcpServers": {
    "zencloak": {
      "command": "zencloak-mcp"
    }
  }
}
```

### Claude Desktop / Cursor 等

`claude_desktop_config.json`（或对应配置文件）：

```json
{
  "mcpServers": {
    "zencloak": {
      "command": "python",
      "args": ["-m", "zencloak.mcp"]
    }
  }
}
```

> 用打包版 EXE 的用户暂请使用开发模式（`python -m zencloak`）运行主程序；后续版本会把 MCP 入口一并打进安装包。

## 工具列表

| 工具 | 说明 |
|---|---|
| `list_profiles` | 列出全部指纹档案 |
| `list_sessions` | 列出会话状态（哪些在运行） |
| `launch_session` | 启动某档案的浏览器窗口 |
| `stop_session` | 停止某档案的浏览器窗口 |
| `open_url` | 在某档案浏览器里打开网址 |
| `list_pages` | 列出某档案当前打开的标签页（索引/URL/标题） |
| `read_page` | 读取某标签页正文文本（可限制长度） |
| `screenshot_page` | 对某标签页截图，返回 PNG 路径 |
| `fingerprint_health_check` | 跑指纹体检，返回 pass/warn/fail 检查项 |
| `check_consistency` | 检查时区/语言与代理出口 IP 的一致性 |

## 示例指令

配置好后可以直接对 AI 助手说：

- 「列出我的所有档案和运行状态」
- 「启动 2026.08.10 jabir 这个档案，打开 https://browserleaks.com/javascript，把页面里的语言和时区读给我」
- 「对所有运行中的档案跑一次指纹体检，汇总警告项」
- 「给某个档案的当前页面截图」

## 安全说明

- token 每次启动随机生成，只写入本机用户目录，MCP 进程与本机 API 通信。
- MCP 服务器没有任何网络监听；它只作为客户端去连 ZenCloak 的本地 API。
- AI 助手能做的事 = 上述工具能做的事，不会获得文件系统或 shell 权限。
