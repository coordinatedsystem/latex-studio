param([switch]$NoBrowser, [switch]$CheckRuntime)

$ErrorActionPreference = 'Stop'
$release = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'version.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedBuild = $release.build
$appDir = $PSScriptRoot
$dataDir = Join-Path $appDir 'storage'
$launchLog = $null
$startupMutex = $null
$mutexHeld = $false

function Write-LaunchLog([string]$Message) {
    if ($launchLog) {
        try { Add-Content -LiteralPath $launchLog -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $Message) -Encoding UTF8 } catch { }
    }
}

function Resolve-StudioPython {
    $candidates = @((Join-Path (Split-Path -Parent $appDir) 'python\pythonw.exe'))
    if ($installation -and $installation.pythonExecutable) { $candidates += $installation.pythonExecutable }
    foreach ($name in @('pythonw.exe', 'python.exe')) {
        $commands = @(Get-Command $name -All -ErrorAction SilentlyContinue)
        foreach ($command in $commands) { $candidates += $command.Source }
    }
    $probeCode = "import sys,json,importlib.util; print(json.dumps({'version':sys.version.split()[0],'compatible':sys.version_info>=(3,10),'pdf':bool(importlib.util.find_spec('pypdf') and importlib.util.find_spec('pdfplumber'))}))"
    $seen = @{}
    $fallback = $null
    foreach ($candidate in $candidates) {
        if (-not $candidate -or $candidate -match 'WindowsApps' -or -not (Test-Path -LiteralPath $candidate)) { continue }
        $consoleExe = Join-Path (Split-Path -Parent $candidate) 'python.exe'
        if (-not (Test-Path -LiteralPath $consoleExe)) { continue }
        $key = $consoleExe.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        try {
            $output = & $consoleExe -c $probeCode 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            $probe = ($output -join "`n") | ConvertFrom-Json
            if (-not $probe.compatible) { Write-LaunchLog ('Skipped incompatible Python ' + $probe.version + ': ' + $consoleExe); continue }
            $windowless = Join-Path (Split-Path -Parent $consoleExe) 'pythonw.exe'
            $executable = $consoleExe
            if (Test-Path -LiteralPath $windowless) { $executable = $windowless }
            $result = [PSCustomObject]@{ executable=$executable; console=$consoleExe; version=$probe.version; pdf=$probe.pdf }
            if ($probe.pdf) { return $result }
            if (-not $fallback) { $fallback = $result }
        } catch { Write-LaunchLog ('Python probe failed: ' + $consoleExe) }
    }
    if ($fallback) { return $fallback }
    throw 'Python 3.10 or later was not found. Install a supported Python runtime before starting LaTeX Studio.'
}

function Open-StudioWindow([string]$url) {
    $edge = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
    if (Test-Path -LiteralPath $edge) {
        Start-Process -FilePath $edge -ArgumentList @('--new-window', ('--app=' + $url)) -WindowStyle Normal
    } else { Start-Process -FilePath $url }
}

