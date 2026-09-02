param(
    [switch] $RuntimeProbeOnly,
    [switch] $CoreRpcGateOnly,
    [switch] $FinalizeExistingPackage,
    [string] $PreviousReleaseZip
)

$ErrorActionPreference = 'Stop'
if (-not ($PSVersionTable.PSEdition -eq 'Core' -and $PSVersionTable.PSVersion.Major -ge 7)) {
    throw 'Release packaging requires PowerShell 7 or newer.'
}
Set-Location $PSScriptRoot

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $PSScriptRoot '.venv-py38-pyside2\Scripts\python.exe'),
    (Join-Path $repoRoot '.venv38\Scripts\python.exe'),
    'C:\Python38\python.exe',
    (Join-Path $PSScriptRoot '.venv-pyside6\Scripts\python.exe'),
    'python'
)
$pythonExe = $null
foreach ($candidate in $pythonCandidates) {
    if ($candidate -eq 'python') {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) {
            $pythonExe = $cmd.Source
            break
        }
        continue
    }
    if (Test-Path -LiteralPath $candidate) {
        $pythonExe = $candidate
        break
    }
}
if (-not $pythonExe) {
    throw 'Python runtime not found.'
}

$runtimeProbeCode = @'
import json
import sys
import PySide2
from PySide2 import QtCore

print(json.dumps({
    "python": ".".join(str(item) for item in sys.version_info[:3]),
    "major": int(sys.version_info[0]),
    "minor": int(sys.version_info[1]),
    "pyside2": str(PySide2.__version__),
    "qt": str(QtCore.qVersion()),
}, ensure_ascii=True))
'@
$runtimeProbePath = Join-Path ([System.IO.Path]::GetTempPath()) (
    'xiami-release-runtime-probe-{0}-{1}.py' -f $PID, [guid]::NewGuid().ToString('N')
)
$runtimeProbeOutput = @()
$runtimeProbeExitCode = -1
try {
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($runtimeProbePath, $runtimeProbeCode, $utf8WithoutBom)
    $runtimeProbeOutput = @(& $pythonExe $runtimeProbePath 2>&1)
    $runtimeProbeExitCode = $LASTEXITCODE
}
finally {
    Remove-Item -LiteralPath $runtimeProbePath -Force -ErrorAction SilentlyContinue
}
if ($runtimeProbeExitCode -ne 0) {
    throw "Selected Python cannot import PySide2: $pythonExe`n$($runtimeProbeOutput -join [Environment]::NewLine)"
}
$runtimeProbeLine = $runtimeProbeOutput | Where-Object { [string] $_ -match '^\s*\{' } | Select-Object -Last 1
if (-not $runtimeProbeLine) {
    throw "Selected Python did not return runtime metadata: $pythonExe"
}
try {
    $runtimeProbe = $runtimeProbeLine | ConvertFrom-Json
}
catch {
    throw "Selected Python returned invalid runtime metadata: $runtimeProbeLine"
}
if ([int] $runtimeProbe.major -ne 3 -or [int] $runtimeProbe.minor -ne 8) {
    throw "Release packaging requires Python 3.8; selected $($runtimeProbe.python): $pythonExe"
}
if (-not [string] $runtimeProbe.pyside2 -or -not [string] $runtimeProbe.qt) {
    throw "Release packaging requires PySide2 with a readable Qt runtime version: $pythonExe"
}
Write-Host "Release runtime: Python $($runtimeProbe.python), PySide2 $($runtimeProbe.pyside2), Qt $($runtimeProbe.qt)"
if ($RuntimeProbeOnly) {
    Write-Host 'Release runtime probe completed.'
    exit 0
}

$heartbeatResilienceProbe = Join-Path $PSScriptRoot 'scripts\heartbeat_resilience_probe.py'
if (-not (Test-Path -LiteralPath $heartbeatResilienceProbe -PathType Leaf)) {
    throw "Heartbeat resilience probe is missing: $heartbeatResilienceProbe"
}
& $pythonExe -B $heartbeatResilienceProbe
if ($LASTEXITCODE -ne 0) {
    throw "Heartbeat resilience probe failed with exit code $LASTEXITCODE."
}

