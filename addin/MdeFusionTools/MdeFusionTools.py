"""MDE FusionTools: PCB-uitvoer in een handeling.

Een knop op de werkbalk van de PCB-editor die de stuklijst van het open board als correcte
CSV wegschrijft en daarna de CAM-export van Fusion opent voor Gerber, drill en
pick-and-place. De CAM-processor deed dat laatste al goed; alleen de BOM eruit
was onbruikbaar door ontbrekende aanhalingstekens.
"""

import os
import re
import traceback

import adsk.core
import adsk.electron

from . import bom
from . import instellingen

COMMANDO_ID = "MDE_PcbUitvoer"
PANEEL_ID = "MDE_Paneel"
TITEL = "MDE PCB-uitvoer"

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
        definitie = _ui.commandDefinitions.itemById(COMMANDO_ID)
        if definitie is None:
            definitie = _ui.commandDefinitions.addButtonDefinition(
                COMMANDO_ID,
                "PCB-uitvoer",
                "Schrijft de stuklijst als correcte CSV en opent de CAM-export "
                "voor Gerber, drill en pick-and-place.")

        aangemaakt = _Aangemaakt()
        definitie.commandCreated.add(aangemaakt)
        _handlers.append(aangemaakt)

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

            if paneel.controls.itemById(COMMANDO_ID) is None:
                knop = paneel.controls.addCommand(definitie)
                knop.isPromoted = True
                knop.isPromotedByDefault = True

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


class _Aangemaakt(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            uitvoeren = _Uitvoeren()
            args.command.execute.add(uitvoeren)
            _handlers.append(uitvoeren)
            # Geen invoervelden, dus geen dialoog: de knop doet meteen zijn werk.
            args.command.isAutoExecute = True
        except Exception:
            instellingen.log("commandCreated mislukt:\n" + traceback.format_exc())


class _Uitvoeren(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            _voer_uit()
        except Exception:
            instellingen.log("Uitvoeren mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Er ging iets mis:\n\n" + traceback.format_exc()
                           + "\n\nDetails staan in " + instellingen.LOG, TITEL)


def _voer_uit():
    board = adsk.electron.Board.cast(_app.activeProduct)
    if board is None:
        _ui.messageBox("Open eerst het board (niet het schema).", TITEL)
        return

    uitvoermap = _uitvoermap()
    if not uitvoermap:
        return

    boardnaam = _bestandsnaam(board.name) or "board"
    doelmap = os.path.join(uitvoermap, boardnaam)
    os.makedirs(doelmap, exist_ok=True)

    onderdelen = _onderdelen(board)
    regels = bom.bouw(onderdelen)

    bom_pad = os.path.join(doelmap, f"{boardnaam}-BOM.csv")
    try:
        bom.schrijf(bom_pad, regels)
    except PermissionError:
        # Windows houdt een bestand vast zolang een ander programma het open heeft,
        # en dat is bij een CSV vrijwel altijd Excel met de vorige versie.
        instellingen.log(f"BOM niet geschreven, bestand vergrendeld: {bom_pad}")
        _ui.messageBox(
            f"De stuklijst kon niet worden geschreven omdat het bestand open staat in een "
            f"ander programma, waarschijnlijk Excel:

{bom_pad}

"
            "Sluit het daar en klik opnieuw op PCB-uitvoer.",
            TITEL)
        return

    eigen = sum(1 for o in onderdelen if o.populate and o.is_eigen)
    instellingen.log(f"BOM geschreven: {bom_pad} ({len(regels)} regels uit {len(onderdelen)} elementen, "
                     f"{eigen} eigen onderdelen weggelaten)")

    # De CAM-export van Fusion zelf voor Gerber, drill en pick-and-place. Die
    # onthoudt de laatst gebruikte job; de gebruiker hoeft alleen op Process te
    # drukken en de map te kiezen.
    cam_gestart = _start_cam()

    _ui.messageBox(
        f"Stuklijst geschreven:\n{bom_pad}\n\n"
        f"{len(regels)} regels; {eigen} eigen onderdelen (fabrikant {bom.EIGEN_FABRIKANT}) weggelaten.\n\n"
        + ("De CAM-export staat open voor Gerber en pick-and-place."
           if cam_gestart else
           "De CAM-export kon niet automatisch geopend worden; start hem via Manufacturing."),
        TITEL)


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

        try:
            footprint = el.package.name
        except Exception:
            footprint = ""

        resultaat.append(bom.Onderdeel(
            naam=el.name,
            waarde=el.value or "",
            footprint=footprint or "",
            populate=bool(el.populate),
            attributen=attributen))
    return resultaat


def _uitvoermap():
    """De map uit de instellingen, of de gebruiker laten kiezen als die er nog niet is."""
    huidig = instellingen.laad()
    map_ = huidig.get("uitvoermap", "")
    if map_ and os.path.isdir(map_):
        return map_

    dialoog = _ui.createFolderDialog()
    dialoog.title = "Kies de map voor de PCB-uitvoer (per board komt er een submap)"
    if dialoog.showDialog() != adsk.core.DialogResults.DialogOK:
        return None

    huidig["uitvoermap"] = dialoog.folder
    instellingen.bewaar(huidig)
    return dialoog.folder


def _start_cam():
    try:
        antwoord = _app.executeTextCommand("Commands.Start Electron::CAMExport")
        instellingen.log(f"CAM-export geopend: {antwoord}")
        return True
    except Exception as ex:
        instellingen.log(f"CAM-export openen mislukt: {ex}")
        return False


def _bestandsnaam(naam):
    return re.sub(r'[<>:"/\\|?*]+', "", naam or "").strip()
