<#
.SYNOPSIS
    Installeert de MDE FusionTools add-in op deze werkplek.

.DESCRIPTION
    Dit script heeft de broncode niet nodig. Het kopieert een kant-en-klare
    uitgave naar de add-in map van Fusion voor de huidige gebruiker:

        %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\MdeFusionTools\

    Fusion leest die map bij het opstarten; de add-in start dan automatisch
    mee (runOnStartup in het manifest). Draait Fusion al, dan wordt de nieuwe
    versie pas na een herstart van Fusion gebruikt.

    Instellingen van de gebruiker staan elders (%APPDATA%\MDE\FusionTools) en
    blijven bij een nieuwe versie behouden.

.EXAMPLE
    .\install.ps1
    Installeert de uitgave die naast dit script staat (map payload).
#>
param(
    [string]$Payload
)

$ErrorActionPreference = 'Stop'

if (-not $Payload) { $Payload = Join-Path $PSScriptRoot 'payload\MdeFusionTools' }
if (-not (Test-Path (Join-Path $Payload 'MdeFusionTools.py'))) {
    throw "MdeFusionTools.py niet gevonden in: $Payload`nStaat dit script naast de uitgave?"
}

$addinsRoot = Join-Path $env:APPDATA 'Autodesk\Autodesk Fusion 360\API\AddIns'
if (-not (Test-Path (Split-Path $addinsRoot -Parent))) {
    throw "De API-map van Fusion bestaat niet: $(Split-Path $addinsRoot -Parent)`nIs Fusion op deze werkplek geinstalleerd en al eens gestart?"
}
New-Item -ItemType Directory -Path $addinsRoot -Force | Out-Null

$doel = Join-Path $addinsRoot 'MdeFusionTools'

# Schoon vervangen: bestanden die in een nieuwe versie niet meer bestaan
# moeten ook weg, anders blijft Fusion oude modules laden.
if (Test-Path $doel) { Remove-Item $doel -Recurse -Force }
New-Item -ItemType Directory -Path $doel -Force | Out-Null
Copy-Item -Path (Join-Path $Payload '*') -Destination $doel -Recurse -Force

$versie = ''
$versieBestand = Join-Path $doel 'versie.txt'
if (Test-Path $versieBestand) { $versie = (Get-Content $versieBestand -Raw).Trim() }

Write-Host ""
Write-Host "MDE FusionTools $versie is geinstalleerd in:" -ForegroundColor Green
Write-Host "  $doel"
Write-Host ""

$fusion = Get-Process -Name 'Fusion360' -ErrorAction SilentlyContinue
if ($fusion) {
    Write-Host "Fusion draait nog. Sluit Fusion af en start hem opnieuw; dan wordt deze versie gebruikt." -ForegroundColor Yellow
} else {
    Write-Host "Start Fusion. Open een PCB en kijk op het tabblad Manufacturing naar het paneel MDE." -ForegroundColor Cyan
}
Write-Host "Staat de add-in niet aan: Shift+S, tabblad Add-Ins, MdeFusionTools, Run (en vink Run on Startup aan)." -ForegroundColor DarkGray