$coreRpcReleaseGate = Join-Path $PSScriptRoot 'scripts\core_rpc_release_gate.ps1'
if (-not (Test-Path -LiteralPath $coreRpcReleaseGate -PathType Leaf)) {
    throw "Core RPC release gate is missing: $coreRpcReleaseGate"
}
$coreRpcGateArgs = @(
    '-NoProfile',
    '-NonInteractive',
    '-File',
    $coreRpcReleaseGate,
    '-PythonExe',
    $pythonExe
)
& pwsh.exe @coreRpcGateArgs
if ($LASTEXITCODE -ne 0) {
    throw "Core RPC release gate failed with exit code $LASTEXITCODE."
}
if ($CoreRpcGateOnly) {
    Write-Host 'Core RPC release-only gate completed.'
    exit 0
}

$mainPy = Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*_qt.py' -File | Select-Object -First 1 -ExpandProperty FullName
if (-not $mainPy) {
    throw 'main python file not found'
}
$mainText = Get-Content -Path $mainPy -Raw -Encoding UTF8
$verMatch = [regex]::Match($mainText, 'VERSION\s*=\s*["'']([^"'']+)["'']')
if (-not $verMatch.Success) {
    throw 'VERSION not found in 工具箱_qt.py'
}
$version = $verMatch.Groups[1].Value

$releaseZipName = [string]::Concat(
    [char]0x867E, [char]0x7C73, [char]0x5DE5, [char]0x5177, [char]0x7BB1,
    "-$version.zip"
)
$releaseZipPath = Join-Path $PSScriptRoot $releaseZipName
$releaseSha256Path = [System.IO.Path]::ChangeExtension($releaseZipPath, '.sha256')
$releaseJsonPath = [System.IO.Path]::ChangeExtension($releaseZipPath, '.release.json')
if (-not $FinalizeExistingPackage) {
    foreach ($existingReleaseArtifact in @($releaseZipPath, $releaseSha256Path, $releaseJsonPath)) {
        if (Test-Path -LiteralPath $existingReleaseArtifact) {
            throw "Refuse to rebuild while a same-version release artifact exists: $existingReleaseArtifact"
        }
    }
}

if (-not $FinalizeExistingPackage) {
    if (Test-Path build) {
        Remove-Item build -Recurse -Force
    }
    if (Test-Path dist) {
        Remove-Item dist -Recurse -Force
    }

    $nativeBuildScript = Join-Path $PSScriptRoot 'scripts\build_native_core.ps1'
    if (-not (Test-Path -LiteralPath $nativeBuildScript -PathType Leaf)) {
        throw "Native core build script is missing: $nativeBuildScript"
    }
    & pwsh.exe -NoProfile -NonInteractive -File $nativeBuildScript
    if ($LASTEXITCODE -ne 0) {
        throw "Native core build failed with exit code $LASTEXITCODE."
    }

    & $pythonExe -m PyInstaller --clean --noconfirm '.\build_win2012r2_fixed.spec'
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$appDir = Get-ChildItem .\dist -Directory | Select-Object -First 1
if (-not $appDir) {
    throw 'dist output not found'
}

$appExe = Get-ChildItem -LiteralPath $appDir.FullName -Filter '*.exe' -File | Select-Object -First 1
if (-not $appExe) {
    throw 'dist exe not found'
}
$nativeCorePath = Join-Path $appDir.FullName 'native\xiami_native_core.exe'
if (-not (Test-Path -LiteralPath $nativeCorePath -PathType Leaf)) {
    throw "dist native core not found: $nativeCorePath"
}
$nativeCoreExe = Get-Item -LiteralPath $nativeCorePath
$appPackages = @(Get-ChildItem -LiteralPath $appDir.FullName -Filter '*.pkg' -File)
if ($appPackages.Count -ne 1) {
    throw "dist must contain exactly one PyInstaller package archive; found $($appPackages.Count)"
}
$appPackage = $appPackages[0]

$npcAssetNativeGate = Join-Path $PSScriptRoot 'scripts\npc_asset_native_gate.py'
if (-not (Test-Path -LiteralPath $npcAssetNativeGate -PathType Leaf)) {
    throw "NPC asset native release gate is missing: $npcAssetNativeGate"
}
& $pythonExe -B $npcAssetNativeGate --pkg $appPackage.FullName
if ($LASTEXITCODE -ne 0) {
    throw "NPC asset native package gate failed with exit code $LASTEXITCODE."
}

$releaseSecurityAudit = Join-Path $PSScriptRoot 'scripts\check_embedded_xiami_release.py'
if (-not (Test-Path -LiteralPath $releaseSecurityAudit -PathType Leaf)) {
    throw "Release security policy audit is missing: $releaseSecurityAudit"
}

function Assert-ReleaseSecurityPolicy {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    & $pythonExe -B $releaseSecurityAudit $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Release security policy audit failed for: $Path"
    }
}

