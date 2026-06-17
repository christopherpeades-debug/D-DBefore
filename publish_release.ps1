# Build installer and print GitHub release upload steps.
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

$versionFile = Join-Path $ProjectDir "version.json"
if (-not (Test-Path $versionFile)) {
    throw "version.json not found."
}
$versionJson = Get-Content $versionFile -Raw | ConvertFrom-Json
$version = [string]$versionJson.version
$owner = [string]$versionJson.github_owner
$repo = [string]$versionJson.github_repo

if ([string]::IsNullOrWhiteSpace($version)) {
    throw "version.json must include a version value."
}

Write-Host "==> Building release v$version ..."
& "$ProjectDir\build_installer.ps1"

$setupExe = Get-ChildItem "installer_output\*Setup*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setupExe) {
    throw "Installer exe not found in installer_output."
}

Write-Host ""
Write-Host "SUCCESS: Built $($setupExe.Name)"
Write-Host ""
Write-Host "Next steps on GitHub:"
Write-Host "  1. Commit and push your changes to the repository."
Write-Host "  2. Open: https://github.com/$owner/$repo/releases/new"
Write-Host "  3. Choose tag: v$version"
Write-Host "  4. Release title: D&D Before v$version"
Write-Host "  5. Attach this file as a release asset:"
Write-Host "       $($setupExe.FullName)"
Write-Host "  6. Publish the release."
Write-Host ""
Write-Host "Players can then use Hamburger menu -> Check for Updates in the app."