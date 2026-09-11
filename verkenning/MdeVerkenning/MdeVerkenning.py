"""Verkenning van de Electronics-API op een open board.

Dit is geen onderdeel van de add-in. Het draait een keer, met een board open,
en schrijft weg wat de API prijsgeeft: de elementen met hun plaatsing en
attributen, de varianten, en welke commando's Fusion zelf heeft voor CAM.
Daarmee valt te beoordelen wat er van BOM, CPL en Gerber via de API kan,
voordat er een scherm op gebouwd wordt.
"""

import os
import traceback

import adsk.core
import adsk.electron

RAPPORT = os.path.join(os.environ.get("LOCALAPPDATA", "."), "MDE", "FusionTools", "verkenning.txt")

# Meer dan dit aan elementen is voor de vraag niet nodig; de volledige lijst komt
# later uit de add-in zelf.
MAX_ELEMENTEN = 400
MAX_ATTRIBUUT_DETAIL = 5


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    regels = []

    try:
        regels.append(f"Fusion {app.version}")
        regels.append(f"Actief document: {app.activeDocument.name if app.activeDocument else '-'}")
        regels.append(f"Actief product: {app.activeProduct.productType if app.activeProduct else '-'}")
        regels.append("")

        board = adsk.electron.Board.cast(app.activeProduct)
        if board is None:
            regels.append("GEEN BOARD: het actieve product is geen Electronics-board. "
                          "Open het board (niet het schema) en draai het script opnieuw.")
        else:
            _board(board, regels)

        _commandos(ui, regels)

    except Exception:
        regels.append("")
        regels.append("FOUT tijdens de verkenning:")
        regels.append(traceback.format_exc())

    os.makedirs(os.path.dirname(RAPPORT), exist_ok=True)
    with open(RAPPORT, "w", encoding="utf-8") as bestand:
        bestand.write("\n".join(regels))

    ui.messageBox(f"Verkenning weggeschreven naar:\n{RAPPORT}", "MDE verkenning")


def _board(board, regels):
    regels.append(f"Board: {board.name}")
    regels.append(f"  headline: {board.headline!r}")
    regels.append(f"  description: {board.description!r}")
    regels.append(f"  units default: {_veilig(lambda: board.unitsManager.defaultLengthUnits)}")
    regels.append(f"  aantal elementen: {board.elements.count}")
    regels.append(f"  aantal lagen: {board.layers.count}")
    regels.append("")

    # Varianten: bepalen welke elementen in een assemblagevariant meegaan.
    regels.append("Varianten (variantDefs):")
    try:
        defs = board.variantDefs
        aantal = defs.count
        for i in range(aantal):
            regels.append(f"  - {defs.item(i).name}")
        if aantal == 0:
            regels.append("  (geen)")
    except Exception as ex:
        regels.append(f"  niet uit te lezen: {ex}")
    regels.append("")

    # Documentattributen op het board zelf.
    regels.append("Board-attributen (documentAttributes):")
    for naam, waarde in _attributen(board.documentAttributes):
        regels.append(f"  {naam} = {waarde!r}")
    regels.append("")

    # Alle attribuutnamen die op elementen voorkomen, met hoe vaak. Hieruit blijkt
    # welke kolommen de BOM kan krijgen (MPN, LCSC, MANUFACTURER, ...).
    telling = {}
    elementen = board.elements
    for i in range(min(elementen.count, MAX_ELEMENTEN)):
        for naam, _ in _attributen(elementen.item(i).attributes):
            telling[naam] = telling.get(naam, 0) + 1

    regels.append("Attribuutnamen op elementen (naam: aantal elementen):")
    for naam in sorted(telling, key=lambda n: (-telling[n], n)):
        regels.append(f"  {naam}: {telling[naam]}")
    regels.append("")

    # De elementen zelf: alles wat CPL en BOM nodig hebben. x en y zijn 'internal
    # units'; welke eenheid dat is blijkt uit vergelijking met een bekende plaatsing.
    regels.append("Elementen (naam | waarde | x | y | hoek | mirror | populate | package | bibliotheek):")
    for i in range(min(elementen.count, MAX_ELEMENTEN)):
        el = elementen.item(i)
        pkg = _veilig(lambda: el.package.name)
        lib = _veilig(lambda: el.package.library)
        regels.append(f"  {el.name} | {el.value} | {el.x} | {el.y} | {el.angle} | {el.mirror} | "
                      f"{el.populate} | {pkg} | {lib}")
    if elementen.count > MAX_ELEMENTEN:
        regels.append(f"  ... en nog {elementen.count - MAX_ELEMENTEN}")
    regels.append("")

    regels.append(f"Alle attributen van de eerste {MAX_ATTRIBUUT_DETAIL} elementen:")
    for i in range(min(elementen.count, MAX_ATTRIBUUT_DETAIL)):
        el = elementen.item(i)
        regels.append(f"  [{el.name}]")
        for naam, waarde in _attributen(el.attributes):
            regels.append(f"    {naam} = {waarde!r}")
        regels.append(f"    package.description = {_veilig(lambda: el.package.description)!r}")
        regels.append(f"    package.headline    = {_veilig(lambda: el.package.headline)!r}")
    regels.append("")


def _commandos(ui, regels):
    """Welke ingebouwde commando's iets met CAM of exporteren te maken hebben.

    De exportManager van de API kan alleen EAGLE-bestanden schrijven, dus als de
    Gerbers vanuit de add-in moeten komen, dan via het ingebouwde CAM-commando.
    Hier staat of dat er is en hoe het heet.
    """
    zoektermen = ("cam", "gerber", "manufactur", "export", "fabricat", "output")
    regels.append("Commando's met cam/gerber/manufactur/export/fabricat/output in id of naam:")
    try:
        defs = ui.commandDefinitions
        gevonden = 0
        for i in range(defs.count):
            d = defs.item(i)
            tekst = f"{d.id} {d.name}".lower()
            if any(t in tekst for t in zoektermen):
                regels.append(f"  {d.id}  |  {d.name}")
                gevonden += 1
        regels.append(f"  ({gevonden} van {defs.count} commando's)")
    except Exception as ex:
        regels.append(f"  niet uit te lezen: {ex}")
    regels.append("")

    regels.append("Werkruimtes:")
    try:
        for i in range(ui.workspaces.count):
            w = ui.workspaces.item(i)
            regels.append(f"  {w.id}  |  {w.name}  |  product {w.productType}")
    except Exception as ex:
        regels.append(f"  niet uit te lezen: {ex}")


def _attributen(verzameling):
    resultaat = []
    try:
        for i in range(verzameling.count):
            a = verzameling.item(i)
            resultaat.append((a.name, a.value))
    except Exception as ex:
        resultaat.append(("(fout)", str(ex)))
    return resultaat


def _veilig(functie):
    try:
        return functie()
    except Exception as ex:
        return f"<{type(ex).__name__}>"
