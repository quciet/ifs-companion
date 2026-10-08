param(
    [Parameter(Mandatory=$true)][string]$ReleaseDirectory,
    [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference='Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$') { throw 'Invalid release version' }
$releaseRoot=(Resolve-Path -LiteralPath $ReleaseDirectory).Path
$keep=@("IFsCompanion-Setup-$Version-win-x64.exe", "IFsCompanion-Portable-$Version-win-x64.zip", "SHA256SUMS-$Version.txt")
# Validate both completed packages before deleting any earlier release.
$manifest=Join-Path $releaseRoot $keep[2]
$lines=@(Get-Content -LiteralPath $manifest)
foreach ($name in $keep[0..1]) {
    $package=Get-Item -LiteralPath (Join-Path $releaseRoot $name)
    if ($package.PSIsContainer -or $package.Length -eq 0) { throw "Missing or empty package: $name" }
    $hash=(Get-FileHash -LiteralPath $package.FullName -Algorithm SHA256).Hash
    $expected="$($hash.ToLowerInvariant())  $name"
    if ($lines -cnotcontains $expected) { throw "Release checksum mismatch: $name" }
}
$versionPattern='\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?'
foreach ($file in Get-ChildItem -LiteralPath $releaseRoot -File) {
    $isRelease=$file.Name -match "^(?:IFsCompanion|IFsModelVetting)-(?:Setup|Portable)-$versionPattern-win-x64\.(?:exe|zip)$" -or $file.Name -match "^SHA256SUMS-$versionPattern\.txt$"
    if ($isRelease -and $file.Name -notin $keep) {
        if ($file.Directory.FullName -ne $releaseRoot -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Unexpected cleanup target: $($file.FullName)" }
        Remove-Item -LiteralPath $file.FullName -ErrorAction Stop
        Write-Output "Removed older release: $($file.Name)"
    }
}
