#define AppName "VintDesk"
#define AppVersion "1.0.0"
[Setup]
AppId={{01E19EA8-64F2-4A3B-9717-92CB0EA40AF9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Lorenzo
DefaultDirName={localappdata}\Programs\VintDesk
DefaultGroupName=VintDesk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\output
OutputBaseFilename=VintDesk-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\vintdesk.ico
UninstallDisplayIcon={app}\VintDesk.exe
CloseApplications=yes
[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; GroupDescription: "Collegamenti:"; Flags: unchecked
[Files]
Source: "..\dist\VintDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\VintDesk"; Filename: "{app}\VintDesk.exe"
Name: "{autodesktop}\VintDesk"; Filename: "{app}\VintDesk.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\VintDesk.exe"; Description: "Avvia VintDesk"; Flags: nowait postinstall skipifsilent
; Dati utente in LOCALAPPDATA\VintDesk: preservati dopo disinstallazione.
