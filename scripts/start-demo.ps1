#requires -Version 7.0

param(
    [switch]$Check,
    [switch]$NoPause
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Split-Path -Parent $scriptDir
$workDir = Join-Path $appDir 'work'
if (-not (Test-Path $workDir)) {
    New-Item -ItemType Directory -Path $workDir | Out-Null
}

$embeddedPython = Join-Path $appDir 'tools\python-3.13.13-embed\python.exe'
$venvPython = Join-Path $appDir '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $python = $venvPython
} elseif (Test-Path $embeddedPython) {
    $python = $embeddedPython
} else {
    $python = 'python'
}

$publicBase = 'https://cfyyy.pythonanywhere.com'
$mainFile = Join-Path $appDir 'app\main.py'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backendOut = Join-Path $workDir "backend-$stamp.out.log"
$backendErr = Join-Path $workDir "backend-$stamp.err.log"

$expectedVersion = $null
if (Test-Path $mainFile) {
    $versionLine = Get-Content -Encoding UTF8 $mainFile |
        Where-Object { $_ -match '^SERVICE_VERSION\s*=\s*"([^"]+)"' } |
        Select-Object -First 1
    if ($versionLine -match '^SERVICE_VERSION\s*=\s*"([^"]+)"') {
        $expectedVersion = $Matches[1]
    }
}

function Get-LocalHealth {
    try {
        return Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5
    } catch {
        return $null
    }
}

function Test-LocalHealth {
    $health = Get-LocalHealth
    if (-not $health) {
        return $false
    }
    if ($expectedVersion -and $health.version -ne $expectedVersion) {
        return $false
    }
    return $true
}

function Stop-LocalMathService {
    $listening = netstat -ano | Where-Object {
        $_ -match '127\.0\.0\.1:8000\s' -and $_ -match 'LISTENING'
    }
    foreach ($line in $listening) {
        $columns = $line -split '\s+' | Where-Object { $_ }
        $processId = $columns[-1]
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -match 'python|uvicorn') {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-UvicornAvailable {
    try {
        & $python -c 'import uvicorn' *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function ConvertTo-CmdArgument {
    param(
        [string]$Value,
        [switch]$AlwaysQuote
    )

    if (-not $AlwaysQuote -and $Value -match '^[A-Za-z0-9_./:=+,-]+$') {
        return $Value
    }
    return '"' + ($Value -replace '"', '""') + '"'
}

function Start-DetachedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$StandardOutput,
        [Parameter(Mandatory = $true)]
        [string]$StandardError
    )

    $commandParts = @((ConvertTo-CmdArgument $FilePath -AlwaysQuote))
    $commandParts += $ArgumentList | ForEach-Object { ConvertTo-CmdArgument $_ }
    $commandLine = ($commandParts -join ' ') +
        ' > ' + (ConvertTo-CmdArgument $StandardOutput) +
        ' 2> ' + (ConvertTo-CmdArgument $StandardError)

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $env:ComSpec
    $startInfo.Arguments = '/d /s /c "' + $commandLine + '"'
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $process.Dispose()
}

Write-Host '[1/2] Checking local math service...'
if (Test-LocalHealth) {
    Write-Host '      Local service: OK'
} else {
    $currentHealth = Get-LocalHealth
    if ($Check) {
        if ($currentHealth) {
            Write-Host "      Local service: VERSION MISMATCH (running $($currentHealth.version), expected $expectedVersion)"
        } else {
            Write-Host '      Local service: NOT RUNNING'
        }
        exit 1
    }
    if (-not (Test-Path $python)) {
        Write-Host "      ERROR: Python not found at $python"
        exit 1
    }

    if ($currentHealth) {
        Write-Host "      Local service: restarting old version $($currentHealth.version)..."
        Stop-LocalMathService
        Start-Sleep -Seconds 2
    } else {
        Write-Host '      Local service: starting...'
    }

    if (Test-UvicornAvailable) {
        $serverMode = 'uvicorn'
        $serverArguments = @(
            '-m', 'uvicorn', 'app.main:app',
            '--host', '127.0.0.1',
            '--port', '8000'
        )
    } else {
        $serverMode = 'flask'
        $serverArguments = @(
            '-c',
            "from deploy.wsgi_app import application; application.run(host='127.0.0.1', port=8000, use_reloader=False, threaded=True)"
        )
    }

    Write-Host "      Server mode: $serverMode"
    Start-DetachedCommand `
        -FilePath $python `
        -ArgumentList $serverArguments `
        -WorkingDirectory $appDir `
        -StandardOutput $backendOut `
        -StandardError $backendErr

    $started = $false
    for ($i = 1; $i -le 15; $i++) {
        Start-Sleep -Seconds 1
        if (Test-LocalHealth) {
            $started = $true
            break
        }
    }
    if (-not $started) {
        Write-Host "      Local service: FAILED. See $backendErr"
        exit 1
    }
    Write-Host '      Local service: OK'
}

Write-Host '[2/2] Demo entries'
Write-Host '      Local demo: http://127.0.0.1:8000/demo'
Write-Host '      Local health: http://127.0.0.1:8000/health'
Write-Host "      Public demo: $publicBase/demo"
Write-Host "      Public health: $publicBase/health"
Write-Host '      Agent: https://www.coze.cn/store/agent/7687155979821481999?bot_id=true'

if (-not $Check -and -not $NoPause) {
    Write-Host ''
    Read-Host 'Press Enter to close this window'
}
