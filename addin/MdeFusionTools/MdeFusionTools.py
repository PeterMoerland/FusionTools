"""MDE FusionTools: PCB-uitvoer in een handeling.

Een knop op het tabblad Manufacturing van de PCB-editor. Die vraagt welke
CAM-job je wilt gebruiken en zet dan alles voor productie en assemblage in een
zip in de uitvoermap:

    <uitvoermap>\\<board>_<datum>.zip

met daarin, zoals de CAM-processor het ook bundelt:

    CAMOutputs/GerberFiles/...   Gerber en drill, via Electron.mfgexport
    CAMOutputs/Assembly/...      stuklijst en pick-and-place, door de add-in

De CAM-processor van Fusion deed Gerber en pick-and-place goed, maar de
stuklijst eruit was onbruikbaar door ontbrekende aanhalingstekens. Het
tekstcommando Electron.mfgexport doet de CAM-processor zonder venster, maar
levert alleen Gerber en drill; de rest maakt de add-in daarom zelf.
"""

import datetime
import json
import os
import re
import shutil
import time
import traceback

import adsk.core
import adsk.electron

from . import bom
from . import camjob
from . import cpl
from . import instellingen

COMMANDO_ID = "MDE_PcbUitvoer"
PANEEL_ID = "MDE_Paneel"
TITEL = "MDE PCB-uitvoer"

INVOER_JOB = "job"
INVOER_UITVOERMAP = "uitvoermap"
INVOER_ANDERE_UITVOERMAP = "andere_uitvoermap"
INVOER_ANDERE_JOBMAP = "andere_jobmap"

STANDAARD_JOBMAP = r"Z:\Fusion PCB\CAM processor job files"

# De export start een ander commando (mfgexport). Dat mag niet zolang ons eigen
# commando nog bezig is ("Execute failed due to reentrancy"). De execute-handler
# geeft daarom alleen de keuzes door via deze gebeurtenis; de handler daarvan
# draait op de hoofddraad zodra het venster gesloten is.
GEBEURTENIS_ID = "MDE_PcbUitvoerStarten"

# mfgexport geeft meteen antwoord en schrijft de bestanden er vlak achteraan.
# Zo lang wachten we hoogstens, met tussenpozen waarin Fusion zijn werk kan doen.
MFGEXPORT_WACHTTIJD_SECONDEN = 30
MFGEXPORT_PEIL_SECONDEN = 0.25

_app = None
_ui = None

# Handlers moeten in leven blijven: laat je ze los, dan ruimt Python ze op en doet
# de knop niets meer.
_handlers = []


def run(context):
    global _app, _ui
    _app = adsk.core.Application.get()
    _ui = _app.userInterface

    try:
        iconen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "pcbuitvoer")
        definitie = _ui.commandDefinitions.itemById(COMMANDO_ID)
        if definitie is None:
            definitie = _ui.commandDefinitions.addButtonDefinition(
                COMMANDO_ID,
                "PCB-uitvoer",
                "Gerber, drill, stuklijst en pick-and-place van dit board in een zip, "
                "met een gekozen CAM-job.",
                iconen)
        else:
            definitie.resourceFolder = iconen

        aangemaakt = _Aangemaakt()
        definitie.commandCreated.add(aangemaakt)
        _handlers.append(aangemaakt)

        try:
            _app.unregisterCustomEvent(GEBEURTENIS_ID)
        except Exception:
            pass
        gebeurtenis = _app.registerCustomEvent(GEBEURTENIS_ID)
        starten = _Starten()
        gebeurtenis.add(starten)
        _handlers.append(starten)

        _plaats_knop(definitie)
    except Exception:
        instellingen.log("Starten mislukt:\n" + traceback.format_exc())
        if _ui:
            _ui.messageBox("MDE FusionTools kon niet starten:\n\n" + traceback.format_exc(), TITEL)


def stop(context):
    try:
        for ws_id, tab_id in _geplaatst:
            try:
                tab = _ui.workspaces.itemById(ws_id).toolbarTabs.itemById(tab_id)
                paneel = tab.toolbarPanels.itemById(PANEEL_ID) if tab else None
                if paneel:
                    knop = paneel.controls.itemById(COMMANDO_ID)
                    if knop:
                        knop.deleteMe()
                    if paneel.controls.count == 0:
                        paneel.deleteMe()
            except Exception:
                pass
        _geplaatst.clear()

        definitie = _ui.commandDefinitions.itemById(COMMANDO_ID)
        if definitie:
            definitie.deleteMe()

        try:
            _app.unregisterCustomEvent(GEBEURTENIS_ID)
        except Exception:
            pass

        _handlers.clear()
        instellingen.log("Add-in gestopt.")
    except Exception:
        instellingen.log("Stoppen mislukt:\n" + traceback.format_exc())


