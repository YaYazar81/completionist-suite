; Setup fuer CompletionistQR Online (Inno Setup 6).
;
; Gebaut wird ueber  .\build_setup.ps1  im Ordner CompletionistQR-Online. Von Hand:
;
;   ISCC.exe /DAppVersion=1.0.0 installer\CompletionistQR-Online.iss
;
; Voraussetzung: dist\CompletionistQR-Online\ existiert (python build_exe.py).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "CompletionistQR Online"
#define AppPublisher "Completionist Library"
#define AppCopyright "© 2026 Mike-Dominique Horch (Completionist Library)"
#define AppExe "CompletionistQR-Online.exe"
#define FileBase "CompletionistQR-Online"  ; Dateinamen ohne Leerzeichen
#define SourceDir "..\dist\CompletionistQR-Online"

[Setup]
; Diese GUID identifiziert das Programm bei Updates und Deinstallation --
; niemals aendern, sonst steht die App zweimal in der Programmliste.
AppId={{6B921E42-041A-4C07-8303-E187E1A0CEF4}
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

PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=..\dist
OutputBaseFilename={#FileBase}-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
DisableProgramGroupPage=yes
DisableDirPage=no
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\Lizenzen\*"; DestDir: "{app}\Lizenzen"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "Liesmich.md"; Flags: ignoreversion
; Der Server zum Hochladen auf den eigenen Webspace (ohne config.php und Datenbank)
Source: "..\server\index.php"; DestDir: "{app}\server"; Flags: ignoreversion
Source: "..\server\config.sample.php"; DestDir: "{app}\server"; Flags: ignoreversion
Source: "..\server\.htaccess"; DestDir: "{app}\server"; Flags: ignoreversion
Source: "..\server\data\.htaccess"; DestDir: "{app}\server\data"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} – Server-Dateien"; Filename: "{app}\server"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Bis Version 1.1 hiess das Programm "QR-Online" (gleiche AppId, daher Update statt
; Zweitinstallation) -- dessen .exe und Verknuepfungen wegraeumen.
Type: files; Name: "{app}\QR-Online.exe"
Type: files; Name: "{group}\QR-Online.lnk"
Type: files; Name: "{group}\QR-Online – Server-Dateien.lnk"
Type: files; Name: "{group}\QR-Online deinstallieren.lnk"
Type: files; Name: "{group}\Uninstall QR-Online.lnk"
Type: files; Name: "{autodesktop}\QR-Online.lnk"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

; Einstellungen unter %APPDATA%\CompletionistQR Online (bis 1.1: %APPDATA%\CompletionistQR Online) bleiben bei der Deinstallation erhalten.
