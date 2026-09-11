"""MDE FusionTools: PCB-uitvoer in een handeling.

Een knop in de PCB-werkruimte die de stuklijst van het open board als correcte
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
_werkruimte_ids = []


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
        for ws_id in _werkruimte_ids:
            try:
                werkruimte = _ui.workspaces.itemById(ws_id)
                paneel = werkruimte.toolbarPanels.itemById(PANEEL_ID) if werkruimte else None
                if paneel:
                    knop = paneel.controls.itemById(COMMANDO_ID)
                    if knop:
                        knop.deleteMe()
                    if paneel.controls.count == 0:
                        paneel.deleteMe()
            except Exception:
                pass

        try:
            qat = _ui.toolbars.itemById("QAT")
            knop = qat.controls.itemById(COMMANDO_ID) if qat else None
            if knop:
                knop.deleteMe()
        except Exception:
            pass

        definitie = _ui.commandDefinitions.itemById(COMMANDO_ID)
        if definitie:
            definitie.deleteMe()

        _handlers.clear()
        _werkruimte_ids.clear()
        instellingen.log("Add-in gestopt.")
    except Exception:
        instellingen.log("Stoppen mislukt:\n" + traceback.format_exc())


def _plaats_knop(definitie):
    """Zet de knop waar hij bij het board te zien is.

    Eerst in de werkbalk van de werkruimte van het board. De Electronics-editor
    is de oude EAGLE-omgeving in Fusion, en niet elke werkruimte daarvan laat
    zijn werkbalk via de API aanpassen: itemById geeft dan een
    InternalValidationError. Lukt het nergens, dan komt de knop op de Quick
    Access Toolbar bovenin, die in elke omgeving zichtbaar is.
    """
    gelukt = []
    for werkruimte in _werkruimtes_voor_board():
        try:
            paneel = werkruimte.toolbarPanels.itemById(PANEEL_ID)
            if paneel is None:
                paneel = werkruimte.toolbarPanels.add(PANEEL_ID, "MDE")
            if paneel.controls.itemById(COMMANDO_ID) is None:
                knop = paneel.controls.addCommand(definitie)
                knop.isPromoted = True
                knop.isPromotedByDefault = True
            _werkruimte_ids.append(werkruimte.id)
            gelukt.append(f"{werkruimte.id} ({werkruimte.name})")
        except Exception as ex:
            instellingen.log(f"Werkbalk van {werkruimte.id} ({werkruimte.name}) niet aanpasbaar: "
                             f"{type(ex).__name__}: {ex}")

    if gelukt:
        instellingen.log("Knop in werkruimte(s): " + ", ".join(gelukt))
        return

    qat = _ui.toolbars.itemById("QAT")
    if qat is None:
        instellingen.log("Geen werkruimte en geen QAT beschikbaar; de knop is nergens geplaatst.")
        return

    if qat.controls.itemById(COMMANDO_ID) is None:
        qat.controls.addCommand(definitie)
    instellingen.log("Knop op de Quick Access Toolbar geplaatst.")


def _werkruimtes_voor_board():
    try:
        lijst = _ui.workspacesByProductType("BoardProductType")
        return [lijst.item(i) for i in range(lijst.count)]
    except Exception:
        instellingen.log("workspacesByProductType mislukt:\n" + traceback.format_exc())
        return []


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
    bom.schrijf(bom_pad, regels)

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
