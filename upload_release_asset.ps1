# Upload the latest installer to the GitHub Release matching version.json.
# Requires a GitHub personal access token with repo scope:
#   $env:GITHUB_TOKEN = "ghp_..."
param(
    [string]$Token = $env:GITHUB_TOKEN
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

$versionJson = Get-Content (Join-Path $ProjectDir "version.json") -Raw | ConvertFrom-Json
$version = [string]$versionJson.version
$owner = [string]$versionJson.github_owner
$repo = [string]$versionJson.github_repo
$tag = "v$version"

$setupExe = Get-ChildItem "installer_output\*Setup*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setupExe) {
    throw "Run build_installer.ps1 first."
}
if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Host "No GITHUB_TOKEN set. Upload manually:"
    Write-Host "  1. Open https://github.com/$owner/$repo/releases/tag/$tag"
    Write-Host "  2. Edit the release and delete the old Setup .exe asset (if present)."
    Write-Host "  3. Attach: $($setupExe.FullName)"
    Write-Host "  4. Publish / save."
    exit 0
}

$headers = @{
    Authorization = "Bearer $Token"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$owner/$repo/releases/tags/$tag" -Headers $headers
foreach ($asset in $release.assets) {
    if ($asset.name -like "*Setup*.exe") {
        Invoke-RestMethod -Method Delete -Uri "https://api.github.com/repos/$owner/$repo/releases/assets/$($asset.id)" -Headers $headers | Out-Null
        Write-Host "Deleted old asset: $($asset.name)"
    }
}
$uploadUrl = $release.upload_url -replace "\{\?name,label\}", ""
$assetName = if ($setupExe.Name -match '[&]') {
    "DnD_Before_v$version`_Setup.exe"
} else {
    $setupExe.Name
}
$uploadHeaders = @{
    Authorization = "Bearer $Token"
    Accept = "application/vnd.github+json"
    "Content-Type" = "application/octet-stream"
}
Invoke-RestMethod -Method Post -Uri "$uploadUrl`?name=$assetName" -Headers $uploadHeaders -InFile $setupExe.FullName | Out-Null
Write-Host "Uploaded $assetName to release $tag"