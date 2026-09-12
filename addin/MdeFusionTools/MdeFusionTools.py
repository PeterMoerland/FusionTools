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

        palet = _ui.palettes.itemById(PALET_ID)
        if palet:
            palet.deleteMe()

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
#
# Geen commandovenster maar een palet. In de PCB-editor is altijd een
# EAGLE-commando actief dat het onze onderbreekt zodra de muis boven het board
# komt; een commandovenster verdwijnt dan of voert zichzelf uit. Een palet is
# een los venster van Fusion dat daar niets van merkt. De HTML ernaast praat
# met deze code via adsk.fusionSendData / sendInfoToHTML.
# ---------------------------------------------------------------------------

PALET_ID = "MDE_PcbUitvoerPalet"

_palet_board = None   # het board waarvoor het palet openstaat


class _Aangemaakt(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            # Geen invoervelden, dus het commando voert meteen uit en toont het palet.
            uitvoeren = _Uitvoeren()
            args.command.execute.add(uitvoeren)
            _handlers.append(uitvoeren)
            args.command.isAutoExecute = True
        except Exception:
            instellingen.log("commandCreated mislukt:\n" + traceback.format_exc())


class _Uitvoeren(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            _toon_palet()
        except Exception:
            instellingen.log("Palet tonen mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Het venster kon niet worden geopend:\n\n" + traceback.format_exc(), TITEL)


def _toon_palet():
    global _palet_board
    board = adsk.electron.Board.cast(_app.activeProduct)
    if board is None:
        _ui.messageBox("Open eerst het board (niet het schema).", TITEL)
        return
    _palet_board = board

    palet = _maak_palet()
    # Staat de pagina al, dan ververst dit de stand (ander board, andere lagen).
    # Bij een nieuw palet gaat dit bericht verloren; de pagina vraagt de stand
    # dan zelf op zodra Fusion het adsk-object heeft ingespoten.
    _stuur_stand(palet)
    palet.isVisible = True


def _maak_palet():
    """Het palet, aangemaakt bij de eerste klik.

    Niet vooraf bij het starten van de add-in: een palet dat verborgen wordt
    aangemaakt toont Fusion toch, en dan staat er een leeg venster zonder board.
    """
    palet = _ui.palettes.itemById(PALET_ID)
    if palet is not None:
        return palet

    # De ingebouwde browser wil schuine strepen; met backslashes geeft hij
    # ERR_INVALID_URL.
    html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "pcbuitvoer.html")
    html = html.replace("\\", "/")
    palet = _ui.palettes.add(PALET_ID, TITEL, html, False, True, True, 420, 300)
    palet.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
    van_html = _VanHtml()
    palet.incomingFromHTML.add(van_html)
    _handlers.append(van_html)
    return palet


def _sluit_palet():
    """Het palet weggooien, niet verbergen.

    Een verborgen palet haalt Fusion na een commando (zoals mfgexport) weer
    tevoorschijn, en dan nog leeg ook. Weggooien is afdoende; de volgende klik
    maakt het opnieuw aan.
    """
    palet = _ui.palettes.itemById(PALET_ID)
    if palet is not None:
        try:
            palet.deleteMe()
        except Exception:
            instellingen.log("Palet sluiten mislukt:\n" + traceback.format_exc())


def _stand():
    huidig = instellingen.laad()
    board = _palet_board
    boardnaam = _bestandsnaam(board.name) or "board"
    lagen = _koperlagen(board)
    jobs = camjob.lijst(_jobmap(huidig))
    gekozen = camjob.standaard(jobs, lagen, huidig.get("laatste_job"))
    return {
        "board": boardnaam,
        "koperlagen": lagen,
        "jobmap": _jobmap(huidig),
        "uitvoermap": _doelmap(huidig, boardnaam),
        "jobs": [{"naam": os.path.basename(job), "pad": job, "gekozen": job == gekozen} for job in jobs],
    }


def _stuur_stand(palet):
    palet.sendInfoToHTML("stand", json.dumps(_stand()))


class _VanHtml(adsk.core.HTMLEventHandler):
    """Berichten uit de pagina: klaar, andere map, exporteren, annuleren."""

    def notify(self, args):
        try:
            actie = args.action
            gegevens = json.loads(args.data or "{}")
            palet = _ui.palettes.itemById(PALET_ID)
            huidig = instellingen.laad()

            if actie == "klaar":
                # De pagina meldt zich ook bij het verborgen aanmaken tijdens het
                # starten; dan is er nog geen board en niets te tonen.
                if _palet_board is not None:
                    _stuur_stand(palet)

            elif actie in ("andere_uitvoermap", "andere_jobmap"):
                dialoog = _ui.createFolderDialog()
                if actie == "andere_uitvoermap":
                    dialoog.title = "Kies de map waar de zip met de PCB-uitvoer komt"
                    dialoog.initialDirectory = _doelmap(huidig, "")
                else:
                    dialoog.title = "Kies de map met .cam-jobs van de CAM-processor"
                    dialoog.initialDirectory = _jobmap(huidig)
                if dialoog.showDialog() == adsk.core.DialogResults.DialogOK:
                    huidig["uitvoermap" if actie == "andere_uitvoermap" else "jobmap"] = dialoog.folder
                    instellingen.bewaar(huidig)
                _stuur_stand(palet)

            elif actie == "exporteren":
                job = gegevens.get("job", "")
                if not job or not os.path.isfile(job):
                    palet.sendInfoToHTML("melding", "Kies eerst een CAM-job.")
                    return
                huidig["laatste_job"] = job
                instellingen.bewaar(huidig)
                palet.isVisible = False
                boardnaam = _bestandsnaam(_palet_board.name) or "board"
                # Niet hier exporteren maar via de gebeurtenis: dan staat het
                # palet al dicht en loopt er geen ander commando meer.
                _app.fireCustomEvent(GEBEURTENIS_ID, json.dumps({
                    "boardnaam": boardnaam,
                    "job": job,
                    "doelmap": _doelmap(huidig, boardnaam)}))

            elif actie == "annuleren":
                palet.isVisible = False
                _app.fireCustomEvent(GEBEURTENIS_ID, json.dumps({"alleen_sluiten": True}))

            args.returnData = "OK"
        except Exception:
            instellingen.log("Bericht uit het palet mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Er ging iets mis:\n\n" + traceback.format_exc()
                           + "\n\nDetails staan in " + instellingen.LOG, TITEL)


class _Starten(adsk.core.CustomEventHandler):
    """Draait op de hoofddraad nadat het palet dicht is; hier mag mfgexport."""

    def notify(self, args):
        try:
            # Hier sluiten, niet in de HTML-gebeurtenis: daar negeert Fusion het,
            # en een palet dat zichzelf vanuit zijn eigen bericht weggooit is vragen
            # om problemen.
            _sluit_palet()
            keuzes = json.loads(args.additionalInfo or "{}")
            if keuzes.get("alleen_sluiten"):
                return
            board = adsk.electron.Board.cast(_app.activeProduct)
            if board is None:
                _ui.messageBox("Het board is niet meer actief; open het en probeer opnieuw.", TITEL)
                return
            _voer_uit(board, keuzes["boardnaam"], keuzes["job"], keuzes["doelmap"])
        except Exception:
            instellingen.log("Export mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Er ging iets mis:\n\n" + traceback.format_exc()
                           + "\n\nDetails staan in " + instellingen.LOG, TITEL)
        finally:
            # Voor het geval Fusion het na het CAM-commando toch weer toonde.
            _sluit_palet()


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


# Namen van koperlagen zoals Fusion en EAGLE ze geven. Fusion nummert niet meer
# als EAGLE (1..16): een 8-laags board heeft 1:Top, 2:Layer2, 3:Layer3,
# 4:Layer4, 301:Layer5, 302:Layer6, 303:Layer7, 304:Bottom. EAGLE-boards hebben
# Route2..Route15. Daarom telt de naam mee en niet alleen het nummer.
KOPERLAAG_NAAM = re.compile(r"^(top|bottom|layer\s?\d+|route\s?\d+|inner\s?\d*|signal\s?\d*|l\d+)$",
                            re.IGNORECASE)


def _koperlagen(board):
    """Aantal gebruikte koperlagen: laag 1..16 uit de EAGLE-reeks, of een laag met een kopernaam."""
    try:
        lagen = board.layers
        koper = []
        gebruikt = []
        for i in range(lagen.count):
            laag = lagen.item(i)
            if not laag.used:
                continue
            naam = laag.name or ""
            gebruikt.append(f"{laag.number}:{naam}")
            if 1 <= laag.number <= 16 or KOPERLAAG_NAAM.match(naam.strip()):
                koper.append(f"{laag.number}:{naam}")
        instellingen.log(f"Koperlagen ({len(koper)}): {', '.join(koper)} | gebruikte lagen: {', '.join(gebruikt)}")
        return len(koper)
    except Exception:
        instellingen.log("Koperlagen tellen mislukt:\n" + traceback.format_exc())
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