function Remove-PackagePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BaseDir,
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $baseFull = [System.IO.Path]::GetFullPath($BaseDir).TrimEnd('\') + '\'
    $targetFull = [System.IO.Path]::GetFullPath($Path)
    if (-not $targetFull.StartsWith($baseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refuse to remove package path outside app dir: $targetFull"
    }
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
}

function Remove-PackageGeneratedFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string] $AppDir
    )

    $embeddedDir = Join-Path $AppDir 'embedded_xiami'
    if (-not (Test-Path -LiteralPath $embeddedDir)) {
        return
    }

    $generatedDirs = @(
        'runtime\tmp_state',
        'runtime\xiami_v1\logs',
        'runtime\xiami_v1\plugin_data',
        'runtime\xiami_v1\plugin_state',
        'runtime\xiami_v1\kernels',
        'runtime\xiami_v1\kernels\NapCat.Shell.Windows\napcat\logs',
        'runtime\xiami_v1\kernels\NapCat.Shell.Windows\napcat\cache'
    )
    foreach ($relative in $generatedDirs) {
        Remove-PackagePath -BaseDir $AppDir -Path (Join-Path $embeddedDir $relative)
    }

    $generatedFiles = @(
        'runtime\xiami_v1\config.json',
        'runtime\xiami_v1\saved_accounts.json',
        'runtime\xiami_v1\kernels\NapCat.Shell.Windows\beacon_report.log',
        'runtime\xiami_v1\kernels\NapCat.Shell.Windows\guild1.db',
        'runtime\xiami_v1\kernels\NapCat.Shell.Windows\guild1.db-shm',
        'runtime\xiami_v1\kernels\NapCat.Shell.Windows\guild1.db-wal',
        'runtime\xiami_v1\kernels\NapCat.Shell.Windows\napcat\config\webui.json'
    )
    foreach ($relative in $generatedFiles) {
        Remove-PackagePath -BaseDir $AppDir -Path (Join-Path $embeddedDir $relative)
    }

    Get-ChildItem -LiteralPath $embeddedDir -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq '__pycache__' } |
        ForEach-Object { Remove-PackagePath -BaseDir $AppDir -Path $_.FullName }

    Get-ChildItem -LiteralPath $embeddedDir -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -like '*.pyc' -or
            $_.Name -like '*.pyo' -or
            $_.Name -like '*.log' -or
            $_.Name -like '*.jsonl' -or
            $_.Name -like '*.db' -or
            $_.Name -like '*.db-shm' -or
            $_.Name -like '*.db-wal' -or
            $_.Name -like '*.pem' -or
            $_.Name -like '*.key' -or
            $_.Name -like '*.pfx' -or
            $_.Name -like '*.p12' -or
            $_.Name -like '*.jks' -or
            $_.Name -like '*.keystore' -or
            ($_.Name -eq '.env' -or $_.Name -like '.env.*') -or
            $_.Name -match '^(napcat|onebot11)_\d{5,}\.json$' -or
            $_.Name -match '^napcat_protocol_\d{5,}\.json$' -or
            ($_.Name -eq 'plugin_config.json' -and $_.FullName.StartsWith((Join-Path $embeddedDir 'xiami_plugins'), [System.StringComparison]::OrdinalIgnoreCase)) -or
            $_.Name -like '*_smoke.py'
        } |
        ForEach-Object { Remove-PackagePath -BaseDir $AppDir -Path $_.FullName }

    # The bundled NapCat runtime ships native binaries for multiple platforms.
    # This toolbox package only targets Windows x64; removing Linux/macOS/arm64
    # natives from the built payload saves about 20 MB in the final zip without
    # affecting Windows QR-login.
    $napcatNativeDir = Join-Path $embeddedDir 'runtime\xiami_v1\kernels\NapCat.Shell.Windows\napcat\native'
    if (Test-Path -LiteralPath $napcatNativeDir) {
        Get-ChildItem -LiteralPath $napcatNativeDir -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object {
                $relative = $_.FullName.Substring($napcatNativeDir.Length).TrimStart('\', '/')
                $relative -match '(^|[\\/._-])(linux|darwin)([\\/._-]|$)' -or
                $relative -match '(^|[\\/._-])arm64([\\/._-]|$)'
            } |
            ForEach-Object { Remove-PackagePath -BaseDir $AppDir -Path $_.FullName }
    }

    # PyInstaller may reclassify DLLs from the embedded NapCat runtime as root binaries.
    # Keep the runtime-local copies and remove duplicated root copies from the app payload.
    $duplicateRootBinaries = @(
        'libvips-42.dll',
        'broadcast_ipc.dll',
        'QQNT.dll',
        'libglib-2.0-0.dll',
        'libgobject-2.0-0.dll'
    )
    foreach ($name in $duplicateRootBinaries) {
        $rootCopy = Join-Path $AppDir $name
        if (-not (Test-Path -LiteralPath $rootCopy)) {
            continue
        }
        $runtimeCopy = Get-ChildItem -LiteralPath $embeddedDir -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ieq $name } |
            Select-Object -First 1
        if ($runtimeCopy) {
            Remove-PackagePath -BaseDir $AppDir -Path $rootCopy
        }
    }
}

