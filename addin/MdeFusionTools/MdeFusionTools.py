"""MDE FusionTools: PCB-uitvoer in een handeling.

Een knop op de werkbalk van de PCB-editor die de stuklijst van het open board als correcte
CSV wegschrijft en daarna de CAM-export van Fusion opent voor Gerber, drill en
pick-and-place. De CAM-processor deed dat laatste al goed; alleen de BOM eruit
was onbruikbaar door ontbrekende aanhalingstekens.
"""

import json
import os
import re
import threading
import time
import traceback

import adsk.core
import adsk.electron

from . import bom
from . import campakket
from . import instellingen

COMMANDO_ID = "MDE_PcbUitvoer"
PANEEL_ID = "MDE_Paneel"
TITEL = "MDE PCB-uitvoer"

# De zip van de CAM-export verschijnt pas nadat de gebruiker op Process heeft
# gedrukt, dus na onze code. Een achtergronddraad wacht erop en meldt zich via
# deze gebeurtenis weer op de hoofddraad; alleen daar mag de UI aangeraakt worden.
GEBEURTENIS_ID = "MDE_ZipVervangen"
WACHTTIJD_SECONDEN = 15 * 60
PEILINTERVAL_SECONDEN = 2

_app = None
_ui = None

# Handlers moeten in leven blijven: laat je ze los, dan ruimt Python ze op en doet
# de knop niets meer.
_handlers = []
_gebeurtenis = None
_wachter = None


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

        global _gebeurtenis
        _gebeurtenis = _app.registerCustomEvent(GEBEURTENIS_ID)
        klaar = _ZipKlaar()
        _gebeurtenis.add(klaar)
        _handlers.append(klaar)

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

        _stop_wachter()
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
            "De stuklijst kon niet worden geschreven omdat het bestand open staat in een "
            "ander programma, waarschijnlijk Excel:\n\n" + bom_pad + "\n\n"
            "Sluit het daar en klik opnieuw op PCB-uitvoer.",
            TITEL)
        return

    eigen = sum(1 for o in onderdelen if o.populate and o.is_eigen)
    instellingen.log(f"BOM geschreven: {bom_pad} ({len(regels)} regels uit {len(onderdelen)} elementen, "
                     f"{eigen} eigen onderdelen weggelaten)")

    # De map die het CAM-venster als uitvoer moet krijgen, staat op het klembord:
    # de add-in kan die niet in het venster zetten, maar plakken is een handeling.
    # Zo komt Fusions CAMOutputs-map naast de stuklijst terecht.
    klembord = _naar_klembord(doelmap)

    # Welke CAM-job past bij dit board, zodat de gebruiker niet hoeft te tellen.
    lagen = _koperlagen(board)

    # De CAM-export van Fusion zelf voor Gerber, drill en pick-and-place. Die
    # onthoudt de laatst gebruikte job; de gebruiker hoeft alleen op Process te
    # drukken en de map te kiezen.
    cam_gestart = _start_cam()

    # Zodra de zip van de CAM-export in de boardmap verschijnt, gaat onze
    # stuklijst erin, in plaats van de kapotte die Fusion erin zet.
    _start_wachter(doelmap, bom_pad)

    stappen = []
    if cam_gestart:
        stappen.append("De CAM-export staat open.")
    else:
        stappen.append("De CAM-export kon niet automatisch geopend worden; start hem via Manufacturing.")
    if lagen:
        stappen.append(f"Dit board heeft {lagen} koperlagen; gebruik de job MDE_{lagen}_layer.cam.")
    stappen.append(f"Kies als uitvoermap:\n{doelmap}"
                   + ("\n(staat op het klembord, dus plakken volstaat)" if klembord else ""))
    stappen.append("Zodra de zip daar verschijnt, wordt de stuklijst erin vervangen door deze. "
                   "Je krijgt daar een melding van.")

    _ui.messageBox(
        f"Stuklijst geschreven:\n{bom_pad}\n\n"
        f"{len(regels)} regels; {eigen} eigen onderdelen (fabrikant {bom.EIGEN_FABRIKANT}) weggelaten.\n\n"
        + "\n\n".join(stappen),
        TITEL)


def _start_wachter(doelmap, bom_pad):
    """Start een draad die wacht op de zip van de CAM-export en de stuklijst erin vervangt."""
    global _wachter
    _stop_wachter()

    stop_signaal = threading.Event()
    draad = threading.Thread(
        target=_wacht_op_zip,
        args=(doelmap, bom_pad, stop_signaal),
        name="MDE-zipwachter",
        daemon=True)
    _wachter = (draad, stop_signaal)
    draad.start()
    instellingen.log(f"Wacht op CAM-zip in {doelmap} (maximaal {WACHTTIJD_SECONDEN // 60} minuten).")


