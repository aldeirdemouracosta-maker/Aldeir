; Instalador do IAVOX para Windows (Inno Setup 6).
; Gerado pelo GitHub Actions a partir da pasta dist\IAVOX criada pelo PyInstaller.

[Setup]
AppName=IAVOX
AppVersion=1.0
AppPublisher=IAVOX
DefaultDirName={autopf}\IAVOX
DefaultGroupName=IAVOX
OutputDir=..\dist
OutputBaseFilename=IAVOX-Instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\IAVOX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\IAVOX"; Filename: "{app}\IAVOX.exe"
Name: "{autodesktop}\IAVOX"; Filename: "{app}\IAVOX.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\IAVOX.exe"; Description: "Abrir o IAVOX agora"; Flags: nowait postinstall skipifsilent
