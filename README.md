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

    verkenning/     eenmalige scripts die vastleggen wat de Electronics-API prijsgeeft
    addin/          de add-in: MdeFusionTools
    tests/          tests voor het BOM-deel, buiten Fusion te draaien

Fusion-add-ins zijn Python (Fusion levert zijn eigen interpreter mee, 3.14).
Een add-in bestaat uit een map met een `.py` en een `.manifest` met dezelfde
naam, geplaatst in:

    %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\<Naam>\

Scripts staan in `...\API\Scripts\<Naam>\` en zijn te starten via
Utilities → Add-Ins (Shift+S).

## Hoe het werkt

De knop **PCB-uitvoer** staat op het tabblad Manufacturing van de PCB-editor
(paneel MDE). Hij opent een palet dat vraagt welke `.cam`-job je wilt gebruiken
(vooraf gekozen op het aantal koperlagen) en zet dan `<uitvoermap>\<board>_<datum>.zip`
neer, met dezelfde indeling als de zip van Fusions eigen CAM-processor:

    CAMOutputs/GerberFiles/...      Gerber en drill, door de CAM-processor van Fusion
    CAMOutputs/Assembly/...         stuklijst (BOM) en pick-and-place (CPL), door de add-in

De CAM-processor draait zonder venster via het interne tekstcommando

    Electron.mfgexport <uitvoermap> <job.cam>

Wat daarover is vastgesteld (Fusion 2705.1.15):

- Het geeft direct `CAM output generated.` terug en schrijft de bestanden er
  vlak achteraan als losse bestanden, geen zip.
- Ze komen niet in de opgegeven map maar ernaast:
  `<bovenliggende map>\<jobnaam>\<jobnaam>.gbr\CAMOutputs\...`. De add-in
  zoekt de map `CAMOutputs` daarom op en verplaatst hem naar de boardmap.
- Alleen de secties `gerber` en `drill` leveren iets op. `odb++`, `image` en
  `drawing` geven een foutvenster; `assembly` levert stil niets. De add-in
  geeft het commando een afgeslankte kopie van de job en maakt BOM en CPL zelf.
- De CPL heeft precies het formaat van Fusion: `Name,X,Y,Angle,Value,Package`,
  millimeters met twee decimalen (interne eenheid 1/320000 mm), een bestand per
  zijde (`PnP_<board>_CPL_front.csv` en `_back.csv`), gewone tekstsortering.
- De BOM is algemeen: `QTY, Reference Designator, Value, Footprint, MPN,
  MANUFACTURER, DESCRIPTION, PACKAGE_SIZE`, elk veld tussen
  aanhalingstekens. Onderdelen met fabrikant `MDE` (soldeerpads, montagegaten)
  blijven eruit; niet-geplaatste ook.

Het keuzevenster is een palet (`resources/pcbuitvoer.html`) en geen
commandovenster: in de PCB-editor is altijd een EAGLE-commando actief dat een
API-commando onderbreekt zodra de muis boven het board komt, waardoor zo'n
venster verdwijnt of zichzelf uitvoert. Een palet blijft staan. De export zelf
start via een custom event nadat het palet dicht is, anders weigert Fusion
mfgexport met "Execute failed due to reentrancy".

Instellingen staan in `%APPDATA%\MDE\FusionTools\instellingen.json`
(`uitvoermap`, `jobmap`, `laatste_job`); het logboek in
`%LOCALAPPDATA%\MDE\FusionTools\fusiontools.log`. De standaard jobmap is
`Z:\Fusion PCB\CAM processor job files`.

## Uitgeven en installeren

Een uitgave klaarzetten op de share (draait eerst de tests):

    .\publish.ps1

Dat maakt `\\172.16.1.4\data\Fusion PCB\Apps\MdeFusionTools\<datum-tijd>\`
met de add-in, `install.ps1` en `Installeer.cmd`, en ververst `laatste\` naar
die laatste uitgave. Een andere plek: `-Doel <pad>`. (De map heet niet `huidig`
zoals bij de Inventor-tools: die naam is op de NAS blijven hangen als een
onzichtbare map die "al bestaat" maar niet te openen of te verwijderen is.)

Collega's dubbelklikken op

    \\172.16.1.4\data\Fusion PCB\Apps\MdeFusionTools\laatste\Installeer.cmd

en starten Fusion (opnieuw). Dat kopieert de add-in naar
`%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\MdeFusionTools\`; Fusion
start hem daarna automatisch mee. Staat hij niet aan: Shift+S, tabblad
Add-Ins, MdeFusionTools, Run, met "Run on Startup" aangevinkt.

Handmatig installeren kan ook: kopieer `addin\MdeFusionTools` naar die map.

## Tests

    python -m unittest discover -s tests -v
