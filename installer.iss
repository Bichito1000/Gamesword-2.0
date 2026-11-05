; Script de Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; 1) Ejecuta CREAR_EXE.bat   2) Abre este archivo con Inno Setup y pulsa "Compilar"
[Setup]
AppName=Gamesword
AppVersion=2.0.0
AppPublisher=Gamesword
DefaultDirName={autopf}\Gamesword
DefaultGroupName=Gamesword
OutputBaseFilename=Gamesword-Setup-2.0.0
OutputDir=Output
SetupIconFile=resources\gamesword.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Gamesword
CloseApplications=yes
RestartApplications=yes
; Para firmar el instalador: configura SignTool en Inno Setup y descomenta la siguiente linea
; SignTool=minhasign

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "dist\Gamesword\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Gamesword"; Filename: "{app}\Gamesword.exe"
Name: "{autodesktop}\Gamesword"; Filename: "{app}\Gamesword.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Gamesword.exe"; Description: "Abrir Gamesword"; Flags: nowait postinstall skipifsilent
