# Baut dist\QR-Online-Setup-<Version>.exe
#
#   .\build_setup.ps1             Programmordner (PyInstaller) und Setup
#   .\build_setup.ps1 -SkipBuild  nur das Setup aus vorhandenem dist\QR-Online
#
# Erwartet die venv der Suite (..\.venv) mit requirements.txt dieses Ordners
# und pyinstaller. Braucht Inno Setup 6:  winget install JRSoftware.InnoSetup

param([switch]$SkipBuild)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = "..\.venv\Scripts\python.exe"

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
                     "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                     "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if (-not $iscc) {
    Write-Error "ISCC.exe nicht gefunden. Inno Setup installieren:  winget install JRSoftware.InnoSetup"
}

$version = & $py -c "import qronline as p; print(p.__version__)"
if ($LASTEXITCODE -ne 0) { Write-Error "Version konnte nicht gelesen werden." }
Write-Host "QR-Online $version"

if (-not $SkipBuild) {
    $ErrorActionPreference = "Continue"
    & $py build_exe.py 2>&1 |
        Select-String -Pattern "ERROR|Traceback|Fertig|Lizenzen" | ForEach-Object { "$_" }
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller-Build fehlgeschlagen." }
}
if (-not (Test-Path "dist\QR-Online\QR-Online.exe")) {
    Write-Error "dist\QR-Online\ fehlt -- erst ohne -SkipBuild laufen lassen."
}

& $iscc "/DAppVersion=$version" "installer\QR-Online.iss" |
    Select-String -Pattern "Error|Warning|Successful|compile" | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { Write-Error "Inno Setup fehlgeschlagen." }

$out = "dist\QR-Online-Setup-$version.exe"
$mb = "{0:N1}" -f ((Get-Item $out).Length / 1MB)
Write-Host ""
Write-Host "Fertig: $PSScriptRoot\$out  ($mb MB)"