try {
    $installation = $null
    $installationFile = Join-Path $appDir 'installation.json'
    if (Test-Path -LiteralPath $installationFile) {
        $installation = Get-Content -LiteralPath $installationFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $centralApp = Join-Path $installation.home 'app'
        if (Test-Path -LiteralPath (Join-Path $centralApp 'server.py')) { $appDir = $centralApp }
        $dataDir = Join-Path $installation.home 'data'
    }
    $null = New-Item -ItemType Directory -Path $dataDir -Force
    $launchLog = Join-Path $dataDir 'launch.log'
    $runtimeFile = Join-Path $dataDir 'runtime.json'
    $python = Resolve-StudioPython
    Write-LaunchLog ('Selected Python ' + $python.version + ': ' + $python.executable)
    if ($CheckRuntime) { $python | ConvertTo-Json -Compress; exit 0 }
    $hash = [System.Security.Cryptography.SHA256]::Create()
    $mutexKey = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($dataDir.ToLowerInvariant()))).Replace('-', '').Substring(0,16)
    $hash.Dispose()
    $startupMutex = New-Object System.Threading.Mutex -ArgumentList @($false, ('Local\LaTeXStudio-' + $mutexKey))
    try { $mutexHeld = $startupMutex.WaitOne(20000) } catch [System.Threading.AbandonedMutexException] { $mutexHeld = $true }
    if (-not $mutexHeld) { throw 'Another LaTeX Studio window is starting. Please try again shortly.' }

    if (Test-Path -LiteralPath $runtimeFile) {
        $serverInfo = $null
        try {
            $running = Get-Content -LiteralPath $runtimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $process = Get-Process -Id $running.pid -ErrorAction Stop
            $uri = [Uri]$running.url
            if ($uri.Host -ne '127.0.0.1' -or $uri.Port -lt 8808 -or $uri.Port -gt 8827) { throw 'Unexpected runtime address' }
            $tokenMatch = [regex]::Match($uri.Query, '(?:\?|&)token=([A-Za-z0-9_-]{32,128})(?:&|$)')
            if (-not $tokenMatch.Success) { throw 'Invalid local session' }
            $apiRoot = $uri.GetLeftPart([System.UriPartial]::Authority)
            $studioSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
            $studioSession.Cookies.SetCookies([Uri]$apiRoot, ('studio_token=' + $tokenMatch.Groups[1].Value + '; Path=/'))
            # Inspect state directly: an old runtime may fail to serve the landing page.
            $serverInfo = Invoke-RestMethod -Uri ($apiRoot + '/api/state') -WebSession $studioSession -TimeoutSec 3
        } catch { Write-LaunchLog 'No reachable existing service; starting a new instance.' }
        if ($serverInfo -and $serverInfo.app -eq $appDir -and $process.ProcessName -match '^pythonw?$') {
            $runtimeOK = $serverInfo.pythonVersion -and ([version]$serverInfo.pythonVersion -ge [version]'3.10')
            if ($serverInfo.serverBuild -eq $expectedBuild -and $runtimeOK -and $serverInfo.pid -eq $running.pid) {
                $response = Invoke-WebRequest -Uri ($apiRoot + '/') -UseBasicParsing -WebSession $studioSession -TimeoutSec 3
                if ($response.StatusCode -eq 200) {
                    Write-LaunchLog ('Reused healthy service on port ' + $uri.Port)
                    if (-not $NoBrowser) { Open-StudioWindow $running.url }
                    exit 0
                }
            }
            if ($serverInfo.running -or $serverInfo.packageBusy -or $serverInfo.aiBusy -or $serverInfo.pagePreviewBusy) { throw 'A task is still running. Stop or finish it before restarting LaTeX Studio.' }
            Write-LaunchLog ('Replacing an idle incompatible service on port ' + $uri.Port)
            try {
                $null = Invoke-RestMethod -Uri ($apiRoot + '/api/shutdown') -Method Post -Body '{}' -ContentType 'application/json' -WebSession $studioSession -TimeoutSec 3
                $null = $process.WaitForExit(3000)
            } catch { }
            if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        }
    }

    $stdout = Join-Path $appDir 'server.log'
    $stderr = Join-Path $appDir 'server-errors.log'
    $helper = Start-Process -FilePath $python.executable -ArgumentList @('-B', ('"' + (Join-Path $appDir 'server.py') + '"'), '--no-browser') -WorkingDirectory $appDir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 200
        if ($helper.HasExited) { throw ('Startup failed. See ' + $stderr) }
        if (-not (Test-Path -LiteralPath $runtimeFile)) { continue }
        try {
            $running = Get-Content -LiteralPath $runtimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($running.pid -ne $helper.Id) { continue }
            $response = Invoke-WebRequest -Uri $running.url -UseBasicParsing -TimeoutSec 2 -SessionVariable responseSession
            if ($response.StatusCode -eq 200) {
                $apiRoot = ([Uri]$running.url).GetLeftPart([System.UriPartial]::Authority)
                $readyState = Invoke-RestMethod -Uri ($apiRoot + '/api/state') -WebSession $responseSession -TimeoutSec 2
                if ($readyState.pid -ne $helper.Id -or $readyState.serverBuild -ne $expectedBuild) { continue }
                Write-LaunchLog ('Service ready on port ' + $running.port + ' using Python ' + $python.version)
                if (-not $NoBrowser) { Open-StudioWindow $running.url }
                exit 0
            }
        } catch { }
    }
    throw 'The local editor did not become ready in time.'
} catch {
    $message = $_.Exception.Message
    Write-LaunchLog ('ERROR: ' + $message)
    if ($NoBrowser -or $CheckRuntime) { Write-Error -Message $message -ErrorAction Continue; exit 1 }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(($message + "`n`nStartup log: " + $launchLog), 'LaTeX Studio') | Out-Null
    exit 1
} finally {
    if ($startupMutex) {
        if ($mutexHeld) { $startupMutex.ReleaseMutex() }
        $startupMutex.Dispose()
    }
}
