param([switch]$SyncOnly)
$ErrorActionPreference = 'Stop'
$releaseRoot = Join-Path $PSScriptRoot 'release'
$latest = Get-ChildItem -LiteralPath $releaseRoot -Filter 'IFsCompanion-Portable-*-win-x64.zip' -File |
    Where-Object { $_.Name -match '^IFsCompanion-Portable-(\d+\.\d+\.\d+)-win-x64\.zip$' } |
    Sort-Object { [version]($_.Name -replace '^IFsCompanion-Portable-|\-win-x64\.zip$','') } -Descending |
    Select-Object -First 1
if (-not $latest) { throw 'No local release found. Run build.ps1 first.' }
$version = $latest.Name -replace '^IFsCompanion-Portable-|\-win-x64\.zip$',''
$digest = (Get-FileHash -LiteralPath $latest.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = Join-Path $releaseRoot "SHA256SUMS-$version.txt"
if (@(Get-Content -LiteralPath $manifest) -cnotcontains "$digest  $($latest.Name)") { throw 'Portable release checksum verification failed.' }
$distRoot = Join-Path $PSScriptRoot 'dist'
$appRoot = Join-Path $distRoot 'IFsCompanion'
$appPath = Join-Path $appRoot 'IFsCompanion.exe'
$marker = Join-Path $appRoot '.local-release.sha256'
if (!(Test-Path -LiteralPath $appPath) -or !(Test-Path -LiteralPath $marker) -or (Get-Content -LiteralPath $marker -Raw).Trim() -ne $digest) {
    $running = @(Get-Process IFsCompanion -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $appPath })
    if ($running.Count) { throw 'Close the Companion dist window before updating it, then run start.ps1 again.' }
    New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
    $stage = Join-Path $distRoot ('launch-' + [guid]::NewGuid().ToString('N'))
    try {
        Expand-Archive -LiteralPath $latest.FullName -DestinationPath $stage
        $source = Join-Path $stage 'IFsCompanion'
        if (!(Test-Path -LiteralPath (Join-Path $source 'IFsCompanion.exe'))) { throw 'Portable package is missing its executable.' }
        foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
            $relative = $file.FullName.Substring($source.Length + 1)
            if ($relative -eq 'storage.json' -or $relative -match '^data[\\/]') { continue }
            $target = Join-Path $appRoot $relative
            $parent = Split-Path -Parent $target
            $cursor = $parent
            while ($cursor.Length -ge $appRoot.Length) {
                if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing to update through a filesystem link: $cursor" }
                $cursor = Split-Path -Parent $cursor
            }
            if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing to replace filesystem link: $target" }
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            Copy-Item -LiteralPath $file.FullName -Destination $target -Force
        }
        Set-Content -LiteralPath $marker -Value $digest -Encoding ascii
        Write-Output "Updated dist to IFsCompanion $version."
    }
    finally {
        if (Test-Path -LiteralPath $stage) {
            $resolved = Get-Item -LiteralPath $stage
            if ($resolved.Parent.FullName -ne (Resolve-Path -LiteralPath $distRoot).Path -or $resolved.Name -notmatch '^launch-[a-f0-9]{32}$' -or ($resolved.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected launcher staging path.' }
            Remove-Item -LiteralPath $resolved.FullName -Recurse -Force
        }
    }
}
if (!$SyncOnly) { Start-Process -FilePath $appPath -WorkingDirectory $appRoot }
