#define MyAppName "DeuDownloader"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DeuDownloader"
#define MyAppExeName "DeuDownloader.exe"

[Setup]
AppId={{8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=DeuDownloader_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=img\app.ico
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german";  MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  FFmpegPage: TOutputMsgMemoWizardPage;
  FFmpegInstalled: Boolean;

function FFmpegExists(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/c where ffmpeg >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;

procedure InstallFFmpeg();
var
  ResultCode: Integer;
begin
  WizardForm.StatusLabel.Caption := 'Installing FFmpeg...';
  Exec(
    ExpandConstant('{cmd}'),
    '/c winget install yt-dlp.FFmpeg --accept-source-agreements --accept-package-agreements',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  if ResultCode = 0 then
    FFmpegInstalled := True
  else
    MsgBox(
      'FFmpeg could not be installed automatically.' + #13#10 +
      'Please install it manually after setup:' + #13#10 +
      'winget install yt-dlp.FFmpeg',
      mbInformation, MB_OK
    );
end;

procedure WriteLanguageFile();
var
  LangDir: String;
  LangCode: String;
begin
  LangDir := ExpandConstant('{%USERPROFILE}') + '\.spotify_downloader';
  ForceDirectories(LangDir);
  if ActiveLanguage() = 'german' then
    LangCode := 'de'
  else
    LangCode := 'en';
  SaveStringToFile(LangDir + '\language', LangCode, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    WriteLanguageFile();
    if not FFmpegExists() then begin
      InstallFFmpeg();
    end else begin
      FFmpegInstalled := True;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then begin
    // Remove FFmpeg
    Exec(
      ExpandConstant('{cmd}'),
      '/c winget uninstall yt-dlp.FFmpeg --accept-source-agreements',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode
    );
    // Remove app config / data directory
    DataDir := ExpandConstant('{%USERPROFILE}') + '\.spotify_downloader';
    DelTree(DataDir, True, True, True);
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  S := '';
  if MemoDirInfo <> '' then S := S + MemoDirInfo + NewLine + NewLine;
  if MemoGroupInfo <> '' then S := S + MemoGroupInfo + NewLine + NewLine;
  if MemoTasksInfo <> '' then S := S + MemoTasksInfo + NewLine + NewLine;
  if not FFmpegExists() then
    S := S + 'FFmpeg: will be installed automatically' + NewLine;
  Result := S;
end;
