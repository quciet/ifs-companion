$ErrorActionPreference = 'Stop'
$appPath = Join-Path $PSScriptRoot 'dist\IFsCompanion\IFsCompanion.exe'
if (-not (Test-Path -LiteralPath $appPath)) { throw 'Build IFsCompanion first with ./build.ps1.' }
& $appPath
