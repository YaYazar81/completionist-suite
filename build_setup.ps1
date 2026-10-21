# Baut dist\<App>-Setup-<Version>.exe fuer CompletionistPDF, -MD und -QR
#
#   .\build_setup.ps1                     CompletionistQR (wie bisher)
#   .\build_setup.ps1 -App pdf            CompletionistPDF
#   .\build_setup.ps1 -App md             CompletionistMD
#   .\build_setup.ps1 -App all            alle drei nacheinander
#   .\build_setup.ps1 -App md -SkipBuild  nur das Setup aus vorhandenem dist\CompletionistMD
#
# Braucht Inno Setup 6:  winget install JRSoftware.InnoSetup

param(
    [ValidateSet("qr", "pdf", "md", "all")]
    [string]$App = "qr",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

# Name und Paket, aus dem die Version kommt
$apps = [ordered]@{
    pdf = @{ Name = "CompletionistPDF"; Package = "core" }
    md  = @{ Name = "CompletionistMD";  Package = "mdeditor" }
    qr  = @{ Name = "CompletionistQR";  Package = "completionistqr" }
}

# --- Inno Setup finden -----------------------------------------------------
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    # Inno Setup installiert sich je nach Variante systemweit oder nur fuer den
    # angemeldeten Benutzer.
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
                     "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                     "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if (-not $iscc) {
    Write-Error "ISCC.exe nicht gefunden. Inno Setup installieren:  winget install JRSoftware.InnoSetup"
}

function Build-Setup([string]$key) {
    $name = $apps[$key].Name

    # --- Version aus dem Paket ---------------------------------------------
    $version = & $py -c "import $($apps[$key].Package) as p; print(p.__version__)"
    if ($LASTEXITCODE -ne 0) { Write-Error "Version von $name konnte nicht gelesen werden." }
    Write-Host "$name $version"

    # --- Programmordner ----------------------------------------------------
    if (-not $SkipBuild) {
        # Kein $ErrorActionPreference-Problem: PyInstaller schreibt Infos nach
        # stderr, geprueft wird $LASTEXITCODE.
        $ErrorActionPreference = "Continue"
        & $py build_exe.py --app $key 2>&1 |
            Select-String -Pattern "ERROR|Traceback|Fertig|Dateifilter" | ForEach-Object { "$_" }
        $ErrorActionPreference = "Stop"
        if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller-Build von $name fehlgeschlagen." }
    }
    if (-not (Test-Path "dist\$name\$name.exe")) {
        Write-Error "dist\$name\ fehlt -- erst ohne -SkipBuild laufen lassen."
    }

    # --- Setup -------------------------------------------------------------
    & $iscc "/DAppVersion=$version" "installer\$name.iss" |
        Select-String -Pattern "Error|Warning|Successful|compile" | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { Write-Error "Inno Setup fuer $name fehlgeschlagen." }

    $out = "dist\$name-Setup-$version.exe"
    $mb = "{0:N1}" -f ((Get-Item $out).Length / 1MB)
    Write-Host ""
    Write-Host "Fertig: $PSScriptRoot\$out  ($mb MB)"
}

$keys = if ($App -eq "all") { @($apps.Keys) } else { @($App) }
foreach ($k in $keys) { Build-Setup $k }