# De PCB-editor van Fusion. Het id met de spelfout is van Autodesk; daarom eerst
# opzoeken op producttype en pas dan terugvallen op de letterlijke naam.
PCB_PRODUCTTYPE = "ElectronPcbDocProductType"
PCB_WERKRUIMTE_ID = "BoardLayoutEnvironement"

# Het tabblad waar de knop komt: Manufacturing, naast de CAM-uitvoer van Fusion
# zelf. Daar hoort een uitvoerknop; op DESIGN stond hij alleen in de weg.
PCB_TABBLADEN = ("EaglePcbManufacturing",)

_geplaatst = []   # (werkruimte-id, tab-id) van elk paneel dat we hebben gemaakt


def _plaats_knop(definitie):
    """Zet de knop in een eigen paneel MDE op de werkbalk van de PCB-editor.

    De werkbalk van deze werkruimte is niet via workspace.toolbarPanels te
    bereiken (dat geeft een InternalValidationError), wel via de tabbladen:
    toolbarTabs -> toolbarPanels. Zo staat het ook in de nieuwere API-voorbeelden
    van Autodesk.
    """
    werkruimte = _pcb_werkruimte()
    if werkruimte is None:
        instellingen.log("PCB-werkruimte niet gevonden; de knop is nergens geplaatst.")
        return

    for tab_id in PCB_TABBLADEN:
        try:
            tab = werkruimte.toolbarTabs.itemById(tab_id)
            if tab is None:
                instellingen.log(f"Tabblad {tab_id} niet gevonden in {werkruimte.id}.")
                continue

            paneel = tab.toolbarPanels.itemById(PANEEL_ID)
            if paneel is None:
                paneel = tab.toolbarPanels.add(PANEEL_ID, "MDE")

            knop = paneel.controls.itemById(COMMANDO_ID)
            if knop is None:
                knop = paneel.controls.addCommand(definitie)
            # Elke keer opnieuw, niet alleen bij aanmaken: Fusion onthoudt de
            # indeling van een paneel, en zonder promotie staat de knop verstopt
            # in een uitklaplijst "MDE" in plaats van als grote knop.
            knop.isPromotedByDefault = True
            knop.isPromoted = True
            knop.isVisible = True

            _geplaatst.append((werkruimte.id, tab_id))
            instellingen.log(f"Knop geplaatst: {werkruimte.id} / {tab_id} ({tab.name}).")
        except Exception as ex:
            instellingen.log(f"Plaatsen op {tab_id} mislukt: {type(ex).__name__}: {ex}")


def _pcb_werkruimte():
    try:
        lijst = _ui.workspacesByProductType(PCB_PRODUCTTYPE)
        for i in range(lijst.count):
            ws = lijst.item(i)
            if ws.id == PCB_WERKRUIMTE_ID or "Board" in ws.id:
                return ws
        if lijst.count > 0:
            return lijst.item(0)
    except Exception as ex:
        instellingen.log(f"workspacesByProductType mislukt: {type(ex).__name__}: {ex}")

    return _ui.workspaces.itemById(PCB_WERKRUIMTE_ID)


# ---------------------------------------------------------------------------
# Het venster: welke job, welke map.
# ---------------------------------------------------------------------------

