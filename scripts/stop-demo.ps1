$ErrorActionPreference = 'Continue'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Split-Path -Parent $scriptDir
$projectDir = Split-Path -Parent $appDir
$workDir = Join-Path $projectDir 'work'
$pidFile = Join-Path $workDir 'tunnel.pid'

Write-Host '[1/2] Stopping tunnel...'
if (Test-Path $pidFile) {
    $tunnelPid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tunnelPid) {
        & taskkill.exe /PID $tunnelPid /T /F 2>$null | Out-Null
        Write-Host "      Tunnel stopped (PID $tunnelPid)"
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host '      No tunnel PID file found. If a tunnel started earlier is still running, stop the node.exe process manually.'
}

Write-Host '[2/2] Stopping local math service...'
$listening = netstat -ano | Where-Object { $_ -match '127\.0\.0\.1:8000\s' -and $_ -match 'LISTENING' }
$stopped = $false
foreach ($line in $listening) {
    $columns = $line -split '\s+' | Where-Object { $_ }
    $processId = $columns[-1]
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -match 'python|uvicorn') {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Write-Host "      Math service stopped (PID $processId)"
        $stopped = $true
    }
}
if (-not $stopped) {
    Write-Host '      Math service is not running'
}

Write-Host ''
Read-Host 'Press Enter to close this window'
