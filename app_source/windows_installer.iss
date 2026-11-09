#define MyAppName "OmN-e Sequencer"
#ifndef MyAppVersion
#define MyAppVersion "0.3.1-r1"
#endif
#ifndef MyAppArch
#define MyAppArch "x64"
#endif
#define MyAppPublisher "OmN-e / Pungent Funk"
#define MyAppURL "https://omne.space/"
#define MyAppExeName "OmN-e Sequencer.exe"
[Setup]
AppId={{6C2B7B15-53AD-4A61-B97E-A05BE4787B86}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL=https://omne.space/support
DefaultDirName={localappdata}\Programs\OmN-e Sequencer
DefaultGroupName=OmN-e Sequencer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist-installer
OutputBaseFilename=OmN-e_Sequencer_v{#MyAppVersion}_Windows_{#MyAppArch}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
[Files]
Source: "dist\OmN-e Sequencer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\OmN-e Sequencer"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\OmN-e Sequencer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch OmN-e Sequencer"; Flags: nowait postinstall skipifsilent
