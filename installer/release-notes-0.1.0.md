# ZenCloak 0.1.0

ZenCloak 首个可安装版本，基于 CloakBrowser stealth Chromium 内核的个人指纹浏览器客户端。

## 安装

1. 下载 `ZenCloak-Setup-0.1.0.exe`
2. 双击安装，安装到当前用户目录，无需管理员权限
3. 安装完成后自动打开 ZenCloak

## 首次启动

首次启动浏览器档案时，如果本机还没有 CloakBrowser 内核，ZenCloak 会自动下载约 200MB 的 stealth Chromium 二进制并缓存在 `~/.cloakbrowser/`。

## 功能

- 多指纹档案管理
- 独立持久化浏览器 profile
- HTTP/SOCKS5 代理
- 类人行为
- 面板直接打开网址
- 代理密码 DPAPI 加密
- 单实例保护

## 说明

安装包不包含 CloakBrowser 二进制，首次运行需要联网下载内核。
