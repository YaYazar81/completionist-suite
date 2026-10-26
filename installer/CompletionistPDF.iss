; Setup fuer CompletionistPDF (Inno Setup 6).
;
; Gebaut wird ueber  .\build_setup.ps1 -App pdf  im Projektordner: das Skript
; baut erst den Programmordner mit PyInstaller und ruft dann ISCC mit der
; Version aus core/__init__.py auf. Von Hand geht auch:
;
;   ISCC.exe /DAppVersion=1.0.0 installer\CompletionistPDF.iss
;
; Voraussetzung: dist\CompletionistPDF\ existiert
; (python build_exe.py --app pdf).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "CompletionistPDF"
#define AppPublisher "Completionist Library"
#define AppCopyright "© 2026 Mike-Dominique Horch (Completionist Library)"
#define AppExe "CompletionistPDF.exe"
#define SourceDir "..\dist\CompletionistPDF"

[Setup]
; Diese GUID identifiziert das Programm bei Updates und Deinstallation --
; niemals aendern, sonst steht die App zweimal in der Programmliste.
; CompletionistMD sucht CompletionistPDF ueber diese Kennung
; (APP_IDS in core/qr_launcher.py).
AppId={{D58A3655-430B-431B-81B2-5860BAE5E9C1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright={#AppCopyright}
AppContact=kontakt@completionist-library.de
AppSupportURL=mailto:kontakt@completionist-library.de
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
SetupIconFile=..\assets\icon_pdf.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
DisableProgramGroupPage=yes
DisableDirPage=no
; Laufende Instanz vor dem Kopieren schliessen statt Neustart verlangen
CloseApplications=yes
RestartApplications=no
; Explorer ueber neue Dateizuordnungen informieren (nur mit der Aufgabe pdfassoc)
ChangesAssociations=WizardIsTaskSelected('pdfassoc')

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Abwaehlbar: traegt CompletionistPDF als Programm fuer .pdf ein (Viewer-Modus).
; Windows laesst sich den Standard nicht von einem Setup vorschreiben -- die App
; erscheint unter "Oeffnen mit" und kann dort als Standard gewaehlt werden.
Name: "pdfassoc"; Description: "PDF-Dateien mit {#AppName} öffnen können (unter „Öffnen mit“)"; GroupDescription: "Dateizuordnung:"

[Files]
; Der ganze PyInstaller-Ordner, inklusive _internal mit Laufzeit, Typst und Vorlagen.
Source: "{#SourceDir}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; Lizenztexte (eigene Lizenz, Fremdkomponenten, LGPL fuer Qt/PySide6 ...)
Source: "{#SourceDir}\Lizenzen\*"; DestDir: "{app}\Lizenzen"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\CompletionistPDF.md"; DestDir: "{app}"; DestName: "Liesmich.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Suite-Schluessel: andere Suite-Apps finden hier den Programmordner (core/qr_launcher.py).
Root: HKA; Subkey: "Software\CompletionistLibrary\{#AppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\CompletionistLibrary"; Flags: uninsdeletekeyifempty

; Dateizuordnung .pdf (Aufgabe pdfassoc). HKA landet ohne Adminrechte unter
; HKCU\Software\Classes. Nur OpenWithProgids -- ein vorhandener Standard-Viewer
; bleibt Standard, bis der Nutzer selbst umstellt.
Root: HKA; Subkey: "Software\Classes\CompletionistPDF.Document"; ValueType: string; ValueName: ""; ValueData: "PDF-Dokument"; Flags: uninsdeletekey; Tasks: pdfassoc
Root: HKA; Subkey: "Software\Classes\CompletionistPDF.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: pdfassoc
Root: HKA; Subkey: "Software\Classes\CompletionistPDF.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: pdfassoc
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "CompletionistPDF.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: pdfassoc
; Ein alter Benutzer-Schluessel (z. B. auf einen frueheren Build-Pfad) wuerde
; den neuen verdecken und den "Oeffnen mit"-Dialog in eine Schleife schicken.
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExe}"; Flags: deletekey; Tasks: pdfassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: pdfassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: pdfassoc
; SupportedTypes begrenzt "Oeffnen mit" auf diese Endungen -- .md muss mit
; drin stehen, sonst verschwindet die App dort fuer Markdown-Dateien.
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Tasks: pdfassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".md"; ValueData: ""; Tasks: pdfassoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Von PyInstaller zur Laufzeit erzeugte .pyc-Reste, falls vorhanden.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

; Eigene Presets und die letzte Sitzung unter %APPDATA%\CompletionistPDF bleiben
; bei der Deinstallation absichtlich erhalten.
