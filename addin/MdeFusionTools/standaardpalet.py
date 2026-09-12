"""De knop Standaardcomponenten: R en C van het board vergelijken met de
standaardcomponenten van Eurocircuits en het attribuut GPN bijwerken.

Een palet (resources/standaard.html) toont per weerstand en condensator de
huidige MPN en GPN en het voorgestelde GPN; aangevinkte regels worden met een
EAGLE-script (ATTRIBUTE <naam> GPN '<gpn>') bijgewerkt, want de API laat
attributen alleen lezen. Zie standaard.py voor het vergelijken zelf en
componenten.py voor het ophalen van de tabel.
"""

import json
import os
import traceback

import adsk.core
import adsk.electron

from . import componenten
from . import instellingen
from . import standaard

COMMANDO_ID = "MDE_Standaardcomponenten"
PALET_ID = "MDE_StandaardPalet"
GEBEURTENIS_ID = "MDE_StandaardToepassen"
TITEL = "MDE Standaardcomponenten"

_app = None
_ui = None
_handlers = None
_lees_onderdelen = None   # functie(board) -> onderdelen met naam, waarde, footprint, populate, attributen
_board = None


def start(app, ui, handlers, lees_onderdelen):
    """Maakt de knopdefinitie en de gebeurtenis; geeft de definitie terug om te plaatsen."""
    global _app, _ui, _handlers, _lees_onderdelen
    _app, _ui, _handlers, _lees_onderdelen = app, ui, handlers, lees_onderdelen

    iconen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "standaard")
    definitie = _ui.commandDefinitions.itemById(COMMANDO_ID)
    if definitie is None:
        definitie = _ui.commandDefinitions.addButtonDefinition(
            COMMANDO_ID,
            "Standaardcomponenten",
            "Controleert alle weerstanden en condensatoren tegen de standaardcomponenten van "
            "Eurocircuits en zet het GPN in het attribuut GPN. MPN blijft ongewijzigd.",
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
    toepassen = _Toepassen()
    gebeurtenis.add(toepassen)
    _handlers.append(toepassen)
    return definitie


def stop():
    _sluit_palet()
    definitie = _ui.commandDefinitions.itemById(COMMANDO_ID) if _ui else None
    if definitie:
        definitie.deleteMe()
    try:
        _app.unregisterCustomEvent(GEBEURTENIS_ID)
    except Exception:
        pass


class _Aangemaakt(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            uitvoeren = _Uitvoeren()
            args.command.execute.add(uitvoeren)
            _handlers.append(uitvoeren)
            args.command.isAutoExecute = True
        except Exception:
            instellingen.log("commandCreated (standaard) mislukt:\n" + traceback.format_exc())


class _Uitvoeren(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            _toon_palet()
        except Exception:
            instellingen.log("Palet standaardcomponenten tonen mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Het venster kon niet worden geopend:\n\n" + traceback.format_exc(), TITEL)


def _actief_ontwerp():
    """Het open board of schema, of None. In beide staan de R en C met hun attributen.

    Eerst het producttype bekijken en dan pas casten: een Schematic naar Board
    casten (of omgekeerd) is niet veilig gebleken.
    """
    product = _app.activeProduct
    if product is None:
        return None
    try:
        producttype = product.productType or ""
    except Exception:
        producttype = ""
    instellingen.log(f"Standaardcomponenten: actief product {producttype!r}")

    laag = producttype.lower()
    if "sch" in laag:
        return adsk.electron.Schematic.cast(product)
    if "board" in laag or "pcb" in laag:
        return adsk.electron.Board.cast(product)
    return None


def _is_schema(ontwerp):
    try:
        return "sch" in (ontwerp.productType or "").lower()
    except Exception:
        return False


def _toon_palet():
    global _board
    ontwerp = _actief_ontwerp()
    if ontwerp is None:
        _ui.messageBox("Open eerst een board of schema.", TITEL)
        return
    _board = ontwerp

    palet = _ui.palettes.itemById(PALET_ID)
    if palet is None:
        html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "standaard.html")
        palet = _ui.palettes.add(PALET_ID, TITEL, html.replace("\\", "/"), False, True, True, 900, 520)
        palet.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        van_html = _VanHtml()
        palet.incomingFromHTML.add(van_html)
        _handlers.append(van_html)
    else:
        _stuur_stand(palet)
    palet.isVisible = True


def _sluit_palet():
    palet = _ui.palettes.itemById(PALET_ID) if _ui else None
    if palet is not None:
        try:
            palet.deleteMe()
        except Exception:
            instellingen.log("Palet standaardcomponenten sluiten mislukt:\n" + traceback.format_exc())


def _onderdelen():
    if _is_schema(_board):
        return _onderdelen_schema(_board)

    resultaat = []
    for o in _lees_onderdelen(_board):
        resultaat.append(standaard.Onderdeel(
            naam=o.naam,
            waarde=o.waarde,
            footprint=o.footprint,
            mpn=o.attributen.get("MPN", "") or "",
            gpn=o.attributen.get("GPN", "") or "",
            package_size=o.attributen.get("PACKAGE_SIZE", "") or "",
            populate=o.populate))
    return resultaat


def _onderdelen_schema(schema):
    """De parts van het schema, met dezelfde attributen als op het board (MPN,
    GPN, PACKAGE_SIZE).

    De footprint wordt hier niet gelezen: daarvoor zou part.device.package nodig
    zijn, en dat is de meest waarschijnlijke oorzaak van een crash van Fusion bij
    de eerste poging. De soort volgt uit de naam (R.., C..) en de maat uit
    PACKAGE_SIZE; alleen een part zonder dat attribuut valt daardoor onder
    "maat niet te bepalen". Elke stap wordt gelogd om een crash te kunnen plaatsen.
    """
    resultaat = []
    parts = schema.parts
    aantal = parts.count
    instellingen.log(f"Schema: {aantal} parts lezen.")
    for i in range(aantal):
        part = parts.item(i)
        naam = ""
        try:
            naam = part.name or ""
            waarde = part.value or ""
        except Exception:
            instellingen.log(f"Part {i} niet leesbaar:\n" + traceback.format_exc())
            continue

        attributen = {}
        try:
            lijst = part.attributes
            for j in range(lijst.count):
                a = lijst.item(j)
                attributen[a.name] = a.value
        except Exception:
            instellingen.log(f"Attributen van {naam} niet leesbaar:\n" + traceback.format_exc())

        resultaat.append(standaard.Onderdeel(
            naam=naam,
            waarde=waarde or attributen.get("VALUE", "") or "",
            footprint="",
            mpn=attributen.get("MPN", "") or "",
            gpn=attributen.get("GPN", "") or "",
            package_size=attributen.get("PACKAGE_SIZE", "") or "",
            populate=True))
    instellingen.log(f"Schema: {len(resultaat)} parts gelezen.")
    return resultaat


def _naam_van(ontwerp):
    try:
        return ontwerp.name if ontwerp is not None else ""
    except Exception:
        return ""


def _stand(melding="", fout=False):
    """Alles wat de pagina toont, als dict. Een fout bij het ophalen wordt een melding."""
    huidig = instellingen.laad()
    stand = {
        "board": _naam_van(_board),
        "uitkomsten": [],
        "aantal_componenten": 0,
        "melding": melding,
        "fout": fout,
    }
    try:
        tabel = componenten.haal(
            huidig.get("componenten_url"),
            huidig.get("componenten_sleutel", ""),
            huidig.get("componenten_certificaat") or None)
    except componenten.ComponentenFout as ex:
        stand["melding"] = str(ex) + " Klik op Sleutel… om de sleutel in te voeren." \
            if "sleutel" in str(ex).lower() else str(ex)
        stand["fout"] = True
        instellingen.log(f"Standaardcomponenten niet opgehaald: {ex}")
        return stand

    uitkomsten = standaard.controleer(_onderdelen(), tabel)
    stand["aantal_componenten"] = len(tabel)
    stand["uitkomsten"] = [{
        "naam": u.naam,
        "soort": u.soort,
        "waarde": u.waarde,
        "grootte": u.grootte,
        "mpn": u.mpn,
        "gpn": u.gpn,
        "status": u.status,
        "toelichting": u.toelichting,
        "kandidaten": [{"gpn": k.gpn, "omschrijving": k.omschrijving or k.waarde_tekst,
                        "opmerkingen": k.opmerkingen} for k in u.kandidaten],
    } for u in uitkomsten]
    instellingen.log(f"Standaardcomponenten gecontroleerd: {len(uitkomsten)} R/C, "
                     f"{sum(1 for u in uitkomsten if u.status == 'voorstel')} voorstellen, "
                     f"{sum(1 for u in uitkomsten if u.status == 'standaard')} al standaard.")
    return stand


def _stuur_stand(palet, melding="", fout=False):
    palet.sendInfoToHTML("stand", json.dumps(_stand(melding, fout)))


class _VanHtml(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            actie = args.action
            gegevens = json.loads(args.data or "{}")
            palet = _ui.palettes.itemById(PALET_ID)

            if actie == "klaar":
                if _board is not None:
                    _stuur_stand(palet)

            elif actie == "vernieuwen":
                componenten.vergeet()
                _stuur_stand(palet)

            elif actie == "sleutel":
                huidig = instellingen.laad()
                tekst, geannuleerd = _ui.inputBox(
                    "De gedeelde sleutel voor api/componenten van de MDE-app (X-Sleutel):",
                    TITEL, huidig.get("componenten_sleutel", ""))
                if not geannuleerd:
                    huidig["componenten_sleutel"] = tekst.strip()
                    instellingen.bewaar(huidig)
                    componenten.vergeet()
                    _stuur_stand(palet)

            elif actie == "toepassen":
                # Niet hier: een EAGLE-script draaien vanuit het HTML-bericht gaat
                # via de gebeurtenis, net als de export.
                _app.fireCustomEvent(GEBEURTENIS_ID, json.dumps({"keuzes": gegevens.get("keuzes", [])}))

            elif actie == "sluiten":
                palet.isVisible = False
                _app.fireCustomEvent(GEBEURTENIS_ID, json.dumps({"alleen_sluiten": True}))

            args.returnData = "OK"
        except Exception:
            instellingen.log("Bericht uit het palet standaardcomponenten mislukt:\n" + traceback.format_exc())
            _ui.messageBox("Er ging iets mis:\n\n" + traceback.format_exc()
                           + "\n\nDetails staan in " + instellingen.LOG, TITEL)


class _Toepassen(adsk.core.CustomEventHandler):
    """Zet de gekozen GPN's in het attribuut GPN met een EAGLE-script en ververst het palet."""

    def notify(self, args):
        try:
            gegevens = json.loads(args.additionalInfo or "{}")
            if gegevens.get("alleen_sluiten"):
                _sluit_palet()
                return

            palet = _ui.palettes.itemById(PALET_ID)
            keuzes = [(k.get("naam", ""), k.get("gpn", "")) for k in gegevens.get("keuzes", [])]
            regels = standaard.script_regels(keuzes)
            if not regels:
                if palet:
                    palet.sendInfoToHTML("melding", "Niets om bij te werken.")
                return

            if _actief_ontwerp() is None:
                if palet:
                    palet.sendInfoToHTML("melding", "Het board of schema is niet meer actief.")
                return

            aantal = sum(1 for naam, gpn in keuzes if naam and gpn)
            antwoord = _voer_script_uit(regels)
            instellingen.log(f"GPN bijgewerkt voor {aantal} onderdelen; antwoord: {antwoord!r}")

            # Opnieuw controleren: wat net een voorstel was, is nu standaard.
            if palet:
                _stuur_stand(palet, f"GPN bijgewerkt voor {aantal} onderdelen. "
                                    "Sla het board op om het te bewaren.")
        except Exception:
            instellingen.log("GPN bijwerken mislukt:\n" + traceback.format_exc())
            _ui.messageBox("GPN bijwerken mislukt:\n\n" + traceback.format_exc()
                           + "\n\nDetails staan in " + instellingen.LOG, TITEL)


def _voer_script_uit(regels):
    """Schrijft de ATTRIBUTE-regels naar een .scr en laat de PCB-editor hem draaien."""
    map_ = os.path.join(os.path.dirname(instellingen.LOG), "scripts")
    os.makedirs(map_, exist_ok=True)
    pad = os.path.join(map_, "gpn.scr")
    with open(pad, "w", encoding="utf-8", newline="\n") as bestand:
        bestand.write("\n".join(regels) + "\n")

    commando = "Electron.runScript " + (f'"{pad}"' if " " in pad else pad)
    antwoord = _app.executeTextCommand(commando)
    instellingen.log(f"{commando} -> {antwoord!r}")
    return antwoord