if (-not $FinalizeExistingPackage) {
    Remove-PackageGeneratedFiles -AppDir $appDir.FullName
}

$bundledKernelDir = Join-Path $appDir.FullName 'embedded_xiami\runtime\xiami_v1\kernels'
if (Test-Path -LiteralPath $bundledKernelDir) {
    throw "QQ/NapCat kernel environment leaked into dist: $bundledKernelDir"
}

$authenticodeThumbprint = ([string] $env:XIAMI_AUTHENTICODE_CERT_THUMBPRINT).Trim()
$authenticodePfxPath = ([string] $env:XIAMI_AUTHENTICODE_PFX_PATH).Trim()
$authenticodeTimestampUrl = ([string] $env:XIAMI_AUTHENTICODE_TIMESTAMP_URL).Trim()
$authenticodeStoreLocation = ([string] $env:XIAMI_AUTHENTICODE_CERT_STORE_LOCATION).Trim()
if (-not $authenticodeStoreLocation) {
    $authenticodeStoreLocation = 'CurrentUser'
}
if ($authenticodeStoreLocation -notin @('CurrentUser', 'LocalMachine')) {
    throw 'XIAMI_AUTHENTICODE_CERT_STORE_LOCATION must be CurrentUser or LocalMachine.'
}
if ($authenticodeThumbprint -and $authenticodePfxPath) {
    throw 'Configure only one Authenticode identity: XIAMI_AUTHENTICODE_CERT_THUMBPRINT or XIAMI_AUTHENTICODE_PFX_PATH.'
}
$authenticodeSigningRequested = [bool] ($authenticodeThumbprint -or $authenticodePfxPath)
if ($authenticodeTimestampUrl -and -not $authenticodeSigningRequested) {
    throw 'XIAMI_AUTHENTICODE_TIMESTAMP_URL requires a configured Authenticode signing identity.'
}
if ($authenticodeSigningRequested) {
    if ($FinalizeExistingPackage) {
        throw 'Authenticode signing cannot be added while finalizing an existing ZIP; rebuild the package so signed binaries are compressed.'
    }
    $authenticodeScript = Join-Path $PSScriptRoot 'scripts\sign_authenticode.ps1'
    if (-not (Test-Path -LiteralPath $authenticodeScript -PathType Leaf)) {
        throw "Authenticode signing script is missing: $authenticodeScript"
    }
    $authenticodeCommonArgs = @()
    if ($authenticodeThumbprint) {
        $authenticodeCommonArgs += @(
            '-CertificateThumbprint',
            $authenticodeThumbprint,
            '-CertificateStoreLocation',
            $authenticodeStoreLocation
        )
    }
    else {
        $authenticodeCommonArgs += @('-PfxPath', $authenticodePfxPath)
    }
    if ($authenticodeTimestampUrl) {
        $authenticodeCommonArgs += @('-TimestampUrl', $authenticodeTimestampUrl)
    }
    foreach ($signingTarget in @($appExe.FullName, $nativeCoreExe.FullName)) {
        $authenticodeArgs = @(
            '-NoProfile',
            '-NonInteractive',
            '-File',
            $authenticodeScript,
            '-Path',
            $signingTarget
        ) + $authenticodeCommonArgs
        & pwsh.exe @authenticodeArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Authenticode signing failed for $signingTarget with exit code $LASTEXITCODE."
        }
    }
}

