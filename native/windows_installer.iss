#ifndef NEOSPECTOR_VERSION
#define NEOSPECTOR_VERSION "0.0.0-ux0"
#endif
#define MyAppName "Neospector"
#define MyAppExeName "Neospector.exe"
#define MyAppPublisher "Pungent Funk"
[Setup]
AppId={{EA6A4CF5-A0E4-4D1D-89D2-4151B1CE1540}
AppName={#MyAppName}
AppVersion={#NEOSPECTOR_VERSION}
AppVerName=Neospector {#NEOSPECTOR_VERSION}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://omne.space/downloads/neospector
DefaultDirName={localappdata}\Programs\Neospector
DefaultGroupName=Neospector
PrivilegesRequired=lowest
OutputDir=dist-installer
OutputBaseFilename=Neospector_{#NEOSPECTOR_VERSION}_windows-x64_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
#ifdef NEOSPECTOR_SIGNED
SignTool=neospector
SignedUninstaller=yes
#endif
[Files]
Source: "dist\Neospector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Neospector"; Filename: "{app}\{#MyAppExeName}"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Neospector"; Flags: nowait postinstall skipifsilent
