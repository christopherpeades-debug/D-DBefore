; Inno Setup script for D&D Before (character sheet)
#ifndef MyAppVersion
  #define MyAppVersion "1.2"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "D&D Before v1.2.exe"
#endif
#ifndef MyBuildDir
  #define MyBuildDir "dist\D&D Before v1.2"
#endif
#define MyAppName "D&D Before"
#define MyAppPublisher "DnD Before"

[Setup]
AppId={{B8C4D0E2-5F3A-6B7C-9D0E-1F2A3B4C5D6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\{#MyAppName}
DisableDirPage=no
UsePreviousAppDir=yes
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=D&D_Before_v{#MyAppVersion}_Setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark includetitlebar
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "sync_config.json"
Source: "sync_config.example.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  SyncConfigBackupPath: String;

procedure RemoveLegacyInstallDirs;
var
  LegacyDirs: TArrayOfString;
  I: Integer;
begin
  SetArrayLength(LegacyDirs, 6);
  LegacyDirs[0] := 'C:\D&D Before v1.1';
  LegacyDirs[1] := 'C:\D&D Before v1.11';
  LegacyDirs[2] := 'C:\D&D Before v1.12';
  LegacyDirs[3] := 'C:\D&D Before v1.01';
  LegacyDirs[4] := 'C:\D&D Before v1.21';
  LegacyDirs[5] := 'C:\D&D Before v1.2';
  for I := 0 to GetArrayLength(LegacyDirs) - 1 do
  begin
    if DirExists(LegacyDirs[I]) then
      DelTree(LegacyDirs[I], True, True, True);
  end;
end;

procedure BackupSyncConfig;
var
  AppSyncPath, TmpBackup: String;
begin
  AppSyncPath := ExpandConstant('{app}\sync_config.json');
  TmpBackup := ExpandConstant('{tmp}\dnd_before_sync_config.bak');
  SyncConfigBackupPath := '';
  if FileExists(AppSyncPath) then
  begin
    if CopyFile(AppSyncPath, TmpBackup, False) then
      SyncConfigBackupPath := TmpBackup;
  end;
end;

procedure RestoreSyncConfig;
var
  AppSyncPath: String;
begin
  if SyncConfigBackupPath <> '' then
  begin
    AppSyncPath := ExpandConstant('{app}\sync_config.json');
    CopyFile(SyncConfigBackupPath, AppSyncPath, False);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    BackupSyncConfig;
    RemoveLegacyInstallDirs;
  end;
  if CurStep = ssPostInstall then
    RestoreSyncConfig;
end;