; Inno Setup script for D&D Before (character sheet)
#define MyAppName "D&D Before v1.12"
#define MyAppVersion "1.12"
#define MyAppPublisher "DnD Before"
#define MyAppExeName "D&D Before v1.12.exe"
#define MyBuildDir "dist\D&D Before v1.12"

[Setup]
AppId={{B8C4D0E2-5F3A-6B7C-9D0E-1F2A3B4C5D6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\{#MyAppName}
DisableDirPage=no
UsePreviousAppDir=no
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=D&D_Before_v1.12_Setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark includetitlebar
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
; Install under C:\ only — do not use AppData for application files.
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure RemoveLegacyInstallDirs;
var
  LegacyDirs: TArrayOfString;
  I: Integer;
begin
  SetArrayLength(LegacyDirs, 3);
  LegacyDirs[0] := 'C:\D&D Before v1.1';
  LegacyDirs[1] := 'C:\D&D Before v1.11';
  LegacyDirs[2] := 'C:\D&D Before v1.2';
  for I := 0 to GetArrayLength(LegacyDirs) - 1 do
  begin
    if DirExists(LegacyDirs[I]) then
      DelTree(LegacyDirs[I], True, True, True);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemoveLegacyInstallDirs;
end;