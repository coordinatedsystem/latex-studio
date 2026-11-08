#ifndef Payload
  #define Payload "..\build\payload"
#endif
#ifndef Output
  #define Output "..\distribution"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
[Setup]
AppId={{4B57DB25-FD6E-4471-B660-BF66BDFA9CEB}
AppName=LaTeX Studio
AppVersion={#AppVersion}
AppPublisher=coordinatedsystem
AppPublisherURL=https://github.com/coordinatedsystem/latex-studio
AppUpdatesURL=https://github.com/coordinatedsystem/latex-studio
VersionInfoVersion={#AppVersion}.0
DefaultDirName=D:\LaTeXStudio
DefaultGroupName=LaTeX Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=yes
OutputDir={#Output}
OutputBaseFilename=LaTeX-Studio-{#AppVersion}-win64-Setup
SetupIconFile=..\assets\studio.ico
UninstallDisplayIcon={app}\app\assets\studio.ico
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Messages]
ButtonBack=< 上一步
ButtonNext=下一步 >
ButtonInstall=安装
ButtonCancel=取消
ButtonFinish=完成
ButtonBrowse=浏览...
ButtonWizardBrowse=浏览...
ClickNext=点击“下一步”继续，或点击“取消”退出。
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=即将安装 [name/ver]。%n%n升级前请先保存正在编辑的文档。
WizardSelectDir=选择安装位置
SelectDirDesc=将 [name] 安装在哪里？
SelectDirLabel3=请选择安装文件夹。更换位置不会自动迁移原有项目和设置。
SelectDirBrowseLabel=点击“下一步”继续，或点击“浏览”选择其他位置。
WizardSelectTasks=附加选项
SelectTasksDesc=选择需要的快捷方式
SelectTasksLabel2=选择附加任务，然后点击“下一步”。
WizardReady=准备安装
ReadyLabel1=现在可以安装 [name]。
ReadyLabel2a=点击“安装”开始，或点击“上一步”修改选项。
ReadyLabel2b=点击“安装”开始。
ReadyMemoDir=安装位置：
ReadyMemoTasks=附加任务：
WizardPreparing=准备安装
PreparingDesc=正在准备安装 [name]。
WizardInstalling=正在安装
InstallingLabel=正在安装 [name]，请稍候。
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
[InstallDelete]
Type: files; Name: "{app}\app\studio_usage.py"
[Files]
Source: "{#Payload}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\cache\*"; DestDir: "{app}\cache"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall
Source: "{#Payload}\Launch.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "prepare-install.ps1"; Flags: dontcopy
[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall
Name: "{app}\projects"; Flags: uninsneveruninstall
[Icons]
Name: "{group}\LaTeX Studio"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\studio.ico"
Name: "{autodesktop}\LaTeX Studio"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\studio.ico"; Tasks: desktopicon
[Run]
Filename: "{app}\python\python.exe"; Parameters: "-B ""{app}\app\bootstrap_install.py"" --home ""{app}"""; Flags: runhidden waituntilterminated
Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch.vbs"""; Description: "启动 LaTeX Studio"; Flags: postinstall nowait skipifsilent
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  ExtractTemporaryFile('prepare-install.ps1');
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{tmp}\prepare-install.ps1') + '" -Target "' + ExpandConstant('{app}') + '"',
    '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    Result := '请先保存文档并结束正在运行的任务，关闭 LaTeX Studio 后重试。项目和设置尚未被修改。';
end;
