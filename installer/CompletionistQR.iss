; Setup fuer CompletionistQR (Inno Setup 6).
;
; Gebaut wird ueber  .\build_setup.ps1  im Projektordner: das Skript baut erst
; den Programmordner mit PyInstaller und ruft dann ISCC mit der Version aus
; completionistqr/__init__.py auf. Von Hand geht auch:
;
;   ISCC.exe /DAppVersion=1.0.0 installer\CompletionistQR.iss
;
; Voraussetzung: dist\CompletionistQR\ existiert (python build_exe.py --app qr).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "CompletionistQR"
#define AppPublisher "Completionist Library"
#define AppCopyright "© 2026 Mike-Dominique Horch (Completionist Library)"
#define AppExe "CompletionistQR.exe"
#define SourceDir "..\dist\CompletionistQR"

[Setup]
; Diese GUID identifiziert das Programm bei Updates und Deinstallation --
; niemals aendern, sonst steht die App zweimal in der Programmliste.
AppId={{D1F91E29-E069-4F0E-927C-98957984379B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright={#AppCopyright}
AppContact=mail@mike-horch.de
AppSupportURL=mailto:mail@mike-horch.de
DefaultDirName={autopf}\{#AppName}
DefaultGroupName=Completionist Suite
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExe}

; Ohne Adminrechte installieren (nach %LOCALAPPDATA%\Programs); wer die App
; fuer alle Benutzer will, waehlt das im ersten Dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=..\dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=..\completionistqr\assets\icon.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
DisableProgramGroupPage=yes
DisableDirPage=no
; Laufende Instanz vor dem Kopieren schliessen statt Neustart verlangen
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Der ganze PyInstaller-Ordner, inklusive _internal mit Laufzeit und Assets.
Source: "{#SourceDir}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; Lizenztexte (eigene Lizenz, Fremdkomponenten, LGPL fuer Qt/PySide6 ...)
Source: "{#SourceDir}\Lizenzen\*"; DestDir: "{app}\Lizenzen"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\CompletionistQR.md"; DestDir: "{app}"; DestName: "Liesmich.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Suite-Schluessel: andere Suite-Apps finden hier den Programmordner (core/qr_launcher.py).
Root: HKA; Subkey: "Software\CompletionistLibrary\{#AppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\CompletionistLibrary"; Flags: uninsdeletekeyifempty

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Von PyInstaller zur Laufzeit erzeugte .pyc-Reste, falls vorhanden.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

; Eigene Vorlagen und Einstellungen unter %APPDATA%\CompletionistQR bleiben
; bei der Deinstallation absichtlich erhalten.
