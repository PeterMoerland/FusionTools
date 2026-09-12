"""Weerstanden en condensatoren vergelijken met de standaardcomponenten van
Eurocircuits, zoals de MDE-app die aanbiedt (api/componenten).

Buiten Fusion te testen. Een standaardcomponent heeft een General Part Number
(GPN); staat dat in het attribuut GPN van een element, dan herkent de latere
BOM-verwerking het als standaardcomponent. Deze module leest de waarde van een
element ("100nF 16V X7R 10%", "4k7 1/4W"), bepaalt de behuizingsmaat en zoekt
de passende standaardcomponenten; de add-in zet daarna het gekozen GPN in het
attribuut GPN. MPN blijft het fabrikantnummer, voor andere leveranciers.
"""

import re
from dataclasses import dataclass, field

# De behuizingsmaat komt uit het attribuut PACKAGE_SIZE (imperiaal, vier
# cijfers) of anders uit de footprintnaam, die de metrische maat draagt:
# RESC1005X40 is 1,0 x 0,5 mm, imperiaal 0402.
METRISCH_NAAR_IMPERIAAL = {
    "0402": "01005",
    "0603": "0201",
    "1005": "0402",
    "1608": "0603",
    "2012": "0805",
    "3216": "1206",
    "3225": "1210",
    "4532": "1812",
    "5025": "2010",
    "6332": "2512",
}

DIELECTRICA = ("X7R", "X5R", "X7S", "X6S", "X8R", "C0G", "NP0", "Y5V", "Z5U")

# Toegestane afwijking bij het vergelijken van waardes: 27.4k tegen 27400 en
# afrondingen in de tabel (1e-07 voor 100 nF).
RELATIEVE_TOLERANTIE = 0.005


@dataclass
class Onderdeel:
    naam: str
    waarde: str
    footprint: str
    mpn: str = ""
    gpn: str = ""
    package_size: str = ""
    populate: bool = True


@dataclass
class Kenmerken:
    """Wat er uit de waardetekst van een element te lezen is."""
    basis: float = None          # ohm of farad
    tolerantie: float = None     # procent
    spanning: float = None       # volt
    dielectricum: str = None
    vermogen: float = None       # watt


@dataclass
class Kandidaat:
    gpn: str
    waarde_tekst: str
    omschrijving: str
    score: int
    opmerkingen: list = field(default_factory=list)


@dataclass
class Uitkomst:
    naam: str
    soort: str            # R, C of ""
    waarde: str
    grootte: str
    mpn: str
    status: str           # standaard | voorstel | geen | onleesbaar | overgeslagen
    kandidaten: list = field(default_factory=list)
    toelichting: str = ""
    gpn: str = ""

    @property
    def voorstel(self):
        return self.kandidaten[0].gpn if self.kandidaten else ""


def soort_van(naam, footprint=""):
    """R of C op grond van de naam (R12, C4); de footprint bevestigt of ontkent."""
    naam = (naam or "").strip().upper()
    fp = (footprint or "").upper()
    if re.match(r"^R\d+$", naam) or fp.startswith("RESC"):
        return "R"
    if re.match(r"^C\d+$", naam) or fp.startswith("CAPC"):
        return "C"
    return ""


def grootte_van(package_size, footprint=""):
    """Imperiale behuizingsmaat als tekst van vier of vijf cijfers, of ""."""
    ps = (package_size or "").strip()
    if re.match(r"^\d{4,5}$", ps):
        return ps
    m = re.match(r"^(?:RESC|CAPC|INDC|LEDC|DIOC)(\d{4})", (footprint or "").upper())
    if m:
        return METRISCH_NAAR_IMPERIAAL.get(m.group(1), "")
    return ""


_VOORVOEGSELS = {
    "": 1.0, "R": 1.0, "E": 1.0,
    "K": 1e3, "M": 1e6, "G": 1e9,
    "m": 1e-3, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
}


def _getal(tekst):
    return float(tekst.replace(",", "."))


