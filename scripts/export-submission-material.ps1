[CmdletBinding()]
param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repoRoot "outputs\submission"
}

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 or newer is required. Run this script with pwsh."
}

if (-not (Get-Command ConvertFrom-Markdown -ErrorAction SilentlyContinue)) {
    throw "ConvertFrom-Markdown is unavailable. Install the Microsoft.PowerShell.Utility module."
}

$edgeCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe")
)
$edgePath = $edgeCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
    Select-Object -First 1

if (-not $edgePath) {
    throw "Microsoft Edge was not found. Install Edge or print the generated HTML manually."
}

$documents = @(
    @{
        Path = Join-Path $repoRoot "docs\SUBMISSION_GUIDE.md"
        Title = "知微高数参赛材料与答辩手册"
    },
    @{
        Path = Join-Path $repoRoot "docs\AI_USAGE_LOG.md"
        Title = "知微高数 AI 工具使用记录"
    },
    @{
        Path = Join-Path $repoRoot "PROJECT_STATUS.md"
        Title = "知微高数项目状态"
    }
)

foreach ($document in $documents) {
    if (-not (Test-Path -LiteralPath $document.Path -PathType Leaf)) {
        throw "Required document was not found: $($document.Path)"
    }
}

$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

$htmlPath = Join-Path $outputPath "submission-bundle.html"
$pdfPath = Join-Path $outputPath "submission-bundle.pdf"
$edgeProfile = Join-Path $repoRoot "work\submission-export-edge-profile"
New-Item -ItemType Directory -Path $edgeProfile -Force | Out-Null

$sections = foreach ($document in $documents) {
    $markdown = Get-Content -LiteralPath $document.Path -Raw -Encoding UTF8
    $converted = ConvertFrom-Markdown -InputObject $markdown
    $sectionHtml = $converted.Html

    $demoAssetsPath = [System.IO.Path]::GetFullPath(
        (Join-Path $repoRoot "docs\demo-assets")
    ).Replace("\", "/")
    $sectionHtml = $sectionHtml.Replace(
        'src="demo-assets/',
        "src=`"file:///$demoAssetsPath/"
    )
    $sectionHtml = $sectionHtml.Replace(
        'href="demo-assets/',
        "href=`"file:///$demoAssetsPath/"
    )

    @"
<section class="document">
  <h1 class="document-title">$($document.Title)</h1>
  $sectionHtml
</section>
"@
}

$bundleHtml = @"
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>知微高数参赛材料合订本</title>
  <style>
    @page { size: A4; margin: 18mm 16mm 20mm; }
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0 auto;
      max-width: 920px;
      color: #172033;
      background: #fff;
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
      font-size: 10.5pt;
      line-height: 1.7;
    }
    .document { break-before: page; }
    .document:first-child { break-before: auto; }
    .document-title {
      margin: 0 0 18px;
      padding: 0 0 10px;
      border-bottom: 2px solid #2457a7;
      color: #163f80;
      font-size: 22pt;
      line-height: 1.35;
    }
    h1, h2, h3 { break-after: avoid; line-height: 1.4; }
    h1 { margin-top: 1.5em; font-size: 18pt; }
    h2 { margin-top: 1.35em; padding-bottom: 4px; border-bottom: 1px solid #d7deea; font-size: 15pt; }
    h3 { margin-top: 1.15em; font-size: 12.5pt; }
    p, ul, ol, blockquote, pre, table { break-inside: avoid; }
    p { margin: 0.65em 0; }
    ul, ol { margin: 0.65em 0; padding-left: 1.6em; }
    blockquote {
      margin: 1em 0;
      padding: 8px 12px;
      border-left: 4px solid #4f78b8;
      background: #f4f7fb;
      color: #334155;
    }
    table {
      width: 100%;
      margin: 0.9em 0;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 9.5pt;
    }
    th, td {
      padding: 6px 8px;
      border: 1px solid #cbd5e1;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th { background: #edf2f9; color: #1e3a5f; }
    code {
      padding: 1px 4px;
      border-radius: 3px;
      background: #eef2f7;
      font-family: Consolas, monospace;
      font-size: 0.92em;
      overflow-wrap: anywhere;
    }
    pre {
      padding: 10px 12px;
      border: 1px solid #d8e0eb;
      border-radius: 4px;
      background: #f7f9fc;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    pre code { padding: 0; background: transparent; }
    img { display: block; max-width: 100%; max-height: 190mm; margin: 12px 0; border: 1px solid #d8e0eb; }
    a { color: #184f93; text-decoration: none; }
    @media print {
      a { color: inherit; }
      body { max-width: none; }
    }
  </style>
</head>
<body>
$($sections -join "`n")
</body>
</html>
"@

Set-Content -LiteralPath $htmlPath -Value $bundleHtml -Encoding utf8

$htmlUri = [System.Uri]::new($htmlPath).AbsoluteUri
& $edgePath `
    --headless `
    --disable-gpu `
    --no-pdf-header-footer `
    "--user-data-dir=$edgeProfile" `
    "--print-to-pdf=$pdfPath" `
    $htmlUri | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Edge failed to generate the PDF. Exit code: $LASTEXITCODE"
}

$pdfItem = Get-Item -LiteralPath $pdfPath
if ($pdfItem.Length -lt 1000) {
    throw "Generated PDF is unexpectedly small: $($pdfItem.Length) bytes"
}

$stream = [System.IO.File]::OpenRead($pdfPath)
try {
    $headerBytes = New-Object byte[] 5
    [void]$stream.Read($headerBytes, 0, $headerBytes.Length)
    $header = [System.Text.Encoding]::ASCII.GetString($headerBytes)
}
finally {
    $stream.Dispose()
}

if ($header -ne "%PDF-") {
    throw "Generated file does not have a valid PDF header."
}

$pdfHash = (Get-FileHash -LiteralPath $pdfPath -Algorithm SHA256).Hash
Write-Host "HTML: $htmlPath"
Write-Host "PDF:  $pdfPath"
Write-Host "Size: $($pdfItem.Length) bytes"
Write-Host "SHA256: $pdfHash"
