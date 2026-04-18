; Installer Inno Setup per Scrinium.
; Requisiti: installare Inno Setup (https://jrsoftware.org/isinfo.php)
; e avere `dist\Scrinium.exe` già prodotto da build.bat.

#define MyAppName "Scrinium"
#define MyAppVersion "1.0.5"
#define MyAppPublisher "Avv. Roberto Arcella e Commissione Informatica del Consiglio dell'Ordine degli Avvocati di Napoli"
#define MyAppExeName "Scrinium.exe"

[Setup]
AppId={{6E8E8F8A-7D2B-4F0A-9B6B-3E3B1C8A4F11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=Scrinium-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea icona sul desktop"; GroupDescription: "Scorciatoie aggiuntive:"

[Files]
Source: "dist\Scrinium.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Avvia {#MyAppName}"; Flags: nowait postinstall skipifsilent