def ontleed_waarde(soort, tekst):
    """Leest "100nF 16V X7R 10%" of "4k7 1/4W 1%" en geeft Kenmerken terug.

    De eerste term is de waarde, in de gangbare schrijfwijzen: 10k, 4k7, 2.2R,
    0R, 1M, 100nF, 2n2, 2.2uF, 100 nF (twee termen). De overige termen zijn
    tolerantie (10%), spanning (16V, 6.3v), dielectricum (X7R) en vermogen
    (1/16W, 0.25W). Wat niet te lezen is, blijft None.
    """
    k = Kenmerken()
    termen = (tekst or "").replace("Ω", "R").replace("ohm", "R").replace("Ohm", "R").split()
    if not termen:
        return k

    # "100 nF" en "10 k": eenheid als losse term achter het getal.
    if len(termen) > 1 and re.match(r"^\d+(?:[.,]\d+)?$", termen[0]) and re.match(r"^[pnuµμmkKMGRE]?[FfΩ]?$", termen[1]):
        termen = [termen[0] + termen[1]] + termen[2:]

    k.basis = _waarde_basis(soort, termen[0])

    for term in termen[1:]:
        t = term.strip()
        if re.match(r"^\d+(?:[.,]\d+)?\s*%$", t):
            k.tolerantie = _getal(t.rstrip("%").strip())
        elif re.match(r"^\d+(?:[.,]\d+)?\s*[vV](?:dc|DC)?$", t):
            k.spanning = _getal(re.sub(r"[vV].*$", "", t).strip())
        elif t.upper() in DIELECTRICA:
            k.dielectricum = t.upper().replace("NP0", "C0G")
        elif _watt(t) is not None:
            k.vermogen = _watt(t)
    return k


def _waarde_basis(soort, term):
    """De grondwaarde van de eerste term: ohm voor R, farad voor C. None als onleesbaar."""
    t = term.strip()
    if soort == "C":
        t = re.sub(r"[Ff]$", "", t)
    elif soort == "R":
        t = re.sub(r"[RrΩ]$", "", t) if re.match(r"^\d+(?:[.,]\d+)?[RrΩ]$", t) else t

    # 4k7, 2n2, 1R5: de letter als komma.
    m = re.match(r"^(\d+)([pnuµμmkKMGRrE])(\d+)$", t)
    if m:
        letter = m.group(2)
        if letter in "Rr":
            factor = 1.0
        else:
            factor = _VOORVOEGSELS.get(letter if letter in "pnuµμmf" else letter.upper())
        if factor is None:
            return None
        return float(f"{m.group(1)}.{m.group(3)}") * factor

    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*([pnuµμmkKMGRrE]?)$", t)
    if not m:
        return None
    getal = _getal(m.group(1))
    letter = m.group(2)
    if letter == "":
        factor = 1.0
    elif letter in "Rr":
        factor = 1.0
    elif letter in "pnuµμmf":
        factor = _VOORVOEGSELS[letter]
    else:
        factor = _VOORVOEGSELS[letter.upper()]
    if soort == "R" and letter == "m":
        # Weerstanden in milliohm komen vrijwel niet voor; "10m" bedoelt bijna
        # altijd 10 megaohm niet, maar we lezen het letterlijk en laten de
        # gebruiker het zien.
        factor = 1e-3
    return getal * factor


def _gelijk(a, b):
    if a is None or b is None:
        return False
    if a == 0 or b == 0:
        return a == b
    return abs(a - b) / max(abs(a), abs(b)) <= RELATIEVE_TOLERANTIE


def _volt(tekst):
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)", str(tekst or ""))
    return _getal(m.group(1)) if m else None


def _procent(tekst):
    """Tolerantie in procent; None als er niets staat."""
    m = re.match(r"^\s*[±+/-]*\s*(\d+(?:[.,]\d+)?)\s*%?\s*$", str(tekst or ""))
    return _getal(m.group(1)) if m else None


def _absolute_tolerantie(tekst):
    """Kleine condensatoren hebben een tolerantie in picofarad (±0.25pF) in
    plaats van procenten; die is niet met een percentage te vergelijken."""
    return bool(re.search(r"[pnu]F\s*$", str(tekst or ""), re.IGNORECASE))


def _watt(tekst):
    """Vermogen in watt uit 1/16W, 0.25W, 62.5mW, 100 mW; None als onleesbaar."""
    t = str(tekst or "").strip()
    m = re.match(r"^(\d+)\s*/\s*(\d+)\s*[wW]?$", t)
    if m:
        return float(m.group(1)) / float(m.group(2))
    m = re.match(r"^(\d*[.,]?\d+)\s*(m?)[wW]$", t)
    if m:
        return _getal(m.group(1)) * (1e-3 if m.group(2) else 1.0)
    return None


def _dielectrica(tekst):
    """De dielectrica uit de tabel als verzameling: "C0G, NP0" en "C0G/NP0" zijn beide {C0G}."""
    delen = re.split(r"[,/;\s]+", str(tekst or "").upper())
    return {d.replace("NP0", "C0G") for d in delen if d}