def _stop_wachter():
    global _wachter
    if _wachter is None:
        return
    draad, stop_signaal = _wachter
    stop_signaal.set()
    draad.join(timeout=PEILINTERVAL_SECONDEN + 1)
    _wachter = None


def _wacht_op_zip(doelmap, bom_pad, stop_signaal):
    """Draait op de achtergrond. Raakt de UI niet aan; meldt zich via de gebeurtenis.

    Alleen zips die na de start verschijnen tellen; wat er al lag blijft met rust.
    Een zip is af als hij niet meer groeit en als zip te openen is; Fusion schrijft
    hem in stappen.
    """
    start = time.time()
    try:
        bestaand = set(_zips_in(doelmap))
    except OSError:
        bestaand = set()
    groottes = {}

    while not stop_signaal.is_set() and time.time() - start < WACHTTIJD_SECONDEN:
        try:
            for zip_pad in _zips_in(doelmap):
                if zip_pad in bestaand:
                    continue

                stabiel, grootte = campakket.is_stabiel(zip_pad, groottes.get(zip_pad))
                groottes[zip_pad] = grootte
                if not stabiel:
                    continue

                if campakket.zoek_bom_lid(zip_pad) is None:
                    # Wel een zip, maar geen stuklijst erin; dat is niet de onze.
                    bestaand.add(zip_pad)
                    continue

                with open(bom_pad, "rb") as bestand:
                    lid = campakket.vervang_bom(zip_pad, bestand.read())

                _meld({"status": "vervangen", "zip": zip_pad, "lid": lid})
                return
        except Exception as ex:
            _meld({"status": "fout", "tekst": f"{type(ex).__name__}: {ex}"})
            return

        stop_signaal.wait(PEILINTERVAL_SECONDEN)

    if not stop_signaal.is_set():
        _meld({"status": "verlopen", "map": doelmap})


def _zips_in(map_):
    return [os.path.join(map_, naam) for naam in os.listdir(map_)
            if naam.lower().endswith(".zip") and not naam.startswith(".mde-")]


def _meld(info):
    """Vanuit de achtergronddraad naar de hoofddraad; daar toont _ZipKlaar het."""
    try:
        _app.fireCustomEvent(GEBEURTENIS_ID, json.dumps(info))
    except Exception as ex:
        instellingen.log(f"Gebeurtenis niet afgevuurd: {type(ex).__name__}: {ex} | {info}")


class _ZipKlaar(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            info = json.loads(args.additionalInfo or "{}")
            status = info.get("status")

            if status == "vervangen":
                instellingen.log(f"Stuklijst vervangen in {info['zip']} ({info['lid']}).")
                _ui.messageBox(
                    "De stuklijst in de CAM-zip is vervangen door de correcte:\n\n"
                    + info["zip"] + "\n\n" + info["lid"],
                    TITEL)
            elif status == "verlopen":
                instellingen.log(f"Geen CAM-zip verschenen in {info['map']}; wachten gestopt.")
            else:
                instellingen.log(f"Vervangen in de CAM-zip mislukt: {info.get('tekst')}")
                _ui.messageBox(
                    "De stuklijst kon niet in de CAM-zip gezet worden:\n\n" + str(info.get("tekst"))
                    + "\n\nDe losse stuklijst staat wel in de boardmap.",
                    TITEL)
        except Exception:
            instellingen.log("Afhandelen van de zipgebeurtenis mislukt:\n" + traceback.format_exc())


def _koperlagen(board):
    """Aantal gebruikte koperlagen; in EAGLE zijn dat de lagen 1 tot en met 16."""
    try:
        lagen = board.layers
        return sum(1 for i in range(lagen.count)
                   if 1 <= lagen.item(i).number <= 16 and lagen.item(i).used)
    except Exception:
        return 0


def _naar_klembord(tekst):
    """Zet tekst op het Windows-klembord. Geeft terug of dat gelukt is."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        # Zonder deze typen neemt ctypes een 32-bits int aan voor handles en
        # pointers, en op 64-bits Windows wordt het adres dan afgekapt: een
        # access violation op adres 0.
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

        gegevens = tekst.encode("utf-16-le") + b"\x00\x00"
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(gegevens))
            adres = kernel32.GlobalLock(handle)
            if not adres:
                return False
            ctypes.memmove(adres, gegevens, len(gegevens))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                return False
        finally:
            user32.CloseClipboard()
        return True
    except Exception as ex:
        instellingen.log(f"Klembord niet gezet: {type(ex).__name__}: {ex}")
        return False


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
