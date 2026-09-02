; ZenCloak 自用内置内核版安装包
; 仅供个人 / 组织内部使用：CloakBrowser 二进制许可禁止将内核再分发或
; 打包进分发给第三方的产品（见 CloakBrowser-ref/BINARY-LICENSE.md）。
; 本脚本与产物不得上传到公开仓库。
;
; 构建：python scripts\build_bundled.py
; 前置：dist\ZenCloak\engine\chromium-*\ 已由构建脚本从本机 ~/.cloakbrowser 拷入

[Setup]
AppId={{8F7E2A2C-0A76-4B2F-9C9E-3D2E4A6C5B12}
AppName=ZenCloak
AppVersion=0.3.0
AppPublisher=jiabirc6
AppPublisherURL=https://github.com/jiabirc6/ZenCloak
AppSupportURL=https://github.com/jiabirc6/ZenCloak/issues
DefaultDirName={localappdata}\Programs\ZenCloak
DefaultGroupName=ZenCloak
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer
OutputBaseFilename=ZenCloak-Setup-0.3.0-bundled
SetupIconFile=..\assets\zencloak-icon.ico
UninstallDisplayIcon={app}\ZenCloak.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
; dist\ZenCloak 内含 engine\chromium-*\ 目录（内置 CloakBrowser 内核），
; 应用启动时检测到该目录会把 CLOAKBROWSER_CACHE_DIR 指过去，全程无需联网下载。
Source: "..\dist\ZenCloak\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ZenCloak"; Filename: "{app}\ZenCloak.exe"
Name: "{autodesktop}\ZenCloak"; Filename: "{app}\ZenCloak.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\ZenCloak.exe"; Description: "启动 ZenCloak"; Flags: nowait postinstall skipifsilent
