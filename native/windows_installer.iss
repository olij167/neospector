#define MyAppName "Neospector"
#define MyAppVersion "0.7.25"
#define MyAppChannel "UX41"
#define MyAppExeName "Neospector.exe"
#define MyAppPublisher "Pungent Funk"
#define MyAppURL "https://omne.space/downloads/neospector"
[Setup]
AppId={{EA6A4CF5-A0E4-4D1D-89D2-4151B1CE1540}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName=Neospector 0.7.25 UX41
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL=https://omne.space/support
DefaultDirName={localappdata}\Programs\Neospector
DefaultGroupName=Neospector
DisableProgramGroupPage=no
PrivilegesRequired=lowest
OutputDir=dist-installer
OutputBaseFilename=Neospector_0.7.25-ux41_windows-x64_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
[Files]
Source: "dist\Neospector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts"; Flags: unchecked
[Icons]
Name: "{group}\Neospector"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Neospector"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Neospector"; Flags: nowait postinstall skipifsilent
