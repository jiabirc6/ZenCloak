# ZenCloak

基于 [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) stealth Chromium 构建的专属指纹浏览器桌面客户端。

## 运行

```powershell
python -m pip install -e .
python -m cloakbrowser install   # 若还未下载 stealth Chromium 二进制
python -m zencloak
```

也可以直接双击 `start-zencloak.cmd`。

首次启动会在 `~/.zencloak/` 自动创建「本地档案」。之后在面板里新建多个档案，每个档案拥有独立的指纹种子、持久化 profile、代理和类人行为设置。

注意：不要直接双击打开 `src/zencloak/ui/index.html`，请始终通过桌面程序启动。

## 功能

- 多指纹档案管理：指纹种子、时区、语言、屏幕、CPU 核数、内存、User-Agent
- HTTP / SOCKS5 代理配置
- 类人鼠标/键盘/滚动行为（`humanize`）
- 持久化会话：cookie、登录态、访问历史独立保存
- 一键启动/停止浏览器窗口
- 内置 BrowserScan、FingerprintJS、BrowserLeaks、Incolumitas 检测站点入口

## 数据

- 配置目录：`~/.zencloak/profiles/`
- 会话数据：`~/.zencloak/data/`
- 本地 API 仅监听 `127.0.0.1` 随机端口，不对外暴露

## 测试

```powershell
python -m pytest
python -m pytest tests/test_smoke_launch.py -v
```
