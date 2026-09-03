# CDP Attach 模式：外部脚本驱动指纹浏览器

在档案「行为」页勾选「暴露 CDP 调试端口」后启动，该档案的 CloakBrowser 会在
`127.0.0.1` 的一个随机端口上开放 Chrome DevTools Protocol。外部自动化脚本
（Playwright / Selenium / puppeteer-core）可以直接 attach 到这个已经配好指纹、
代理和持久化登录态的浏览器，无需自己管理环境。

## 获取端点

会话状态接口的 `cdp_endpoint` 字段即端点地址：

```powershell
curl.exe -H "Authorization: Bearer <API token>" http://127.0.0.1:<port>/api/sessions
```

```json
{ "profile_id": "689c6b914456", "status": "running", "cdp_endpoint": "http://127.0.0.1:53124" }
```

API token 在 `~/.zencloak/runtime/api.json`。

## Playwright 示例

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:53124")
    context = browser.contexts[0]          # ZenCloak 的持久化上下文
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://example.com")
    print(page.title())
    browser.close()                        # 只断开连接，不会关掉浏览器
```

Node.js 同理：`chromium.connectOverCDP(endpoint)`。

## 安全边界

- 端口只绑定 `127.0.0.1`，不对外网开放；但**本机任意进程都能完全控制该浏览器**
  （读 cookie、模拟输入、任意跳转）。只在受信任的机器上开启。
- 该开关按档案独立生效；不需要脚本接入时保持关闭。
- 与 ZenCloak 自身的会话循环共存：ZenCloak 仍会做新标签页清理，外部脚本的
  页面操作不受影响，但双方同时驱动同一页面可能互相干扰。