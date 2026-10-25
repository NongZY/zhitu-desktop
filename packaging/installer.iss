#define AppVersion "0.2.0-test.2"
#ifndef BundleDir
  #define BundleDir "..\dist\ZhiTu-0.2.0-test.2"
#endif

[Setup]
AppId={{9772E33F-E917-4CCE-AF23-A76FE1919125}
AppName=知途（测试版）
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\ZhiTuTest
DefaultGroupName=知途（测试版）
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist\installers
OutputBaseFilename=ZhiTu-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\知途.exe
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
InfoBeforeFile=TESTING.txt

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\知途（测试版）"; Filename: "{app}\知途.exe"
Name: "{autodesktop}\知途（测试版）"; Filename: "{app}\知途.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\知途.exe"; Description: "打开知途"; Flags: nowait postinstall skipifsilent

; User data under LocalAppData\ZhiTu is deliberately absent from uninstall actions.

[Code]
function WebViewInstalled(): Boolean;
var
  Version: String;
  Major: Integer;
begin
  Result := False;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
     RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
  begin
    Major := StrToIntDef(Copy(Version, 1, Pos('.', Version) - 1), 0);
    Result := Major >= 86;
  end;
end;

function InitializeSetup(): Boolean;
var
  NetRelease: Cardinal;
begin
  Result := False;
  if not WebViewInstalled() then
  begin
    MsgBox('需要先安装 Microsoft Edge WebView2 Runtime。请从微软官方网站安装后重试：https://developer.microsoft.com/microsoft-edge/webview2/ 。本测试包不会自动下载运行时。', mbError, MB_OK);
    exit;
  end;
  if not RegQueryDWordValue(HKLM32, 'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full', 'Release', NetRelease) or (NetRelease < 394802) then
  begin
    MsgBox('需要 .NET Framework 4.6.2 或更新版本，请完成 Windows 运行时安装后重试。', mbError, MB_OK);
    exit;
  end;
  Result := True;
end;
