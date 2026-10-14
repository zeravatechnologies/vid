; Inno Setup script for the Vid Windows installer.
; Compiled in CI (packaging builds the PyInstaller onedir into dist\vid first):
;   iscc /DVidVersion=<version> packaging\windows\vid.iss
; Produces dist\installer\VidSetup-<version>.exe.
;
; What it does: installs Vid into Program Files, adds a Start Menu entry, and
; registers a per-user logon task so Vid runs in the background with the window
; closed (the Windows parallel of the Linux systemd user service). Uninstall
; removes the task and the files.

#ifndef VidVersion
  #define VidVersion "0.0.0-dev"
#endif

[Setup]
AppId={{B7E9F2A1-4C3D-4E5F-9A8B-1D2C3E4F5A6B}
AppName=Vid
AppVersion={#VidVersion}
AppPublisher=Zerava Technologies Inc.
AppPublisherURL=https://www.zeravatech.ca/
DefaultDirName={autopf}\Vid
DefaultGroupName=Vid
DisableProgramGroupPage=yes
UninstallDisplayName=Vid
OutputDir=..\..\dist\installer
OutputBaseFilename=VidSetup-{#VidVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

[Files]
Source: "..\..\dist\vid\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"
Source: "..\..\NOTICE"; DestDir: "{app}"; DestName: "NOTICE.txt"

[Icons]
Name: "{group}\Vid status"; Filename: "{app}\vid.exe"; Parameters: "status"; Comment: "What Vid is watching"
Name: "{group}\Uninstall Vid"; Filename: "{uninstallexe}"

[Tasks]
Name: "autostart"; Description: "Start Vid automatically when I sign in (recommended)"; GroupDescription: "Background:"

; Register (and start) a per-user logon task that runs `vid serve`. runhidden,
; so no console window. Uninstall deletes it. The task name is per-user-safe.
[Run]
Filename: "schtasks.exe"; Parameters: "/Create /TN ""Vid"" /TR ""\""{app}\vid.exe\"" serve"" /SC ONLOGON /RL LIMITED /F"; Flags: runhidden; Tasks: autostart
Filename: "schtasks.exe"; Parameters: "/Run /TN ""Vid"""; Flags: runhidden; Tasks: autostart

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/End /TN ""Vid"""; Flags: runhidden; RunOnceId: "VidStop"
Filename: "schtasks.exe"; Parameters: "/Delete /TN ""Vid"" /F"; Flags: runhidden; RunOnceId: "VidDelTask"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