def kandidaten(soort, grootte, kenmerken, componenten):
    """De standaardcomponenten die bij soort, maat en waarde passen, beste eerst.

    De score telt hoeveel van de opgegeven kenmerken kloppen. Een hogere
    spanning of een kleinere tolerantie dan gevraagd is goed; een lagere spanning
    of ruimere tolerantie kost punten en krijgt een opmerking, zodat de gebruiker
    het ziet voordat hij het GPN overneemt.
    """
    resultaat = []
    for c in componenten:
        if str(c.get("soort", "")).upper() != soort:
            continue
        if str(c.get("grootte", "")) != grootte:
            continue
        if not _gelijk(kenmerken.basis, c.get("waardeBasis")):
            continue

        score = 0
        opmerkingen = []

        if kenmerken.spanning is not None:
            v = _volt(c.get("spanning"))
            if v is None:
                opmerkingen.append("spanning onbekend")
            elif v >= kenmerken.spanning:
                score += 2 if v == kenmerken.spanning else 1
            else:
                score -= 2
                opmerkingen.append(f"spanning {c.get('spanning')} lager dan {_kort(kenmerken.spanning)}V")

        if kenmerken.dielectricum is not None:
            d = _dielectrica(c.get("dielectricum"))
            if kenmerken.dielectricum in d:
                score += 2
            elif d:
                score -= 1
                opmerkingen.append(f"dielectricum {c.get('dielectricum')} i.p.v. {kenmerken.dielectricum}")

        if kenmerken.tolerantie is not None and not _absolute_tolerantie(c.get("tolerantie")):
            t = _procent(c.get("tolerantie"))
            if t is None:
                opmerkingen.append("tolerantie onbekend")
            elif t <= kenmerken.tolerantie:
                score += 2 if t == kenmerken.tolerantie else 1
            else:
                score -= 2
                opmerkingen.append(f"tolerantie {_kort(t)}% ruimer dan {_kort(kenmerken.tolerantie)}%")

        if kenmerken.vermogen is not None:
            w = _watt(c.get("vermogen"))
            if w is None:
                opmerkingen.append("vermogen onbekend")
            elif w >= kenmerken.vermogen - 1e-9:
                score += 2 if abs(w - kenmerken.vermogen) < 1e-9 else 1
            else:
                score -= 2
                opmerkingen.append(f"vermogen {c.get('vermogen')} lager dan {_kort(kenmerken.vermogen)}W")

        resultaat.append(Kandidaat(
            gpn=str(c.get("gpn", "")),
            waarde_tekst=str(c.get("waardeTekst", "")),
            omschrijving=str(c.get("omschrijving", "") or ""),
            score=score,
            opmerkingen=opmerkingen))

    resultaat.sort(key=lambda k: (-k.score, k.gpn))
    return resultaat


def _kort(getal):
    return f"{getal:g}"


def controleer(onderdelen, componenten):
    """Alle R en C van het board langs de standaardcomponenten. Geeft Uitkomsten."""
    gpns = {str(c.get("gpn", "")).upper() for c in componenten}
    uitkomsten = []
    for o in onderdelen:
        if not o.populate:
            continue
        soort = soort_van(o.naam, o.footprint)
        if not soort:
            continue

        grootte = grootte_van(o.package_size, o.footprint)
        mpn = (o.mpn or "").strip()
        gpn = (o.gpn or "").strip()
        uitkomst = Uitkomst(naam=o.naam, soort=soort, waarde=o.waarde or "", grootte=grootte,
                            mpn=mpn, status="geen", gpn=gpn)

        if gpn.upper() in gpns:
            uitkomst.status = "standaard"
            uitkomst.toelichting = "GPN is al een standaardcomponent."
            uitkomsten.append(uitkomst)
            continue

        kenmerken = ontleed_waarde(soort, o.waarde)
        if kenmerken.basis is None:
            uitkomst.status = "onleesbaar"
            uitkomst.toelichting = "Waarde niet te lezen."
        elif not grootte:
            uitkomst.status = "onleesbaar"
            uitkomst.toelichting = "Behuizingsmaat niet te bepalen."
        else:
            uitkomst.kandidaten = kandidaten(soort, grootte, kenmerken, componenten)
            if uitkomst.kandidaten:
                uitkomst.status = "voorstel"
                beste = uitkomst.kandidaten[0]
                uitkomst.toelichting = "; ".join(beste.opmerkingen)
            else:
                uitkomst.toelichting = f"Geen standaardcomponent {soort} {grootte} met deze waarde."
        uitkomsten.append(uitkomst)

    uitkomsten.sort(key=lambda u: _natuurlijk(u.naam))
    return uitkomsten


def _natuurlijk(tekst):
    return [int(d) if d.isdigit() else d.upper() for d in re.split(r"(\d+)", tekst)]


def script_regels(toewijzingen):
    """EAGLE-scriptregels die het attribuut GPN zetten: [(naam, gpn), ...].

    Attributen zijn via de API alleen te lezen; schrijven gaat met het
    EAGLE-commando ATTRIBUTE, uitgevoerd als script (Electron.runScript).
    """
    regels = []
    for naam, gpn in toewijzingen:
        if not naam or not gpn:
            continue
        veilig = str(gpn).replace("'", "")
        regels.append(f"ATTRIBUTE {naam} GPN '{veilig}';")
    return regels
