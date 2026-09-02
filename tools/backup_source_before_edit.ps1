$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backupRoot = Join-Path $projectRoot "source_backups"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

if (-not (Test-Path $backupRoot)) {
    New-Item -ItemType Directory -Path $backupRoot | Out-Null
}

$targetDir = Join-Path $backupRoot $timestamp
New-Item -ItemType Directory -Path $targetDir | Out-Null

$mainSource = Get-ChildItem -LiteralPath $projectRoot -File |
    Where-Object {
        $_.Name -like "*_qt.py" -and
        $_.Name -notlike "*.bootstrap_backup.py" -and
        $_.Name -notlike "*.corrupted.py"
    } |
    Select-Object -First 1

if (-not $mainSource) {
    throw "Main source file not found with rule *_qt.py"
}

$dst = Join-Path $targetDir $mainSource.Name
Copy-Item -LiteralPath $mainSource.FullName -Destination $dst -Force

Write-Output ("Backup created: " + $targetDir)
Write-Output $dst