function Get-ReleaseAuthenticodeState {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    try {
        $signature = Get-AuthenticodeSignature -LiteralPath $Path -ErrorAction Stop
        return [pscustomobject] @{
            path = $Path
            status = [string] $signature.Status
            valid = $signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid
            signer_thumbprint = if ($signature.SignerCertificate) { [string] $signature.SignerCertificate.Thumbprint } else { '' }
            timestamped = [bool] $signature.TimeStamperCertificate
            timestamp_thumbprint = if ($signature.TimeStamperCertificate) { [string] $signature.TimeStamperCertificate.Thumbprint } else { '' }
        }
    }
    catch {
        return [pscustomobject] @{
            path = $Path
            status = 'Unavailable'
            valid = $false
            signer_thumbprint = ''
            timestamped = $false
            timestamp_thumbprint = ''
        }
    }
}

$appAuthenticode = Get-ReleaseAuthenticodeState -Path $appExe.FullName
$nativeAuthenticode = Get-ReleaseAuthenticodeState -Path $nativeCoreExe.FullName
$authenticodeValid = [bool] ($appAuthenticode.valid -and $nativeAuthenticode.valid)
$authenticodeTimestamped = [bool] ($appAuthenticode.timestamped -and $nativeAuthenticode.timestamped)
$authenticodeSameSigner = [bool] (
    $authenticodeValid -and
    -not [string]::IsNullOrWhiteSpace([string] $appAuthenticode.signer_thumbprint) -and
    [string] $appAuthenticode.signer_thumbprint -eq [string] $nativeAuthenticode.signer_thumbprint
)
$authenticodeReleaseReady = [bool] ($authenticodeValid -and $authenticodeTimestamped -and $authenticodeSameSigner)
$authenticodeStatus = "app=$($appAuthenticode.status); native=$($nativeAuthenticode.status)"
$requireAuthenticode = ([string] $env:XIAMI_RELEASE_REQUIRE_AUTHENTICODE).Trim().ToLowerInvariant() -in @('1', 'true', 'yes', 'on')
if ($requireAuthenticode -and -not $authenticodeReleaseReady) {
    throw "Authenticode release gate failed: $authenticodeStatus; timestamped=$authenticodeTimestamped; same_signer=$authenticodeSameSigner"
}
Write-Host "Authenticode status: $authenticodeStatus"

Assert-ReleaseSecurityPolicy -Path $appDir.FullName

$smokeJson = Join-Path $env:TEMP 'xiami_dark_workbench_packaged_smoke.json'
if (Test-Path $smokeJson) {
    Remove-Item $smokeJson -Force
}
$smokeArgs = @('--dark-workbench-smoke', '--dark-workbench-json', '--smoke-json-file', $smokeJson)
$smokeExitCode = $null
$previousQtPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = 'offscreen'
for ($smokeAttempt = 1; $smokeAttempt -le 3; $smokeAttempt++) {
    if (Test-Path $smokeJson) {
        Remove-Item $smokeJson -Force
    }
    $smokeProcess = Start-Process -FilePath $appExe.FullName -ArgumentList $smokeArgs -WorkingDirectory $appDir.FullName -Wait -PassThru -WindowStyle Hidden
    $smokeExitCode = $smokeProcess.ExitCode
    if ($smokeExitCode -eq 0 -and (Test-Path $smokeJson)) {
        break
    }
    Start-Sleep -Seconds 1
}
if ([string]::IsNullOrEmpty($previousQtPlatform)) {
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
}
else {
    $env:QT_QPA_PLATFORM = $previousQtPlatform
}
if ($smokeExitCode -ne 0) {
    throw "packaged dark workbench smoke failed with exit code $smokeExitCode"
}
if (-not (Test-Path $smokeJson)) {
    throw 'packaged dark workbench smoke json not found'
}
$smoke = Get-Content -LiteralPath $smokeJson -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedTitle = [string]::Concat(
    [char]0x867E, [char]0x7C73, [char]0x5DE5, [char]0x5177, [char]0x7BB1,
    ' - Dark Workbench'
)
if ($smoke.window_title -ne $expectedTitle) {
    throw "unexpected packaged window title: $($smoke.window_title)"
}
if ([string] $smoke.brand_version -ne "v$version") {
    throw "unexpected packaged brand version: $($smoke.brand_version); expected v$version"
}
if ($smoke.sample_chrome_visible.header_actions -ne $false -or $smoke.sample_chrome_visible.toolbar -ne $false -or $smoke.sample_chrome_visible.detail -ne $false -or $smoke.sample_chrome_visible.log -ne $false) {
    throw 'packaged entry still shows preview chrome'
}
if (-not ($smoke.mounted_pages -contains 'real_basic') -or -not ($smoke.mounted_pages -contains 'website')) {
    throw 'packaged entry did not mount required real pages'
}
$packageSmokePassed = $true

