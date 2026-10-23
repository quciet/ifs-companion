param([string]$DotnetPath, [string]$PythonPath, [string]$InnoPath, [string]$ModelVettingPath)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$versionMatch=Select-String -LiteralPath 'packaging\installer.iss' -Pattern '^#define AppVersion "([^"]+)"$'
if (-not $versionMatch) { throw 'Installer version is missing' }
$appVersion=$versionMatch.Matches[0].Groups[1].Value
$desktopVersion=([xml](Get-Content -LiteralPath 'desktop\IFsCompanion.csproj' -Raw)).Project.PropertyGroup.Version
if ($desktopVersion -ne $appVersion) { throw 'Desktop and installer versions must match' }
$engineVersionMatch=Select-String -LiteralPath 'official_tools.py' -Pattern '^COMPANION_VERSION = \((\d+),\s*(\d+),\s*(\d+)\)$'
if (-not $engineVersionMatch) { throw 'Engine version is missing' }
$engineVersion=($engineVersionMatch.Matches[0].Groups[1..3].Value -join '.')
if ($engineVersion -ne $appVersion) { throw 'Engine, desktop, and installer versions must match' }
foreach ($name in @("IFsCompanion-Setup-$appVersion-win-x64.exe","IFsCompanion-Portable-$appVersion-win-x64.zip","SHA256SUMS-$appVersion.txt")) {
    if (Test-Path -LiteralPath (Join-Path 'release' $name)) { throw "Release $appVersion already exists. Increment the application version before building changed code." }
}

if (-not $ModelVettingPath) { $ModelVettingPath=Join-Path $PSScriptRoot '..\ifs-model-vetting' }
$ModelVettingPath=(Resolve-Path -LiteralPath $ModelVettingPath).Path
$env:IFS_MODEL_VETTING_PATH=$ModelVettingPath
if (-not (Test-Path -LiteralPath (Join-Path $ModelVettingPath 'app.py'))) { throw 'Model-vetting source is missing' }
if (-not $DotnetPath) { $DotnetPath=Join-Path $PSScriptRoot '..\DevelopmentTools\dotnet\dotnet.exe' }
if (-not $PythonPath) { $PythonPath=Join-Path $PSScriptRoot '.packaging-venv314\Scripts\python.exe' }
if (-not $InnoPath) { $InnoPath=Join-Path $PSScriptRoot '..\DevelopmentTools\inno\ISCC.exe' }
foreach ($toolPath in @($DotnetPath,$PythonPath,$InnoPath)) {
    if (-not (Test-Path -LiteralPath $toolPath)) { throw "Build tool missing: $toolPath" }
}
New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot 'build-tools') | Out-Null
$bootstrapper=Join-Path $PSScriptRoot 'build-tools\MicrosoftEdgeWebview2Setup.exe'
if (-not (Test-Path -LiteralPath $bootstrapper)) {
    Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $bootstrapper
}
$signature=Get-AuthenticodeSignature -LiteralPath $bootstrapper
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'WebView2 bootstrapper signature verification failed' }
& $DotnetPath publish (Join-Path $ModelVettingPath 'decoder') -c Release -r win-x64 --self-contained true -o decoder-runtime --nologo
if ($LASTEXITCODE -ne 0) { throw 'Decoder publish failed' }
# Build a fresh distribution: the runnable dist folder may now contain user data.
$packageRoot=Join-Path $PSScriptRoot ('build\package-' + [guid]::NewGuid().ToString('N'))
$distribution=Join-Path $packageRoot 'IFsCompanion'
try {
    & $DotnetPath publish desktop -c Release -r win-x64 --self-contained true -o $distribution --nologo
    if ($LASTEXITCODE -ne 0) { throw 'Desktop publish failed' }
    & $PythonPath packaging/build_shared_runtime.py --destination $distribution --model $ModelVettingPath
    if ($LASTEXITCODE -ne 0) { throw 'Shared Python packaging failed' }
    foreach ($file in @('USER_GUIDE.txt','LICENSE','THIRD_PARTY_NOTICES.txt','packaging\INSTALLATION_NOTICE.txt')) {
        Copy-Item -LiteralPath $file -Destination $distribution
    }
    New-Item -ItemType Directory -Force 'release' | Out-Null
    Copy-Item -LiteralPath 'licenses' -Destination $distribution -Recurse -Force
    # A runnable dist checkout may be open. Publish from staging without touching it.
    & $InnoPath /Q "/DDistributionDir=$distribution" packaging/installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    $versionMatch=Select-String -LiteralPath 'packaging\installer.iss' -Pattern '^#define AppVersion "([^"]+)"$'
    if (-not $versionMatch) { throw 'Installer version is missing' }
    $appVersion=$versionMatch.Matches[0].Groups[1].Value
    Compress-Archive -Path $distribution -DestinationPath "release\IFsCompanion-Portable-$appVersion-win-x64.zip" -Force
    Get-ChildItem -LiteralPath 'release' -File | Where-Object { $_.Name -like "IFsCompanion-*-$appVersion-win-x64.*" } | ForEach-Object {
        $hash=Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        "$($hash.Hash.ToLowerInvariant())  $($_.Name)"
    } | Set-Content -LiteralPath "release\SHA256SUMS-$appVersion.txt" -Encoding ascii
    & (Join-Path $PSScriptRoot 'packaging\prune-releases.ps1') -ReleaseDirectory (Join-Path $PSScriptRoot 'release') -Version $appVersion
}
finally {
    if (Test-Path -LiteralPath $packageRoot) {
        $resolvedPackageRoot=(Resolve-Path -LiteralPath $packageRoot).Path
        $resolvedBuildRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'build')).Path
        if ((Split-Path -Parent $resolvedPackageRoot) -ne $resolvedBuildRoot -or (Split-Path -Leaf $resolvedPackageRoot) -notmatch '^package-[a-f0-9]{32}$') { throw 'Unexpected package staging path' }
        Remove-Item -LiteralPath $resolvedPackageRoot -Recurse -Force
    }
}
Write-Output 'IFsCompanion Windows installer and portable ZIP are in release.'
