; Inno Setup script -> Output\NoMsindo-Setup.exe   (iscc installer.iss)
#define AppName "NoMsindo"
#define AppVersion "0.1.0"

[Setup]
AppId={{7D2E9B14-3A58-4F0C-8B66-5E1A0C9D2F37}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=NoMsindo-Setup
SetupIconFile=assets\nomsindo.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\NoMsindo.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
Name: "startup"; Description: "Start NoMsindo when Windows starts"

[Files]
Source: "dist\NoMsindo\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\NoMsindo.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\NoMsindo.exe"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\NoMsindo.exe"; Tasks: startup

[Run]
Filename: "{app}\NoMsindo.exe"; Description: "Launch NoMsindo"; Flags: nowait postinstall skipifsilent
