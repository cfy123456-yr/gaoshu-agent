#requires -Version 7.0

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$LocalPath,

    [Parameter(Mandatory = $true)]
    [string]$RemotePath,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedHash,

    [string]$Username = "cfyyy",
    [string]$WebApp = "cfyyy.pythonanywhere.com",
    [string]$PublicUrl = "",
    [string[]]$RequiredMarker = @(),
    [switch]$SkipReload,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Add-Type -AssemblyName System.Net.Http

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

function Get-Sha256FromBytes([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash($Bytes)
        return (($hashBytes | ForEach-Object { $_.ToString("X2") }) -join "")
    }
    finally {
        $sha.Dispose()
    }
}

function Assert-Markers([string]$Text, [string[]]$Markers, [string]$Scope) {
    $missing = @($Markers | Where-Object { $_ -and -not $Text.Contains($_) })
    if ($missing.Count -gt 0) {
        throw "$Scope is missing required marker(s): $($missing -join ', ')"
    }
}

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$localFile = (Resolve-Path -LiteralPath $LocalPath).Path
$localItem = Get-Item -LiteralPath $localFile
$expected = $ExpectedHash.Trim().ToUpperInvariant()
$localHash = Get-Sha256 $localFile

if ($expected -notmatch "^[A-F0-9]{64}$") {
    throw "-ExpectedHash must be a 64-character SHA256 value."
}
if ($localHash -ne $expected) {
    throw "Local file hash mismatch: expected $expected, got $localHash."
}
if ($RequiredMarker.Count -gt 0) {
    Assert-Markers (Get-Content -Raw -LiteralPath $localFile) $RequiredMarker "Local file"
}

$validation = [ordered]@{
    local_path = $localFile
    bytes = $localItem.Length
    sha256 = $localHash
    remote_path = $RemotePath
    web_app = $WebApp
    required_markers = $RequiredMarker
}

if ($ValidateOnly) {
    $validation | ConvertTo-Json
    return
}

$target = "$WebApp : $RemotePath"
if (-not $PSCmdlet.ShouldProcess($target, "Upload file and reload web app")) {
    return
}

$token = [string]$env:PYTHONANYWHERE_API_TOKEN
if ([string]::IsNullOrWhiteSpace($token)) {
    throw "Set PYTHONANYWHERE_API_TOKEN in the current PowerShell session before publishing."
}
$token = $token.Trim()
if ($token -notmatch "^[A-Za-z0-9]{40}$") {
    throw "PYTHONANYWHERE_API_TOKEN has an invalid format."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $projectRoot "work\pythonanywhere-backup-$timestamp"
$backupFile = Join-Path $backupRoot ([IO.Path]::GetFileName($RemotePath))
$readbackFile = Join-Path $backupRoot ("readback-" + [IO.Path]::GetFileName($RemotePath))
$resultFile = Join-Path $projectRoot "work\pythonanywhere-publish-result.json"
$remoteUrl = "https://www.pythonanywhere.com/api/v0/user/$Username/files/path$RemotePath"
$reloadUrl = "https://www.pythonanywhere.com/api/v0/user/$Username/webapps/$WebApp/reload/"
$publicUri = if ($PublicUrl) { "https://$WebApp$PublicUrl" } else { "" }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$client = $null

try {
    $client = [System.Net.Http.HttpClient]::new()
    $client.DefaultRequestHeaders.Authorization =
        [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Token", $token)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd("gaoshu-agent-release/1.0")

    $backupResponse = $client.GetAsync($remoteUrl).GetAwaiter().GetResult()
    $backupBytes = $backupResponse.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    if (-not $backupResponse.IsSuccessStatusCode) {
        throw "Remote backup failed with HTTP $([int]$backupResponse.StatusCode)."
    }
    [IO.File]::WriteAllBytes($backupFile, $backupBytes)
    $backupHash = Get-Sha256FromBytes $backupBytes

    $localBytes = [IO.File]::ReadAllBytes($localFile)
    $multipart = [System.Net.Http.MultipartFormDataContent]::new()
    $fileContent = [System.Net.Http.ByteArrayContent]::new($localBytes)
    $fileContent.Headers.ContentType =
        [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/octet-stream")
    $multipart.Add($fileContent, "content", [IO.Path]::GetFileName($localFile))

    try {
        $uploadResponse = $client.PostAsync($remoteUrl, $multipart).GetAwaiter().GetResult()
        $uploadBody = $uploadResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $uploadResponse.IsSuccessStatusCode) {
            throw "Upload failed with HTTP $([int]$uploadResponse.StatusCode): $uploadBody"
        }
    }
    finally {
        $multipart.Dispose()
    }

    $readbackResponse = $client.GetAsync($remoteUrl).GetAwaiter().GetResult()
    $readbackBytes = $readbackResponse.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    if (-not $readbackResponse.IsSuccessStatusCode) {
        throw "Readback failed with HTTP $([int]$readbackResponse.StatusCode)."
    }
    [IO.File]::WriteAllBytes($readbackFile, $readbackBytes)
    $readbackHash = Get-Sha256FromBytes $readbackBytes
    if ($readbackBytes.Length -ne $localItem.Length -or $readbackHash -ne $localHash) {
        throw "Readback mismatch: expected $($localItem.Length) bytes / $localHash."
    }

    $reloadStatus = $null
    if (-not $SkipReload) {
        $reloadContent = [System.Net.Http.StringContent]::new(
            "{}",
            [Text.Encoding]::UTF8,
            "application/json"
        )
        try {
            $reloadResponse = $client.PostAsync($reloadUrl, $reloadContent).GetAwaiter().GetResult()
            $reloadBody = $reloadResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if (-not $reloadResponse.IsSuccessStatusCode) {
                throw "Reload failed with HTTP $([int]$reloadResponse.StatusCode): $reloadBody"
            }
            $reloadStatus = [int]$reloadResponse.StatusCode
        }
        finally {
            $reloadContent.Dispose()
        }
    }

    $publicStatus = $null
    $publicVerified = $false
    if ($publicUri -and -not $SkipReload) {
        $publicText = ""
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            try {
                $publicResponse = $client.GetAsync($publicUri).GetAwaiter().GetResult()
                $publicText = $publicResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                if ($publicResponse.IsSuccessStatusCode) {
                    $publicStatus = [int]$publicResponse.StatusCode
                    $missing = @($RequiredMarker | Where-Object { $_ -and -not $publicText.Contains($_) })
                    if ($missing.Count -eq 0) {
                        $publicVerified = $true
                        break
                    }
                }
            }
            catch {
                $publicStatus = $null
            }
            Start-Sleep -Seconds 2
        } while ([DateTime]::UtcNow -lt $deadline)

        if (-not $publicVerified) {
            Assert-Markers $publicText $RequiredMarker "Public page"
            throw "Public page did not expose all required markers after reload."
        }
    }

    $summary = [ordered]@{
        published_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
        local_path = $localFile
        bytes = $localItem.Length
        sha256 = $localHash
        remote_path = $RemotePath
        backup_file = $backupFile
        backup_bytes = $backupBytes.Length
        backup_sha256 = $backupHash
        readback_file = $readbackFile
        readback_matched = $true
        reload_http_status = $reloadStatus
        public_url = $publicUri
        public_http_status = $publicStatus
        public_marker_verified = $publicVerified
    }
    $summary | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $resultFile -Encoding utf8
    $summary | ConvertTo-Json -Depth 4
}
finally {
    if ($null -ne $client) {
        $client.Dispose()
    }
    $token = $null
}
