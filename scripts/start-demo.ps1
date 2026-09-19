param(
    [switch]$Check,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Split-Path -Parent $scriptDir
$projectDir = Split-Path -Parent $appDir
$workDir = Join-Path $projectDir 'work'
if (-not (Test-Path $workDir)) {
    New-Item -ItemType Directory -Path $workDir | Out-Null
}

$embeddedPython = Join-Path $appDir 'tools\python-3.13.13-embed\python.exe'
$venvPython = Join-Path $appDir '.venv\Scripts\python.exe'
if (Test-Path $embeddedPython) {
    $python = $embeddedPython
} elseif (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = 'python'
}
$node = Join-Path $env:ProgramFiles 'nodejs\node.exe'
$npx = Join-Path $env:ProgramFiles 'nodejs\npx.cmd'
$publicBase = 'https://zhixi-gaoshu-2026.loca.lt'
$pidFile = Join-Path $workDir 'tunnel.pid'
$mainFile = Join-Path $appDir 'app\main.py'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tunnelOut = Join-Path $workDir "localtunnel-$stamp.out.log"
$tunnelErr = Join-Path $workDir "localtunnel-$stamp.err.log"
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

function Test-PublicHealth {
    if (Test-Path $node) {
        try {
            $json = & $node -e "fetch(process.argv[1],{headers:{'bypass-tunnel-reminder':'true'},signal:AbortSignal.timeout(5000)}).then(async r=>{if(!r.ok)process.exit(1);process.stdout.write(await r.text())}).catch(()=>process.exit(1))" "$publicBase/health" 2>$null
            if ($LASTEXITCODE -eq 0 -and $json) {
                $health = $json | ConvertFrom-Json
                if ($expectedVersion -and $health.version -ne $expectedVersion) {
                    return $false
                }
                return $true
            }
        } catch {
            # Fall back to PowerShell when Node is unavailable or blocked.
        }
    }

    try {
        $health = Invoke-RestMethod -Uri "$publicBase/health" -Headers @{
            'bypass-tunnel-reminder' = 'true'
        } -TimeoutSec 10
        if ($expectedVersion -and $health.version -ne $expectedVersion) {
            return $false
        }
        return $true
    } catch {
        return $false
    }
}

function Stop-ProjectTunnel {
    if (-not (Test-Path $pidFile)) {
        return
    }
    $savedPid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($savedPid) {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
        & taskkill.exe /PID $savedPid /T /F 2>$null | Out-Null
        $ErrorActionPreference = $previousPreference
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
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
        [string]$StandardError,
        [switch]$PassThru
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

    if ($PassThru) {
        return $process
    }

    $process.Dispose()
}

Write-Host '[1/3] Checking local math service...'
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
    Write-Host '      Starting local math service...'
    Start-DetachedCommand `
        -FilePath $python `
        -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' `
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
    if ($started) {
        Write-Host '      Local service: OK'
    } else {
        Write-Host "      Local service: FAILED. See $backendErr"
        exit 1
    }
}

Write-Host '[2/3] Checking tunnel process...'
if (Test-PublicHealth) {
    Write-Host '      Tunnel: public health OK'
} else {
    if ($Check) {
        Write-Host '      Tunnel: NOT READY'
        exit 1
    }
    if (-not (Test-Path $npx)) {
        Write-Host "      ERROR: npx not found at $npx"
        exit 1
    }
    Write-Host '      Tunnel: restarting...'
    Stop-ProjectTunnel
    $env:npm_config_cache = Join-Path $workDir 'npm-cache'
    $tunnelProcess = Start-DetachedCommand `
        -FilePath $npx `
        -ArgumentList '--yes','localtunnel','--port','8000','--local-host','127.0.0.1','--subdomain','zhixi-gaoshu-2026' `
        -WorkingDirectory $appDir `
        -StandardOutput $tunnelOut `
        -StandardError $tunnelErr `
        -PassThru
    Set-Content -Path $pidFile -Value $tunnelProcess.Id -Encoding ASCII
    $tunnelReady = $false
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-PublicHealth) {
            $tunnelReady = $true
            break
        }
        if ($tunnelProcess.HasExited) {
            break
        }
    }
    if (-not $tunnelReady) {
        Write-Host "      Tunnel: FAILED. See $tunnelErr"
        if (Test-Path $tunnelOut) {
            $assignedUrl = Get-Content $tunnelOut -ErrorAction SilentlyContinue |
                Where-Object { $_ -match 'your url is' } |
                Select-Object -Last 1
            if ($assignedUrl) {
                Write-Host "      $assignedUrl"
                Write-Host "      Expected fixed URL: $publicBase"
            }
        }
        if (Test-Path $tunnelErr) {
            Get-Content $tunnelErr -Tail 10 -ErrorAction SilentlyContinue |
                ForEach-Object { Write-Host "      $_" }
        }
        exit 1
    }
    Write-Host '      Tunnel: public health OK'
}

if (Test-Path $tunnelOut) {
    $urlLine = Get-Content $tunnelOut -ErrorAction SilentlyContinue | Where-Object { $_ -match 'your url is' } | Select-Object -Last 1
    if ($urlLine) {
        Write-Host "      $urlLine"
    }
}

Write-Host '[3/3] Demo entries'
Write-Host '      Agent: https://www.coze.cn/store/agent/7687155979821481999?bot_id=true'
Write-Host "      Verify endpoint: $publicBase/verify-query"
Write-Host "      Integrate endpoint: $publicBase/integrate-query"
Write-Host "      Limit endpoint: $publicBase/limit-query"

if (-not $Check -and -not $NoPause) {
    Write-Host ''
    Read-Host 'Press Enter to close this window'
}
