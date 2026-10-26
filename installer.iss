#define MyAppName "DeuMediaDownloader"
; Taken from the version resource of the .exe (APP_VERSION in backend/config.py).
#define MyAppVersion GetStringFileInfo(AddBackslash(SourcePath) + "dist\DeuMediaDownloader.exe", "ProductVersion")
#if MyAppVersion == ""
  #error dist\DeuMediaDownloader.exe has no version resource, build it with build.py
#endif
#define MyAppPublisher "DeuMediaDownloader"
#define MyAppExeName "DeuMediaDownloader.exe"
; Remembers which tools this setup installed, so the uninstaller (and the app's
; "Uninstall FFmpeg" button) only removes what was not there before.
#define StateKey "Software\DeuMediaDownloader"
; Official Windows build of Deno, always the latest release.
#define DenoZipUrl "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

[Setup]
AppId={{8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#GetVersionNumbersString(AddBackslash(SourcePath) + "dist\DeuMediaDownloader.exe")}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=DeuMediaDownloader_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=img\app.ico
MinVersion=10.0
; Writes Setup Log <date>.txt to %TEMP%, useful when a tool could not be installed.
SetupLogging=yes
#ifdef SIGN
; build.py defines SIGN and the "dmdsign" tool when a code signing certificate is configured.
SignTool=dmdsign
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german";  MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[UninstallDelete]
; Deno downloaded by the setup (see DownloadDeno)
Type: filesandordirs; Name: "{app}\deno"

[Icons]
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Key = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2Wow = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

var
  FFmpegPage: TOutputMsgMemoWizardPage;
  FFmpegInstalled: Boolean;
  DenoInstalled: Boolean;

function WebView2Installed(): Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, WebView2Wow, 'pv', Version) or
    RegQueryStringValue(HKLM, WebView2Key, 'pv', Version) or
    RegQueryStringValue(HKCU, WebView2Key, 'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
end;

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
  if ResultCode = 0 then begin
    FFmpegInstalled := True;
    RegWriteDWordValue(HKLM, '{#StateKey}', 'FFmpegInstalledBySetup', 1);
  end else
    MsgBox(
      'FFmpeg could not be installed automatically.' + #13#10 +
      'Please install it manually after setup:' + #13#10 +
      'winget install yt-dlp.FFmpeg',
      mbInformation, MB_OK
    );
end;

// yt-dlp needs a JavaScript runtime for YouTube (signature solving, see yt-dlp-ejs).
function DenoExists(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/c where deno >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (Result and (ResultCode = 0)) or
    FileExists(ExpandConstant('{app}\deno\deno.exe')) or
    FileExists(ExpandConstant('{%USERPROFILE}') + '\.deno\bin\deno.exe') or
    FileExists(ExpandConstant('{localappdata}') + '\Microsoft\WinGet\Links\deno.exe');
end;

// Deno is a single deno.exe. The setup downloads the official release zip into {app}\deno,
// so it works without winget (winget's portable install fails in the elevated setup on some
// systems) and the uninstaller removes it together with the app.
function DownloadDeno(): Boolean;
var
  ResultCode: Integer;
  ZipFile, DestDir: String;
begin
  ZipFile := ExpandConstant('{tmp}\deno.zip');
  DestDir := ExpandConstant('{app}\deno');
  Exec(
    'powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = ''SilentlyContinue''; ' +
    '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ' +
    'Invoke-WebRequest -UseBasicParsing -Uri ''{#DenoZipUrl}'' -OutFile ''' + ZipFile + '''; ' +
    'Expand-Archive -Force -Path ''' + ZipFile + ''' -DestinationPath ''' + DestDir + '''"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Result := FileExists(DestDir + '\deno.exe');
  if not Result then
    Log(Format('Deno download failed (exit code %d)', [ResultCode]));
end;

function WingetInstallDeno(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(
    ExpandConstant('{cmd}'),
    '/c winget install --exact --id DenoLand.Deno --scope user --accept-source-agreements --accept-package-agreements',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);
  if Result then
    RegWriteDWordValue(HKLM, '{#StateKey}', 'DenoInstalledBySetup', 1)
  else
    Log(Format('winget install DenoLand.Deno failed (exit code %d)', [ResultCode]));
end;

procedure InstallDeno();
begin
  WizardForm.StatusLabel.Caption := 'Installing Deno (JavaScript runtime for YouTube)...';
  DenoInstalled := DownloadDeno() or WingetInstallDeno();
  if not DenoInstalled then
    MsgBox(
      'Deno could not be installed automatically.' + #13#10 +
      'Without it some YouTube formats may be missing. Install it later with:' + #13#10 +
      'winget install DenoLand.Deno',
      mbInformation, MB_OK
    );
end;

procedure InstallWebView2();
var
  ResultCode: Integer;
  SetupFile: String;
begin
  WizardForm.StatusLabel.Caption := 'Installing Microsoft Edge WebView2 Runtime...';
  SetupFile := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
  Exec(
    ExpandConstant('{cmd}'),
    '/c powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri ''https://go.microsoft.com/fwlink/p/?LinkId=2124703'' -OutFile ''' + SetupFile + '''"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  if (ResultCode = 0) and FileExists(SetupFile) then
    Exec(SetupFile, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if not WebView2Installed() then
    MsgBox(
      'The Microsoft Edge WebView2 Runtime could not be installed automatically.' + #13#10 +
      'DeuMediaDownloader needs it to start. Please install it from:' + #13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/',
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
    if not WebView2Installed() then begin
      InstallWebView2();
    end;
    if not FFmpegExists() then begin
      InstallFFmpeg();
    end;
    if not DenoExists() then begin
      InstallDeno();
    end;
  end;
end;

function InstalledBySetup(Name: String): Boolean;
var
  Value: Cardinal;
begin
  Result := RegQueryDWordValue(HKLM, '{#StateKey}', Name, Value) and (Value = 1);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then begin
    // Only remove tools this setup installed; a FFmpeg or Deno the user had before stays.
    if InstalledBySetup('FFmpegInstalledBySetup') then
      Exec(
        ExpandConstant('{cmd}'),
        '/c winget uninstall yt-dlp.FFmpeg --accept-source-agreements',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode
      );
    if InstalledBySetup('DenoInstalledBySetup') then
      Exec(
        ExpandConstant('{cmd}'),
        '/c winget uninstall DenoLand.Deno --accept-source-agreements',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode
      );
    RegDeleteKeyIncludingSubkeys(HKLM, '{#StateKey}');
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
  if not WebView2Installed() then
    S := S + 'Microsoft Edge WebView2 Runtime: will be installed automatically' + NewLine;
  if not FFmpegExists() then
    S := S + 'FFmpeg: will be installed automatically' + NewLine;
  if not DenoExists() then
    S := S + 'Deno (JavaScript runtime for YouTube): will be installed automatically' + NewLine;
  Result := S;
end;