class _Aangemaakt(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            board = adsk.electron.Board.cast(_app.activeProduct)
            if board is None:
                _ui.messageBox("Open eerst het board (niet het schema).", TITEL)
                return

            opdracht = args.command
            opdracht.okButtonText = "Exporteren"
            opdracht.isRepeatable = False
            # In de PCB-editor is altijd een EAGLE-commando actief dat het onze
            # meteen onderbreekt. Standaard voert Fusion het commando dan uit
            # alsof je op OK drukte; het venster leek daardoor niet te wachten.
            opdracht.isExecutedWhenPreEmpted = False

            huidig = instellingen.laad()
            invoer = opdracht.commandInputs

            keuzelijst = invoer.addDropDownCommandInput(
                INVOER_JOB, "CAM-job", adsk.core.DropDownStyles.TextListDropDownStyle)
            keuzelijst.tooltip = "De .cam-job van de CAM-processor waarmee Gerber en drill gemaakt worden."
            _vul_jobs(keuzelijst, huidig, _koperlagen(board))

            invoer.addBoolValueInput(INVOER_ANDERE_JOBMAP, "Andere map met jobs...", False, "", False)
            invoer.itemById(INVOER_ANDERE_JOBMAP).tooltip = (
                "Nu: " + _jobmap(huidig) + "\nKies een andere map met .cam-bestanden.")

            boardnaam = _bestandsnaam(board.name) or "board"
            tekst = invoer.addTextBoxCommandInput(
                INVOER_UITVOERMAP, "Uitvoer in", _doelmap(huidig, boardnaam), 2, True)
            tekst.tooltip = "Hier komt de zip <board>_<datum>.zip."

            invoer.addBoolValueInput(INVOER_ANDERE_UITVOERMAP, "Andere uitvoermap...", False, "", False)

            gewijzigd = _InvoerGewijzigd(boardnaam, _koperlagen(board))
            opdracht.inputChanged.add(gewijzigd)
            _handlers.append(gewijzigd)

            uitvoeren = _Uitvoeren(board, boardnaam)
            opdracht.execute.add(uitvoeren)
            _handlers.append(uitvoeren)
        except Exception:
            instellingen.log("commandCreated mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Het venster kon niet worden opgebouwd:\n\n" + traceback.format_exc(), TITEL)


def _vul_jobs(keuzelijst, huidig, koperlagen):
    """Zet de .cam-bestanden uit de jobmap in de keuzelijst, met de passende vooraf gekozen."""
    keuzelijst.listItems.clear()
    jobs = camjob.lijst(_jobmap(huidig))
    gekozen = camjob.standaard(jobs, koperlagen, huidig.get("laatste_job"))
    for job in jobs:
        keuzelijst.listItems.add(os.path.basename(job), job == gekozen)
    if not jobs:
        keuzelijst.listItems.add("(geen .cam-bestanden in " + _jobmap(huidig) + ")", True)
    return jobs


class _InvoerGewijzigd(adsk.core.InputChangedEventHandler):
    """De twee 'Andere map...'-vinkjes werken als knoppen: aanvinken opent de mapkeuze."""

    def __init__(self, boardnaam, koperlagen):
        super().__init__()
        self._boardnaam = boardnaam
        self._koperlagen = koperlagen

    def notify(self, args):
        try:
            invoer = args.input
            if invoer.id not in (INVOER_ANDERE_UITVOERMAP, INVOER_ANDERE_JOBMAP) or not invoer.value:
                return
            invoer.value = False

            alle = args.inputs
            huidig = instellingen.laad()
            dialoog = _ui.createFolderDialog()

            if invoer.id == INVOER_ANDERE_UITVOERMAP:
                dialoog.title = "Kies de map waar de zip met de PCB-uitvoer komt"
                if dialoog.showDialog() != adsk.core.DialogResults.DialogOK:
                    return
                huidig["uitvoermap"] = dialoog.folder
                instellingen.bewaar(huidig)
                alle.itemById(INVOER_UITVOERMAP).text = _doelmap(huidig, self._boardnaam)
            else:
                dialoog.title = "Kies de map met .cam-jobs van de CAM-processor"
                if dialoog.showDialog() != adsk.core.DialogResults.DialogOK:
                    return
                huidig["jobmap"] = dialoog.folder
                instellingen.bewaar(huidig)
                _vul_jobs(alle.itemById(INVOER_JOB), huidig, self._koperlagen)
                alle.itemById(INVOER_ANDERE_JOBMAP).tooltip = (
                    "Nu: " + dialoog.folder + "\nKies een andere map met .cam-bestanden.")
        except Exception:
            instellingen.log("inputChanged mislukt:\n" + traceback.format_exc())


class _Uitvoeren(adsk.core.CommandEventHandler):
    def __init__(self, board, boardnaam):
        super().__init__()
        self._board = board
        self._boardnaam = boardnaam

    def notify(self, args):
        try:
            invoer = args.command.commandInputs
            keuze = invoer.itemById(INVOER_JOB).selectedItem
            huidig = instellingen.laad()
            job = os.path.join(_jobmap(huidig), keuze.name) if keuze else ""
            if not job or not os.path.isfile(job):
                _ui.messageBox("Kies eerst een CAM-job. Er staan geen .cam-bestanden in\n"
                               + _jobmap(huidig), TITEL)
                return
            huidig["laatste_job"] = job
            instellingen.bewaar(huidig)

            # Niet hier exporteren (reentrancy), maar zodra dit commando klaar is.
            _app.fireCustomEvent(GEBEURTENIS_ID, json.dumps({
                "boardnaam": self._boardnaam,
                "job": job,
                "doelmap": _doelmap(huidig, self._boardnaam)}))
        except Exception:
            instellingen.log("Uitvoeren mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Er ging iets mis:\n\n" + traceback.format_exc()
                           + "\n\nDetails staan in " + instellingen.LOG, TITEL)


class _Starten(adsk.core.CustomEventHandler):
    """Draait op de hoofddraad nadat het venster dicht is; hier mag mfgexport wel."""

    def notify(self, args):
        try:
            keuzes = json.loads(args.additionalInfo or "{}")
            board = adsk.electron.Board.cast(_app.activeProduct)
            if board is None:
                _ui.messageBox("Het board is niet meer actief; open het en probeer opnieuw.", TITEL)
                return
            _voer_uit(board, keuzes["boardnaam"], keuzes["job"], keuzes["doelmap"])
        except Exception:
            instellingen.log("Export mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Er ging iets mis:\n\n" + traceback.format_exc()
                           + "\n\nDetails staan in " + instellingen.LOG, TITEL)


# ---------------------------------------------------------------------------
# De export zelf.
# ---------------------------------------------------------------------------

def _voer_uit(board, boardnaam, job, doelmap):
    os.makedirs(doelmap, exist_ok=True)

    # Eerst de stuklijst opbouwen, zodat een vergrendeld bestand (Excel) de
    # gebruiker tegenhoudt voordat er iets aan de map is veranderd.
    onderdelen = _onderdelen(board)
    regels = bom.bouw(onderdelen)
    plaatsingen = _plaatsingen(board)

    # 1. Gerber en drill via de CAM-processor zonder venster, in de werkmap.
    camoutputs, weggelaten = _mfgexport(job)
    if camoutputs is None:
        return

    # 2. Stuklijst en pick-and-place ernaast, in de Assembly-map die de
    #    CAM-processor ook zou vullen.
    assembly = os.path.join(camoutputs, camjob.ASSEMBLY)
    os.makedirs(assembly, exist_ok=True)
    bom_pad = os.path.join(assembly, f"{boardnaam}-BOM.csv")
    bom.schrijf(bom_pad, regels)
    voor = cpl.rijen(plaatsingen, achterkant=False)
    achter = cpl.rijen(plaatsingen, achterkant=True)
    cpl.schrijf(os.path.join(assembly, f"PnP_{boardnaam}_CPL_front.csv"), plaatsingen, achterkant=False)
    cpl.schrijf(os.path.join(assembly, f"PnP_{boardnaam}_CPL_back.csv"), plaatsingen, achterkant=True)

    # 3. Alles in een zip in de uitvoermap, met dezelfde naam en indeling als
    #    Fusion die zou geven. Alleen de zip komt daar; de losse bestanden
    #    blijven in de werkmap tot de volgende export.
    gerbers = len([r for r, _ in camjob.bestanden_in(camoutputs) if not r.startswith(camjob.ASSEMBLY)])
    zip_naam = f"{boardnaam}_{datetime.date.today():%Y-%m-%d}.zip"
    try:
        aantal = camjob.maak_zip(camoutputs, os.path.join(doelmap, zip_naam))
    except PermissionError as ex:
        instellingen.log(f"Zip niet te schrijven: {ex}")
        _ui.messageBox("De zip kon niet worden geschreven; hij staat open in een ander programma:\n\n"
                       + os.path.join(doelmap, zip_naam) + "\n\nSluit hem en klik opnieuw op PCB-uitvoer.",
                       TITEL)
        return

    eigen = sum(1 for o in onderdelen if o.populate and o.is_eigen)
    instellingen.log(f"PCB-uitvoer klaar in {doelmap}: {gerbers} Gerber/drill-bestanden (job {os.path.basename(job)}), "
                     f"BOM {len(regels)} regels ({eigen} eigen weggelaten), CPL {len(voor)} voor / {len(achter)} achter, "
                     f"zip {zip_naam} ({aantal} bestanden)")

    samenvatting = [
        f"Gerber en drill: {gerbers} bestanden, met job {os.path.basename(job)}.",
        f"Stuklijst: {len(regels)} regels; {eigen} eigen onderdelen (fabrikant {bom.EIGEN_FABRIKANT}) weggelaten.",
        f"Pick-and-place: {len(voor)} onderdelen boven, {len(achter)} onder.",
        f"Zip: {zip_naam} ({aantal} bestanden).",
    ]
    if weggelaten:
        samenvatting.append("Niet gemaakt (kan niet zonder het CAM-venster): " + ", ".join(sorted(set(weggelaten))) + ".")

    antwoord = _ui.messageBox(
        "PCB-uitvoer klaar:\n" + doelmap + "\n\n" + "\n".join(samenvatting) + "\n\nMap openen?",
        TITEL,
        adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        adsk.core.MessageBoxIconTypes.InformationIconType)
    if antwoord == adsk.core.DialogResults.DialogYes:
        os.startfile(doelmap)


def _mfgexport(job):
    """Draait de CAM-processor zonder venster op een afgeslankte kopie van de job.

    Geeft (pad van CAMOutputs, weggelaten output_types) terug, of (None, ...)
    na een melding aan de gebruiker.
    """
    werkmap = os.path.join(os.path.dirname(instellingen.LOG), "cam-werk")
    shutil.rmtree(werkmap, ignore_errors=True)
    job_kopie = os.path.join(werkmap, "job", os.path.basename(job))
    weggelaten = camjob.slank(job, job_kopie)
    uitmap = os.path.join(werkmap, "uit")
    os.makedirs(uitmap)

    commando = f"Electron.mfgexport {_argument(uitmap)} {_argument(job_kopie)}"
    try:
        antwoord = _app.executeTextCommand(commando)
    except Exception as ex:
        antwoord = f"{type(ex).__name__}: {ex}"
    instellingen.log(f"{commando} -> {antwoord!r}")

    # Het commando geeft meteen antwoord; de bestanden volgen er vlak achteraan.
    # Wachten tot de map er is en niet meer groeit, en Fusion intussen zijn
    # gang laten gaan (doEvents), anders wacht het misschien op zichzelf.
    camoutputs = None
    vorige = None
    einde = time.time() + MFGEXPORT_WACHTTIJD_SECONDEN
    while time.time() < einde:
        adsk.doEvents()
        time.sleep(MFGEXPORT_PEIL_SECONDEN)
        camoutputs = camjob.zoek_camoutputs(werkmap)
        if camoutputs is None:
            continue
        stand = camjob.bestanden_in(camoutputs)
        if stand and stand == vorige:
            break
        vorige = stand

    if camoutputs is None or not camjob.bestanden_in(camoutputs):
        _ui.messageBox(
            "De CAM-processor heeft geen Gerber-bestanden opgeleverd.\n\n"
            f"Job: {job}\nAntwoord van Fusion: {antwoord}\n\n"
            "Details staan in " + instellingen.LOG, TITEL)
        return None, weggelaten
    return camoutputs, weggelaten


def _argument(pad):
    """Een pad als argument voor het tekstcommando; alleen quoten als het moet."""
    return f'"{pad}"' if " " in pad else pad


def _koperlagen(board):
    """Aantal gebruikte koperlagen; in EAGLE zijn dat de lagen 1 tot en met 16."""
    try:
        lagen = board.layers
        return sum(1 for i in range(lagen.count)
                   if 1 <= lagen.item(i).number <= 16 and lagen.item(i).used)
    except Exception:
        return 0


def _onderdelen(board):
    resultaat = []
    elementen = board.elements
    for i in range(elementen.count):
        el = elementen.item(i)

        attributen = {}
        try:
            for j in range(el.attributes.count):
                a = el.attributes.item(j)
                attributen[a.name] = a.value
        except Exception:
            instellingen.log(f"Attributen van {el.name} niet leesbaar:\n" + traceback.format_exc())

        resultaat.append(bom.Onderdeel(
            naam=el.name,
            waarde=el.value or "",
            footprint=_footprint(el),
            populate=bool(el.populate),
            attributen=attributen))
    return resultaat


def _plaatsingen(board):
    resultaat = []
    elementen = board.elements
    for i in range(elementen.count):
        el = elementen.item(i)
        resultaat.append(cpl.Plaatsing(
            naam=el.name,
            x=el.x,
            y=el.y,
            hoek=float(el.angle),
            achterkant=bool(el.mirror),
            waarde=el.value or "",
            footprint=_footprint(el),
            populate=bool(el.populate)))
    return resultaat


def _footprint(el):
    try:
        return el.package.name or ""
    except Exception:
        return ""


def _jobmap(huidig):
    return huidig.get("jobmap") or STANDAARD_JOBMAP


def _doelmap(huidig, boardnaam):
    """De map waar de zip komt: de uitvoermap zelf, standaard Downloads zoals bij Fusion."""
    return os.path.normpath(huidig.get("uitvoermap") or os.path.join(os.path.expanduser("~"), "Downloads"))


def _bestandsnaam(naam):
    return re.sub(r'[<>:"/\\|?*]+', "", naam or "").strip()
