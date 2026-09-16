param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$distPath = Join-Path $projectRoot "dist"
$zipPath = Join-Path $distPath "gtm-mcp-agent.zip"

if (-not $zipPath.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create an archive outside the project."
}

New-Item -ItemType Directory -Path $distPath -Force | Out-Null
if (Test-Path -LiteralPath $zipPath) {
    if (-not $Force) {
        throw "Archive already exists: $zipPath. Run with -Force to replace it."
    }
    Remove-Item -LiteralPath $zipPath -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open(
    $zipPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)

try {
    $files = Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -File
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($projectRoot.Length).TrimStart("\")
        $excludedDirectory = $relative -match '(^|\\)(\.git|\.venv|\.data|dist|__pycache__|\.pytest_cache|[^\\]+\.egg-info|evidence)(\\|$)'
        $excludedFile = $file.Name -eq ".env" -or `
            $file.Name -like "*.pyc" -or `
            $file.Name -like "credentials*.json" -or `
            $file.Name -like "*service-account*.json"

        if ($excludedDirectory -or $excludedFile) {
            continue
        }

        $entryName = $relative.Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $file.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

Write-Output $zipPath
