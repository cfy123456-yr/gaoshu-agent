#requires -Version 7.0

param(
    [switch]$NoPause
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Split-Path -Parent $scriptDir

Write-Host '[1/1] Stopping local math service...'

$listening = netstat -ano | Where-Object {
    $_ -match '127\.0\.0\.1:8000\s' -and $_ -match 'LISTENING'
}
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

if (-not $NoPause) {
    Write-Host ''
    Read-Host 'Press Enter to close this window'
}
