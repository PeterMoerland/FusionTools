# MDE FusionTools

Add-in voor Autodesk Fusion (Electronics) die de uitvoer van een PCB in één
handeling klaarzet voor productie en assemblage: Gerber, BOM en CPL.

## Waarom

Fusion exporteert Gerber en CPL prima via de CAM-processor, maar de BOM die
daaruit komt is een CSV zonder aanhalingstekens. Een komma in een omschrijving
wordt daardoor een kolomgrens en de regel verschuift. Deze add-in schrijft de
BOM zelf, correct gequote, en bundelt alles in één uitvoermap per board.

Het BOM-formaat is algemeen. Het omzetten naar wat een specifieke
PCBA-leverancier wil, gebeurt daarna.

## Opzet

    verkenning/     eenmalig script dat vastlegt wat de Electronics-API prijsgeeft
    addin/          de add-in zelf (volgt)

Fusion-add-ins zijn Python (Fusion levert zijn eigen interpreter mee, 3.14).
Een add-in bestaat uit een map met een `.py` en een `.manifest` met dezelfde
naam, geplaatst in:

    %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\<Naam>\

Scripts staan in `...\API\Scripts\<Naam>\` en zijn te starten via
Utilities → Add-Ins (Shift+S).

## Stand van zaken

Verkenning. Zie `verkenning/` en het rapport dat het script wegschrijft naar
`%LOCALAPPDATA%\MDE\FusionTools\verkenning.txt`.
