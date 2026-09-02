# ZenCloak 打包 EXE 与安装程序

## 生成图标

```powershell
python scripts/make_icon.py
```

输出：

- `assets/zencloak-icon.png`
- `assets/zencloak-icon.ico`

图标使用客户端品牌的绿色渐变圆角方块 + 白色大写 Z。

## 内核分发方式（重要）

CloakBrowser 的 stealth Chromium 二进制受 [BINARY-LICENSE.md](../CloakBrowser-ref/BINARY-LICENSE.md) 约束：**禁止再分发、禁止打包进分发给第三方的产品**。因此存在两条构建路线：

| 路线 | 内核来源 | 可否公开分发 |
|---|---|---|
| 公开版（onefile / onedir） | 安装包不含内核；安装时可选立即下载（`--install-engine`，由用户机器直接向 CloakHQ 官方通道下载），或首次启动档案时自动下载 | ✅ |
| 内置版（bundled） | 内核直接打进安装包，安装后零下载 | ❌ 仅限个人 / 组织内部使用 |

公开版的"安装时下载"合规依据：许可明确说明 *end users download the CloakBrowser Binary directly from official CloakHQ channels* 不构成再分发。

## 打包 EXE（公开 onefile 版）

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean zencloak.spec
```

输出：`dist/ZenCloak.exe`

## 打包快速启动版（公开 onedir）

单文件 EXE 每次启动需要解压依赖，约 20 秒。需要更快启动时改用 onedir 文件夹模式：

```powershell
python -m PyInstaller --noconfirm --clean zencloak-dir.spec
```

输出：`dist/ZenCloak/` 文件夹。onedir 启动约 1-2 秒，但发布物是一个目录，便携性不如单个 EXE。

## 制作安装程序（公开版）

需要 Inno Setup 6：

```powershell
winget install --id JRSoftware.InnoSetup -e
```

编译 onefile 版：

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\zencloak.iss
```

输出：`installer/ZenCloak-Setup-0.3.0.exe`

编译 onedir 版：

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\zencloak-dir.iss
```

输出：`installer/ZenCloak-Setup-0.3.0-dir.exe`

两个安装包都带一个默认不勾选的附加任务「安装后立即下载 CloakBrowser 内核」，勾选后安装完成时静默执行 `ZenCloak.exe --install-engine` 下载内核；不勾选则维持首次启动档案时自动下载。

## 构建内置内核版（仅自用）

```powershell
python scripts\build_bundled.py
```

脚本依次执行：PyInstaller onedir → 把本机 `~/.cloakbrowser/chromium-*` 拷入 `dist/ZenCloak/engine/` → 编译 `installer/zencloak-bundled.iss`。

输出：`installer/ZenCloak-Setup-0.3.0-bundled.exe`（约 600 MB+）。应用启动时检测到 `engine/chromium-*` 目录会自动把 `CLOAKBROWSER_CACHE_DIR` 指过去，全程无需联网下载内核。

> ⚠️ 该产物**只能在自己 / 组织内部机器安装使用，禁止上传 GitHub Release 或任何公开分发渠道**——违反 CloakBrowser 二进制许可。

## 发布到 GitHub Releases

```powershell
gh release create v0.3.0 installer/ZenCloak-Setup-0.3.0.exe `
  --title "ZenCloak 0.3.0" `
  --notes-file installer/release-notes-0.3.0.md
gh release upload v0.3.0 installer/ZenCloak-Setup-0.3.0-dir.exe
```

只上传公开版两个安装包；内置版不上传。

## 说明

- 单文件 EXE，不显示控制台窗口
- 安装程序安装到当前用户目录，无需管理员权限，并创建开始菜单/桌面快捷方式
- UI 静态资源会随 EXE 一起打包
- 档案数据仍在 `~/.zencloak/`
- 单实例锁：重复启动会弹出“ZenCloak 已在运行”提示
- 构建前需退出正在运行的 ZenCloak（含开发模式），否则 PyInstaller 覆盖 `dist/` 会报 PermissionError

## 冒烟测试

```powershell
dist\ZenCloak.exe --headless-ui --data-dir .\tmp-exe-smoke --port 8888
```

然后访问 `http://127.0.0.1:8888/api/health`。

内置版额外验证：安装后删除 `~/.cloakbrowser` 目录（或换台没下过内核的机器），启动档案应能直接打开浏览器——证明用的是包内 `engine/` 内核。
