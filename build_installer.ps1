# Build D&D 3.5 Character Sheet Windows installer
$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

$versionFile = Join-Path $ProjectDir "version.json"
if (-not (Test-Path $versionFile)) {
    throw "version.json not found in $ProjectDir"
}
$versionJson = Get-Content $versionFile -Raw | ConvertFrom-Json
$appVersion = [string]$versionJson.version
if ([string]::IsNullOrWhiteSpace($appVersion)) {
    throw "version.json must include a version value."
}
$distFolder = "D&D Before v$appVersion"
$exeName = "$distFolder.exe"

Write-Host "==> Building D&D Before v$appVersion ..."
Write-Host "==> Installing build dependencies..."
python -m pip install --upgrade pip
python -m pip install pyinstaller pillow customtkinter

Write-Host "==> Preparing assets..."
if (-not (Test-Path "icon.png")) {
    throw "icon.png not found in $ProjectDir"
}
if (-not (Test-Path "feats.json")) {
    Copy-Item -Path "Feats.json" -Destination "feats.json" -Force
}

Write-Host "==> Building application with PyInstaller..."
$env:APP_VERSION = $appVersion
Get-Process -Name "D&D Before*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
if (Test-Path "build") { Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue }
python -m PyInstaller --noconfirm --clean "dnd_character_sheet.spec"

$ExePath = Join-Path $ProjectDir "dist\$distFolder\$exeName"
if (-not (Test-Path $ExePath)) {
    throw "Build failed: executable not found at $ExePath"
}

$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($Iscc) {
    Write-Host "==> Building installer with Inno Setup..."
    if (Test-Path "installer_output") { Remove-Item -Recurse -Force "installer_output" }
    $issDefines = @(
        "/DMyAppVersion=$appVersion",
        "/DMyAppExeName=D&D Before v$appVersion.exe",
        "/DMyBuildDir=dist\D&D Before v$appVersion"
    )
    & $Iscc @issDefines "installer.iss"
    $SetupExe = Get-ChildItem "installer_output\*Setup*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($SetupExe) {
        $desktopPath = Join-Path ([Environment]::GetFolderPath("Desktop")) $SetupExe.Name
        Copy-Item -Path $SetupExe.FullName -Destination $desktopPath -Force
        Write-Host ""
        Write-Host "SUCCESS: Installer created at:"
        Write-Host "  $($SetupExe.FullName)"
        Write-Host "Copied to Desktop:"
        Write-Host "  $desktopPath"
    } else {
        throw "Inno Setup finished but no installer exe was found."
    }
} else {
    Write-Host ""
    Write-Host "Built application (portable folder):"
    Write-Host "  $ExePath"
    Write-Host ""
    Write-Host "Inno Setup 6 was not found. Install it from:"
    Write-Host "  https://jrsoftware.org/isdl.php"
    Write-Host "Then re-run this script to create the setup installer."
}