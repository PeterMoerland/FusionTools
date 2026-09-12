<#
.SYNOPSIS
    Zet een uitgave van de Fusion add-in klaar op een share voor de collega's.

.DESCRIPTION
    Draait eerst de tests en kopieert dan de add-in naar een genummerde map
    onder -Doel, met install.ps1 en Installeer.cmd ernaast. Collega's hebben
    daarmee geen toegang tot de broncode nodig: ze dubbelklikken op
    Installeer.cmd vanaf de share.

    De map heet naar de datum en het tijdstip, zodat een oude uitgave blijft
    staan en je kunt terugvallen als er iets niet blijkt te werken. Daarnaast
    wijst 'laatste' altijd naar de laatste uitgave.

.EXAMPLE
    .\publish.ps1
    Publiceert naar de standaardmap op de share.

.EXAMPLE
    .\publish.ps1 -Doel "\\server\Apps\MdeFusionTools"
#>
param(
    [string]$Doel = '\\172.16.1.4\data\Fusion PCB\Apps\MdeFusionTools',

    # De vaste map die altijd naar de laatste uitgave wijst. Niet 'huidig' zoals
    # bij de Inventor-tools: die naam is op de NAS blijven hangen als een
    # onzichtbare, ontoegankelijke map die "al bestaat" en niet weg te krijgen is.
    [string]$VasteMap = 'laatste',

    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$addin = Join-Path $projectRoot 'addin\MdeFusionTools'

if (-not (Test-Path (Join-Path $addin 'MdeFusionTools.py'))) {
    throw "Add-in niet gevonden: $addin"
}

# De map zelf mag ontbreken, de map erboven niet: zo wordt een typefout in het pad
# een foutmelding in plaats van een nieuwe map op een verkeerde plek.
if (-not (Test-Path $Doel)) {
    $bovenliggend = Split-Path $Doel -Parent

    if (-not $bovenliggend -or -not (Test-Path $bovenliggend)) {
        throw "Het pad bestaat niet of is niet bereikbaar: $Doel`nLet op: een gekoppelde letter zoals Z: is onzichtbaar in een PowerShell die als beheerder draait; gebruik dan het volledige netwerkpad."
    }

    New-Item -ItemType Directory -Path $Doel -Force | Out-Null
    Write-Host "Doelmap aangemaakt: $Doel" -ForegroundColor DarkGray
}

if (-not $SkipTests) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        Write-Host "Tests..." -ForegroundColor Cyan
        & $python.Source -m unittest discover -s (Join-Path $projectRoot 'tests')
        if ($LASTEXITCODE -ne 0) { throw "Tests mislukt; er is niets gepubliceerd." }
    } else {
        Write-Host "Geen python gevonden; tests overgeslagen." -ForegroundColor Yellow
    }
}

$stempel = Get-Date -Format 'yyyy-MM-dd-HHmm'
$uitgave = Join-Path $Doel $stempel
$payload = Join-Path $uitgave 'payload\MdeFusionTools'

New-Item -ItemType Directory -Path $payload -Force | Out-Null
Copy-Item -Path (Join-Path $addin '*') -Destination $payload -Recurse -Force

# Gecompileerde bestanden van deze werkplek horen niet in de uitgave.
Get-ChildItem -Path $payload -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force

# Niet via ConvertFrom-Json: het manifest heeft een lege sleutel ("") in
# description en daar struikelt PowerShell 5.1 over.
$manifestTekst = Get-Content (Join-Path $payload 'MdeFusionTools.manifest') -Raw
$versieNummer = if ($manifestTekst -match '"version"\s*:\s*"([^"]+)"') { $Matches[1] } else { '?' }
$versie = "$versieNummer ($stempel)"
Set-Content -Path (Join-Path $payload 'versie.txt') -Value $versie -Encoding utf8

Copy-Item -Path (Join-Path $projectRoot 'install.ps1') -Destination $uitgave -Force
Copy-Item -Path (Join-Path $projectRoot 'Installeer.cmd') -Destination $uitgave -Force

# 'huidig' wijst altijd naar de laatste uitgave, zodat de snelkoppeling die de
# collega's gebruiken niet elke keer verandert.
#
# De map zelf blijft staan en alleen de inhoud wordt vervangen. Een map op de
# share verwijderen en meteen opnieuw aanmaken liet op de NAS een map achter die
# voor niemand meer toegankelijk was ("Toegang geweigerd", ook voor rd).
$huidig = Join-Path $Doel $VasteMap
try {
    if (Test-Path $huidig) {
        Get-ChildItem $huidig -Force | Remove-Item -Recurse -Force
    } else {
        New-Item -ItemType Directory -Path $huidig -Force | Out-Null
    }
    Copy-Item -Path (Join-Path $uitgave '*') -Destination $huidig -Recurse -Force
} catch {
    Write-Host ""
    Write-Host "De uitgave staat klaar in $uitgave, maar '$VasteMap' kon niet worden bijgewerkt:" -ForegroundColor Yellow
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "Laat de map $huidig op de server verwijderen en draai publish.ps1 opnieuw, of verwijs de collega's naar $uitgave\Installeer.cmd." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Uitgave:  $uitgave" -ForegroundColor Green
Write-Host "Versie:   $versie" -ForegroundColor Green
Write-Host "Laatste:  $huidig" -ForegroundColor Green
Write-Host ""
Write-Host "De collega's dubbelklikken op:" -ForegroundColor Cyan
Write-Host "  $huidig\Installeer.cmd" -ForegroundColor Cyan
Write-Host "en starten daarna Fusion (opnieuw)." -ForegroundColor Cyan
