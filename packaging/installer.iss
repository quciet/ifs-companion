#define AppVersion "0.1.0"
[Setup]
AppId={{36E1A6E2-60A5-47D0-A947-11A716ED46B6}
AppName=IFsCompanion
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\IFsCompanion
DefaultGroupName=IFsCompanion
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\release
OutputBaseFilename=IFsCompanion-Setup-{#AppVersion}-win-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
InfoBeforeFile=INSTALLATION_NOTICE.txt
UninstallDisplayIcon={app}\IFsCompanion.exe
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
[Files]
Source: "..\dist\IFsCompanion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build-tools\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy
[InstallDelete]
Type: files; Name: "{userdesktop}\IFs Model Vetting.lnk"
Type: files; Name: "{userprograms}\IFs Model Vetting\IFs Model Vetting.lnk"
[Icons]
Name: "{userprograms}\IFsCompanion\IFsCompanion"; Filename: "{app}\IFsCompanion.exe"
Name: "{userdesktop}\IFsCompanion"; Filename: "{app}\IFsCompanion.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\IFsCompanion.exe"; Description: "Open IFsCompanion"; Flags: nowait postinstall skipifsilent
[Code]
function HasWebView2: Boolean;
var Version: String;
begin
  Result := (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
  if not Result then
    Result := (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var ResultCode: Integer;
begin
  Result := '';
  if not HasWebView2 then begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Result := 'Unable to start WebView2 setup. Check your connection and retry.'
    else if not HasWebView2 then
      Result := 'WebView2 could not be installed. Connect to the internet and retry setup. Exit code: ' + IntToStr(ResultCode);
  end;
end;
