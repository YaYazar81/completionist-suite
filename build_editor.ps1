# Baut das Tiptap-Bundle von CompletionistMD (assets/editor/tiptap.bundle.js)
# mit dem portablen Node aus tools/node -- PATH und System bleiben unberuehrt.
#
#   .\build_editor.ps1           einmal bauen
#   .\build_editor.ps1 -Watch    bei jeder Aenderung in editor-src/src neu bauen

param([switch]$Watch)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$node = Join-Path $root "tools\node"

if (-not (Test-Path (Join-Path $node "node.exe"))) {
    Write-Error "Kein Node unter $node -- Node-LTS-ZIP von nodejs.org dorthin entpacken."
}

$env:PATH = "$node;$env:PATH"
Push-Location (Join-Path $root "editor-src")
try {
    if (-not (Test-Path "node_modules")) {
        # Exakt die Versionen aus package-lock.json
        npm ci --no-fund --no-audit
    }
    if ($Watch) { node build.mjs --watch } else { node build.mjs }
}
finally {
    Pop-Location
}
