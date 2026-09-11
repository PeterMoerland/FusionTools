"""Stuklijst opbouwen en als correcte CSV wegschrijven.

Dit deel kent Fusion niet; het werkt op gewone Python-waarden en is daardoor
buiten Fusion te testen. De reden dat dit bestaat: de BOM uit de CAM-processor
zet velden niet tussen aanhalingstekens, zodat een komma in een omschrijving
een kolomgrens wordt en de regel verschuift. De csv-module doet dat wel goed.
"""

import csv
import re
from dataclasses import dataclass, field

# Attributen die een eigen kolom krijgen, in deze volgorde. Wat er verder op een
# element staat, gaat niet mee: de BOM is een algemeen tussenformaat dat later per
# leverancier wordt omgezet, en daar heb je aan prijzen en categorieen niets.
KOLOM_ATTRIBUTEN = (
    "MPN",
    "MANUFACTURER",
    "DESCRIPTION",
    "PACKAGE_SIZE",
)

KOPREGEL = ("QTY", "Reference Designator", "Value", "Footprint") + KOLOM_ATTRIBUTEN

# Elementen van deze fabrikant zijn geen in te kopen onderdelen: montagegaten,
# labels, soldeerpads uit de eigen bibliotheek. Die horen niet op de stuklijst.
EIGEN_FABRIKANT = "MDE"


@dataclass
class Onderdeel:
    """Een element op het board, zoals de API het aanlevert."""

    naam: str
    waarde: str
    footprint: str
    populate: bool = True
    attributen: dict = field(default_factory=dict)

    def attribuut(self, sleutel):
        return (self.attributen.get(sleutel) or "").strip()

    @property
    def is_eigen(self):
        return self.attribuut("MANUFACTURER").upper() == EIGEN_FABRIKANT


@dataclass
class Regel:
    referenties: list
    waarde: str
    footprint: str
    attributen: dict

    @property
    def aantal(self):
        return len(self.referenties)


def bouw(onderdelen):
    """Groepeert de onderdelen tot stuklijstregels.

    Gelijk zijn: dezelfde waarde, dezelfde footprint en hetzelfde MPN. Twee
    weerstanden van 10k in 0402 met een verschillend MPN blijven dus twee regels,
    want dat zijn voor de inkoop twee artikelen.
    """
    groepen = {}

    for o in onderdelen:
        if not o.populate or o.is_eigen:
            continue

        sleutel = (o.waarde.strip(), o.footprint.strip(), o.attribuut("MPN"))
        regel = groepen.get(sleutel)
        if regel is None:
            regel = Regel(
                referenties=[],
                waarde=o.waarde.strip(),
                footprint=o.footprint.strip(),
                attributen={k: o.attribuut(k) for k in KOLOM_ATTRIBUTEN},
            )
            groepen[sleutel] = regel
        else:
            # Een attribuut dat op het ene element leeg is en op het andere niet:
            # de gevulde wint, zodat een half ingevulde bibliotheek geen kolom leegt.
            for k in KOLOM_ATTRIBUTEN:
                if not regel.attributen[k] and o.attribuut(k):
                    regel.attributen[k] = o.attribuut(k)

        regel.referenties.append(o.naam)

    regels = list(groepen.values())
    for regel in regels:
        regel.referenties.sort(key=natuurlijk)

    # Op de eerste referentie sorteren geeft de volgorde die je op het board ook
    # aanhoudt: C's, dan D's, dan J's, en binnen een letter op nummer.
    regels.sort(key=lambda r: natuurlijk(r.referenties[0]))
    return regels


def natuurlijk(tekst):
    """Sorteersleutel waarbij R2 voor R10 komt."""
    return [int(deel) if deel.isdigit() else deel.upper() for deel in re.split(r"(\d+)", tekst)]


def schrijf(pad, regels):
    """Schrijft de regels als CSV volgens RFC 4180, elk veld tussen aanhalingstekens.

    Alles quoten, ook wat het niet nodig heeft, zodat een importeur die op de
    aanhalingstekens let getallen als tekst neemt: een MPN als 885012109004 mag
    geen 8,85E+11 worden en een behuizing 0402 geen 402. Aanhalingstekens in een
    veld worden verdubbeld. De byte order mark aan het begin zorgt dat Excel het
    bestand als UTF-8 leest, zodat een micro- of graadteken niet verminkt raakt.
    """
    with open(pad, "w", newline="", encoding="utf-8-sig") as bestand:
        schrijver = csv.writer(bestand, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        schrijver.writerow(KOPREGEL)
        for r in regels:
            schrijver.writerow(
                [r.aantal, ", ".join(r.referenties), r.waarde, r.footprint]
                + [r.attributen[k] for k in KOLOM_ATTRIBUTEN]
            )
