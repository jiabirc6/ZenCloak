---
name: obscura-skill
description: Use when fetching, scraping, or automating web pages with Obscura, especially for lightweight headless browsing, screenshots, stealth scraping, CDP, Puppeteer/Playwright, or MCP browser tasks.
---

# Obscura Skill

## Overview

Obscura 是一个用 Rust 编写的轻量级 headless 浏览器，内置 V8、Chrome DevTools Protocol（CDP）和反检测能力。适用于网页抓取、截图、PDF、AI Agent 浏览器操作，以及 Puppeteer/Playwright 兼容自动化。

## 二进制位置

本机已安装：

- `C:\Users\Administrator\.codex\tools\obscura\obscura.exe`
- `C:\Users\Administrator\.codex\tools\obscura\obscura-worker.exe`

`scrape` 并行模式依赖同目录下的 `obscura-worker.exe`，不要只拷贝主程序。

## 快速参考

```powershell
# 获取页面标题
obscura fetch https://example.com --eval "document.title"

# 提取页面文本 / HTML / 链接 / Markdown
obscura fetch https://example.com --dump text
obscura fetch https://example.com --dump html
obscura fetch https://example.com --dump links
obscura fetch https://example.com --dump markdown

# 等待动态内容
obscura fetch https://example.com --wait-until networkidle0 --selector "#content"

# 截图 / 输出到文件
obscura fetch https://example.com --screenshot page.png
obscura fetch https://example.com --dump text --output page.txt

# 代理 / 反检测 / 允许内网
obscura --proxy socks5://127.0.0.1:1080 fetch https://example.com --dump text
obscura --stealth fetch https://example.com --dump text
obscura --allow-private-network fetch http://localhost:8080 --dump text
```

## 并行抓取

```powershell
obscura scrape url1 url2 url3 `
  --concurrency 25 `
  --eval "document.querySelector('h1')?.textContent" `
  --format json `
  --quiet
```

## CDP / Puppeteer / Playwright

```powershell
obscura serve --port 9222 --stealth
```

然后：

```javascript
// puppeteer-core
const browser = await puppeteer.connect({
  browserWSEndpoint: 'ws://127.0.0.1:9222/devtools/browser',
});
```

```javascript
// playwright-core
const browser = await chromium.connectOverCDP({
  endpointURL: 'ws://127.0.0.1:9222',
});
```

## MCP

```powershell
# stdio（Claude Desktop / Cursor 子进程模式）
obscura mcp

# HTTP 模式
obscura mcp --http --port 8080
```

MCP 工具包括 `browser_navigate`、`browser_snapshot`、`browser_screenshot`、`browser_click`、`browser_fill`、`browser_evaluate`、`browser_wait_for` 等。

## 常见问题

| 问题 | 解法 |
| --- | --- |
| 抓 localhost/内网被拒绝 | 加 `--allow-private-network` |
| JS 堆内存不足 | `obscura --v8-flags "--max-old-space-size=4096" fetch <url>` |
| 重型 SPA 脚本超时 | 设 `OBSCURA_SCRIPT_DEADLINE_MS=60000` |
| 并行抓取失败 | 确认 `obscura-worker.exe` 与主程序同目录 |
| 外网超时 | 加 `--proxy http://127.0.0.1:7890` |

## 参考

- 官方仓库：https://github.com/h4ckf0r0day/obscura
- 文档：https://docs.obscura.sh
