"""Pick-and-place (CPL) in het formaat van Fusions CAM-processor.

Electron.mfgexport levert alleen Gerber en drill; de Assembly-uitvoer blijft
uit. Deze module maakt de pick-and-place daarom zelf, en wel precies zoals de
CAM-processor hem schreef, zodat wat er na de export mee gebeurt niet hoeft te
veranderen: een bestand per zijde, kolommen Name,X,Y,Angle,Value,Package,
millimeters met twee decimalen.
"""

from dataclasses import dataclass

# Interne eenheid van de Electronics-API: 1/320000 mm, de resolutie van EAGLE.
# Bevestigd aan het testboard: C4 op 27188160 / 320000 = 84,963 mm.
EENHEDEN_PER_MM = 320000

KOPREGEL = "Name,X,Y,Angle,Value,Package"


@dataclass
class Plaatsing:
    naam: str
    x: int            # interne eenheden
    y: int
    hoek: float       # graden
    achterkant: bool  # Element.mirror
    waarde: str
    footprint: str
    populate: bool = True


def mm(interne_eenheden):
    return interne_eenheden / EENHEDEN_PER_MM


def rijen(plaatsingen, achterkant):
    """De geplaatste elementen van een zijde, gesorteerd op naam.

    Alles wat in de actieve variant geplaatst is gaat mee, ook eigen onderdelen
    zoals soldeerpads: zo deed de CAM-processor het ook. De volgorde is die van
    Fusion: een gewone tekstsortering (R1, R10, R11, R2), geen natuurlijke.
    """
    gekozen = [p for p in plaatsingen if p.populate and bool(p.achterkant) == achterkant]
    gekozen.sort(key=lambda p: p.naam.upper())
    return gekozen


def schrijf(pad, plaatsingen, achterkant):
    with open(pad, "w", newline="", encoding="utf-8") as bestand:
        bestand.write(KOPREGEL + "\r\n")
        for p in rijen(plaatsingen, achterkant):
            bestand.write(regel(p) + "\r\n")


def regel(p):
    return ",".join([
        _veld(p.naam),
        f"{mm(p.x):.2f}",
        f"{mm(p.y):.2f}",
        f"{p.hoek:.2f}",
        _veld(p.waarde),
        _veld(p.footprint),
    ])


def _veld(tekst):
    """Fusion zet een veld tussen aanhalingstekens zodra er een spatie, komma of
    aanhalingsteken in staat, en verdubbelt aanhalingstekens erin."""
    tekst = tekst or ""
    if any(teken in tekst for teken in ' ,"'):
        return '"' + tekst.replace('"', '""') + '"'
    return tekst
