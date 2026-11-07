param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference='Stop'
try {
  $root=[IO.Path]::GetFullPath($Target)
  $file=Join-Path $root 'data\runtime.json'
  if(-not (Test-Path -LiteralPath $file)){exit 0}
  $runtime=Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
  $uri=[Uri]$runtime.url
  if($uri.Host -ne '127.0.0.1' -or $uri.Port -lt 8808 -or $uri.Port -gt 8827){exit 3}
  $match=[regex]::Match($uri.Query,'(?:\?|&)token=([A-Za-z0-9_-]{32,128})(?:&|$)')
  if(-not $match.Success){exit 3}
  $base=$uri.GetLeftPart([UriPartial]::Authority)
  $session=New-Object Microsoft.PowerShell.Commands.WebRequestSession
  $session.Cookies.SetCookies([Uri]$base,('studio_token='+$match.Groups[1].Value+'; Path=/'))
  try{$state=Invoke-RestMethod -Uri ($base+'/api/state') -WebSession $session -TimeoutSec 3}catch{exit 0}
  if($state.app -ne (Join-Path $root 'app') -or $state.pid -ne $runtime.pid){exit 3}
  if($state.running -or $state.packageBusy -or $state.aiBusy -or $state.pagePreviewBusy){exit 2}
  $null=Invoke-RestMethod -Uri ($base+'/api/shutdown') -Method Post -Body '{}' -ContentType 'application/json' -WebSession $session -TimeoutSec 4
  $process=Get-Process -Id $runtime.pid -ErrorAction SilentlyContinue
  if($process -and -not $process.WaitForExit(8000)){exit 4}
  exit 0
} catch {exit 4}
