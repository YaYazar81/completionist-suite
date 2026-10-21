; Setup fuer CompletionistMD (Inno Setup 6).
;
; Gebaut wird ueber  .\build_setup.ps1 -App md  im Projektordner: das Skript
; baut erst den Programmordner mit PyInstaller und ruft dann ISCC mit der
; Version aus mdeditor/__init__.py auf. Von Hand geht auch:
;
;   ISCC.exe /DAppVersion=1.0.0 installer\CompletionistMD.iss
;
; Voraussetzung: dist\CompletionistMD\ existiert
; (python build_exe.py --app md).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "CompletionistMD"
#define AppPublisher "Completionist Library"
#define AppCopyright "© 2026 Mike-Dominique Horch (Completionist Library)"
#define AppExe "CompletionistMD.exe"
#define SourceDir "..\dist\CompletionistMD"

[Setup]
; Diese GUID identifiziert das Programm bei Updates und Deinstallation --
; niemals aendern, sonst steht die App zweimal in der Programmliste.
AppId={{BBD71472-CB23-4208-A011-F09A4C2CE450}
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
SetupIconFile=..\assets\icon_md.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
DisableProgramGroupPage=yes
DisableDirPage=no
; Laufende Instanz (samt QtWebEngineProcess.exe) vor dem Kopieren schliessen
CloseApplications=yes
RestartApplications=no
; Explorer nach der .md-Registrierung benachrichtigen (Icons, "Oeffnen mit")
ChangesAssociations=yes

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Der ganze PyInstaller-Ordner, inklusive _internal mit QtWebEngine und Editor-Bundle.
Source: "{#SourceDir}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; Lizenztexte (eigene Lizenz, Fremdkomponenten, LGPL fuer Qt/PySide6 ...)
Source: "{#SourceDir}\Lizenzen\*"; DestDir: "{app}\Lizenzen"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\CompletionistMD.md"; DestDir: "{app}"; DestName: "Liesmich.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Suite-Schluessel: andere Suite-Apps finden hier den Programmordner (core/qr_launcher.py).
Root: HKA; Subkey: "Software\CompletionistLibrary\{#AppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\CompletionistLibrary"; Flags: uninsdeletekeyifempty

; .md-Zuordnung. Windows legt bei "Oeffnen mit" einen Schluessel
; Applications\CompletionistMD.exe pro EXE-Namen an und ueberschreibt ihn
; nie -- zeigt er auf einen alten Build-Pfad, landet man in einer
; Endlosschleife des Auswahldialogs. Darum zuerst den Benutzer-Schluessel
; loeschen (der sonst auch eine Installation fuer alle Benutzer verdeckt).
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}"; Flags: deletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".md"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
; Eigene ProgID, damit .md-Dateien das App-Icon bekommen und die App
; unter "Oeffnen mit" sauber (einmal) auftaucht.
Root: HKA; Subkey: "Software\Classes\{#AppName}.md"; ValueType: string; ValueName: ""; ValueData: "Markdown-Dokument"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#AppName}.md\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\{#AppName}.md\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.md\OpenWithProgids"; ValueType: string; ValueName: "{#AppName}.md"; ValueData: ""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Von PyInstaller zur Laufzeit erzeugte .pyc-Reste, falls vorhanden.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

; Einstellungen unter %APPDATA%\CompletionistPDF (gemeinsam mit CompletionistPDF)
; bleiben bei der Deinstallation absichtlich erhalten.
