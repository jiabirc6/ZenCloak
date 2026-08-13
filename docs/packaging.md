# ZenCloak 打包 EXE 与安装程序

## 生成图标

```powershell
python scripts/make_icon.py
```

输出：

- `assets/zencloak-icon.png`
- `assets/zencloak-icon.ico`

图标使用客户端品牌的绿色渐变圆角方块 + 白色大写 Z。

## 打包 EXE

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean zencloak.spec
```

输出：`dist/ZenCloak.exe`

## 打包快速启动版（onedir）

单文件 EXE 每次启动需要解压依赖，约 20 秒。需要更快启动时改用 onedir 文件夹模式：

```powershell
python -m PyInstaller --noconfirm --clean zencloak-dir.spec
```

输出：`dist/ZenCloak/` 文件夹。onedir 启动约 1-2 秒，但发布物是一个目录，便携性不如单个 EXE。

制作 onedir 安装包：

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\zencloak-dir.iss
```

输出：`installer/ZenCloak-Setup-0.1.0-dir.exe`

## 制作安装程序

需要 Inno Setup 6：

```powershell
winget install --id JRSoftware.InnoSetup -e
```

编译：

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\zencloak.iss
```

输出：`installer/ZenCloak-Setup-0.1.0.exe`

## 发布到 GitHub Releases

```powershell
gh release create v0.1.0 installer/ZenCloak-Setup-0.1.0.exe `
  --title "ZenCloak 0.1.0" `
  --notes-file installer/release-notes-0.1.0.md
```

## 说明

- 单文件 EXE，不显示控制台窗口
- 安装程序安装到当前用户目录，无需管理员权限，并创建开始菜单/桌面快捷方式
- UI 静态资源会随 EXE 一起打包
- CloakBrowser 的 stealth Chromium 二进制不在安装包内，首次启动浏览器档案时会自动下载并缓存在 `~/.cloakbrowser/`
- 档案数据仍在 `~/.zencloak/`
- 单实例锁：重复启动会弹出“ZenCloak 已在运行”提示

## 冒烟测试

```powershell
dist\ZenCloak.exe --headless-ui --data-dir .\tmp-exe-smoke --port 8888
```

然后访问 `http://127.0.0.1:8888/api/health`。
