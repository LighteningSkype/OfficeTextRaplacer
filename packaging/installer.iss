; Office 文字替换器 2.0.0 · Windows x64 安装版
; 编译：ISCC.exe packaging\installer.iss
; 输出：dist\OfficeTextReplacer-2.0.0-win64-setup.exe

#define AppName "Office 文字替换器"
#define AppVersion "2.0.0"
#define AppPublisher "LighteningSkype"
#define AppUrl "https://github.com/LighteningSkype/OfficeTextRaplacer"
#define AppExe "OfficeTextReplacer.exe"
#define SourceDir "..\dist-out\OfficeTextReplacer-2.0.0-win64"

[Setup]
AppId={{9B7E4C21-5A6D-4F83-8C1E-2D4A6B9F0E73}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion=2.0.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} 安装程序
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
DefaultDirName={autopf}\OfficeTextReplacer
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=OfficeTextReplacer-2.0.0-win64-setup
SetupIconFile=app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
ShowLanguageDialog=auto

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "OfficeTextReplacer-data\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 安装版不把数据写在程序目录；这里只清理可能残留的便携目录，避免误留旧备份
Type: filesandordirs; Name: "{app}\OfficeTextReplacer-data"
; Inno 只删除自己登记的文件与空目录，运行时/插件留下的空子目录会残留，这里整棵清掉
Type: filesandordirs; Name: "{app}\_internal"
