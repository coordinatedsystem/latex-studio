param(
    [Parameter(Mandatory=$true)][string]$HomeDirectory,
    [string]$DesktopDirectory = [Environment]::GetFolderPath('Desktop')
)
$ErrorActionPreference = 'Stop'
$resolvedHome = [System.IO.Path]::GetFullPath($HomeDirectory)
$launcher = Join-Path $resolvedHome 'Launch.vbs'
$iconFile = Join-Path $resolvedHome 'app\assets\studio.ico'
if (-not (Test-Path -LiteralPath $launcher)) { throw 'The installed launcher is missing.' }
if (-not (Test-Path -LiteralPath $iconFile)) { throw 'The desktop icon is missing.' }
$desktopTarget = [System.IO.Path]::GetFullPath($DesktopDirectory)
New-Item -ItemType Directory -Force -Path $desktopTarget | Out-Null
$shortcutPath = Join-Path $desktopTarget 'LaTeX Studio.lnk'
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $resolvedHome
$shortcut.IconLocation = $iconFile + ',0'
$shortcut.Description = 'LaTeX document editor, PDF compiler and package manager'
$shortcut.WindowStyle = 1
$shortcut.Save()
Write-Output $shortcutPath
