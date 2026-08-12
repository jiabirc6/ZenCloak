# ZenCloak 打包 EXE

## 生成图标

```powershell
python scripts/make_icon.py
```

输出：

- `assets/zencloak-icon.png`
- `assets/zencloak-icon.ico`

图标使用客户端品牌的绿色渐变圆角方块 + 白色大写 Z。

## 打包

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean zencloak.spec
```

输出：

- `dist/ZenCloak.exe`

## 说明

- 单文件 EXE，不显示控制台窗口
- UI 静态资源会随 EXE 一起打包
- CloakBrowser 的 stealth Chromium 二进制不在 EXE 内，首次启动会自动下载并缓存在 `~/.cloakbrowser/`
- 档案数据仍在 `~/.zencloak/`
- 单实例锁：重复启动会弹出“ZenCloak 已在运行”提示

## 冒烟测试

```powershell
dist\ZenCloak.exe --headless-ui --data-dir .\tmp-exe-smoke --port 8888
```

然后访问 `http://127.0.0.1:8888/api/health`。