if (-not $FinalizeExistingPackage) {
    # Safety guard: never allow previously generated update packages to be packed into a new update zip.
    Get-ChildItem -Path $appDir.FullName -Recurse -File -Filter '*-update.zip' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

$zipName = $releaseZipName
$zipPath = $releaseZipPath
$sha256Path = $releaseSha256Path
foreach ($releaseArtifact in @($sha256Path, $releaseJsonPath)) {
    if (Test-Path -LiteralPath $releaseArtifact) {
        throw "Refuse to overwrite an existing release artifact: $releaseArtifact"
    }
}

if ($FinalizeExistingPackage) {
    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Existing release package not found for finalization: $zipPath"
    }
    Write-Host "Finalizing existing release package without rebuilding or recompressing: $zipPath"
}
else {
    if (Test-Path -LiteralPath $zipPath) {
        throw "Refuse to overwrite an existing release package: $zipPath"
    }
    Push-Location (Split-Path -Parent $appDir.FullName)
    try {
        Compress-Archive -Path $appDir.Name -DestinationPath $zipPath -Force
    }
    finally {
        Pop-Location
    }
}

Assert-ReleaseSecurityPolicy -Path $zipPath
& $pythonExe -B $npcAssetNativeGate --zip $zipPath
if ($LASTEXITCODE -ne 0) {
    throw "NPC asset native ZIP gate failed with exit code $LASTEXITCODE."
}

