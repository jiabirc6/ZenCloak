[Setup]
AppId={{8F7E2A2C-0A76-4B2F-9C9E-3D2E4A6C5B10}
AppName=ZenCloak
AppVersion=0.2.0
AppPublisher=jiabirc6
AppPublisherURL=https://github.com/jiabirc6/ZenCloak
AppSupportURL=https://github.com/jiabirc6/ZenCloak/issues
DefaultDirName={localappdata}\Programs\ZenCloak
DefaultGroupName=ZenCloak
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer
OutputBaseFilename=ZenCloak-Setup-0.2.0
SetupIconFile=..\assets\zencloak-icon.ico
UninstallDisplayIcon={app}\ZenCloak.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\ZenCloak.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ZenCloak"; Filename: "{app}\ZenCloak.exe"
Name: "{autodesktop}\ZenCloak"; Filename: "{app}\ZenCloak.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\ZenCloak.exe"; Description: "Launch ZenCloak"; Flags: nowait postinstall skipifsilent