$zipItem = Get-Item -LiteralPath $zipPath
if ($zipItem.Length -le 0) {
    throw "Release package is empty: $zipPath"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entries = @($archive.Entries)
    $fileEntries = @($entries | Where-Object { -not [string]::IsNullOrEmpty($_.Name) })
    if ($fileEntries.Count -le 0) {
        throw "Release package contains no files: $zipPath"
    }
    $normalizedNames = @(
        $entries |
            ForEach-Object { ([string] $_.FullName).Replace('\', '/').TrimStart('/') } |
            Where-Object { $_ }
    )
    $normalizedFileNames = @(
        $fileEntries |
            ForEach-Object { ([string] $_.FullName).Replace('\', '/').TrimStart('/') } |
            Where-Object { $_ }
    )
    $topLevels = @(
        $normalizedNames |
            ForEach-Object { ($_ -split '/', 2)[0] } |
            Sort-Object -Unique
    )
    $expectedTopLevel = [string]::Concat(
        [char]0x867E, [char]0x7C73, [char]0x5DE5, [char]0x5177, [char]0x7BB1
    )
    if ($topLevels.Count -ne 1 -or [string] $topLevels[0] -ne $expectedTopLevel) {
        throw "Release package must contain only the '$expectedTopLevel' top-level directory; actual: $($topLevels -join ', ')"
    }
    $requiredExactEntries = @(
        "$expectedTopLevel/$expectedTopLevel.exe",
        "$expectedTopLevel/native/xiami_native_core.exe",
        "$expectedTopLevel/PySide2/plugins/platforms/qwindows.dll",
        "$expectedTopLevel/resources/222.ico"
    )
    foreach ($requiredEntry in $requiredExactEntries) {
        if ($normalizedFileNames -notcontains $requiredEntry) {
            throw "Release package is missing required file: $requiredEntry"
        }
    }
    $retiredLegacyEntries = @(
        "$expectedTopLevel/resources/free_micro_client/PasswordWorker.ps1"
    )
    foreach ($legacyEntry in $retiredLegacyEntries) {
        if ($normalizedFileNames -contains $legacyEntry) {
            throw "Release package contains retired legacy component: $legacyEntry"
        }
    }
    $bundledKernelPrefix = "$expectedTopLevel/embedded_xiami/runtime/xiami_v1/kernels/"
    $bundledKernelEntries = @($normalizedFileNames | Where-Object {
        $_.StartsWith($bundledKernelPrefix, [System.StringComparison]::OrdinalIgnoreCase)
    })
    if ($bundledKernelEntries.Count -gt 0) {
        throw "Release package contains bundled QQ/NapCat kernel environment: $($bundledKernelEntries[0])"
    }
    foreach ($requiredPrefix in @(
        "$expectedTopLevel/embedded_xiami/",
        "$expectedTopLevel/resources/",
        "$expectedTopLevel/微端配置目录/"
    )) {
        if (-not @($normalizedFileNames | Where-Object { $_.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase) }).Count) {
            throw "Release package is missing required directory content: $requiredPrefix"
        }
    }
}
finally {
    $archive.Dispose()
}

$zipBindingScript = Join-Path $PSScriptRoot 'scripts\verify_release_zip_binaries.ps1'
if (-not (Test-Path -LiteralPath $zipBindingScript -PathType Leaf)) {
    throw "Release ZIP binary verifier is missing: $zipBindingScript"
}
& pwsh.exe -NoProfile -NonInteractive -File $zipBindingScript `
    -ZipPath $zipPath `
    -AppPath $appExe.FullName `
    -NativePath $nativeCoreExe.FullName `
    -TopLevelName $expectedTopLevel | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Release ZIP binary binding verification failed with exit code $LASTEXITCODE."
}

function Get-Sha256Hex {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $stream = $null
    $sha256 = $null
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        $digest = $sha256.ComputeHash($stream)
        return ([System.BitConverter]::ToString($digest)).Replace('-', '')
    }
    finally {
        if ($sha256) {
            $sha256.Dispose()
        }
        if ($stream) {
            $stream.Dispose()
        }
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Text
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

$hashHex = Get-Sha256Hex -Path $zipPath
if ($hashHex -notmatch '^[0-9A-Fa-f]{64}$') {
    throw "Failed to compute SHA256 for release package: $zipPath"
}
$hashLine = "$($hashHex.ToUpperInvariant())  $($zipItem.Name)"
Write-Utf8NoBom -Path $sha256Path -Text ($hashLine + [Environment]::NewLine)

$previousReleaseInput = $PreviousReleaseZip
if (-not $previousReleaseInput) {
    $previousReleaseInput = [string] $env:XIAMI_PREVIOUS_RELEASE_ZIP
}
$previousZip = $null
if ($previousReleaseInput) {
    $resolvedPrevious = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($previousReleaseInput)
    if (-not (Test-Path -LiteralPath $resolvedPrevious -PathType Leaf)) {
        throw "Previous release ZIP does not exist: $resolvedPrevious"
    }
    $previousZip = Get-Item -LiteralPath $resolvedPrevious
    if ($previousZip.Extension -ine '.zip' -or $previousZip.Name -like '*-update.zip') {
        throw "Previous release input must be a release ZIP: $($previousZip.FullName)"
    }
    if ($previousZip.FullName -eq $zipItem.FullName) {
        throw 'Previous release ZIP must not be the newly built package.'
    }
}
else {
    $previousZip = Get-ChildItem -LiteralPath $PSScriptRoot -Filter ([string]::Concat(
            [char]0x867E, [char]0x7C73, [char]0x5DE5, [char]0x5177, [char]0x7BB1, '-*.zip'
        )) -File |
        Where-Object { $_.FullName -ne $zipItem.FullName -and $_.Name -notlike '*-update.zip' } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}
$previousPackage = $null
$previousSha256 = $null
$previousSizeBytes = $null
$sameVersionUpdate = $false
$sizeDeltaBytes = $null
$sizeDeltaPercent = $null
if ($previousZip) {
    $previousPackage = $previousZip.Name
    $previousSha256 = (Get-Sha256Hex -Path $previousZip.FullName).ToLowerInvariant()
    $previousSizeBytes = [long] $previousZip.Length
    $previousVersionMatch = [regex]::Match($previousZip.BaseName, '-([0-9]+(?:\.[0-9]+)+)$')
    $sameVersionUpdate = $previousVersionMatch.Success -and $previousVersionMatch.Groups[1].Value -eq $version
    $sizeDeltaBytes = [long] $zipItem.Length - [long] $previousZip.Length
    if ([long] $previousZip.Length -gt 0) {
        $sizeDeltaPercent = [math]::Round(($sizeDeltaBytes * 100.0) / [long] $previousZip.Length, 2)
    }
    Write-Host "Package size comparison: $($previousZip.Name) -> $($zipItem.Name), delta $sizeDeltaBytes bytes ($sizeDeltaPercent%)"
}
else {
    Write-Host 'Package size comparison: no historical release ZIP found.'
}

$downloadUrl = [string] ($env:XIAMI_RELEASE_DOWNLOAD_URL)
$downloadUrl = $downloadUrl.Trim()
$publishReady = $false
if ($downloadUrl) {
    try {
        $downloadUri = [System.Uri] $downloadUrl
        $publishReady = (
            $packageSmokePassed -and
            $authenticodeReleaseReady -and
            $downloadUri.IsAbsoluteUri -and
            $downloadUri.Scheme -eq 'https' -and
            -not [string]::IsNullOrWhiteSpace($downloadUri.Host) -and
            [string]::IsNullOrWhiteSpace($downloadUri.UserInfo)
        )
    }
    catch {
        $publishReady = $false
    }
}
$releaseMetadata = [ordered] @{
    version = $version
    file = $zipItem.Name
    sha256 = $hashHex.ToLowerInvariant()
    size_bytes = [long] $zipItem.Length
    size_mib = [math]::Round($zipItem.Length / 1MB, 2)
    file_count = [int] $fileEntries.Count
    built_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    top_level = $expectedTopLevel
    package_smoke_passed = [bool] $packageSmokePassed
    authenticode_status = $authenticodeStatus
    authenticode_valid = [bool] $authenticodeValid
    authenticode_release_ready = [bool] $authenticodeReleaseReady
    authenticode_timestamped = [bool] $authenticodeTimestamped
    authenticode_same_signer = [bool] $authenticodeSameSigner
    app_authenticode_status = [string] $appAuthenticode.status
    app_authenticode_valid = [bool] $appAuthenticode.valid
    app_signer_thumbprint = [string] $appAuthenticode.signer_thumbprint
    app_timestamped = [bool] $appAuthenticode.timestamped
    app_timestamp_thumbprint = [string] $appAuthenticode.timestamp_thumbprint
    native_authenticode_status = [string] $nativeAuthenticode.status
    native_authenticode_valid = [bool] $nativeAuthenticode.valid
    native_signer_thumbprint = [string] $nativeAuthenticode.signer_thumbprint
    native_timestamped = [bool] $nativeAuthenticode.timestamped
    native_timestamp_thumbprint = [string] $nativeAuthenticode.timestamp_thumbprint
    same_version_update = [bool] $sameVersionUpdate
    download_url = $downloadUrl
    publish_ready = [bool] $publishReady
    previous_package = $previousPackage
    previous_sha256 = $previousSha256
    previous_size_bytes = $previousSizeBytes
    size_delta_bytes = $sizeDeltaBytes
    size_delta_percent = $sizeDeltaPercent
}
$releaseJson = $releaseMetadata | ConvertTo-Json -Depth 5
Write-Utf8NoBom -Path $releaseJsonPath -Text ($releaseJson + [Environment]::NewLine)

Write-Host "Release package: $zipPath"
Write-Host "Release SHA256: $sha256Path"
Write-Host "Release metadata: $releaseJsonPath"
Write-Host "Release size: $($zipItem.Length) bytes ($($releaseMetadata.size_mib) MiB), files: $($fileEntries.Count)"
Write-Host "Publish ready: $publishReady"
