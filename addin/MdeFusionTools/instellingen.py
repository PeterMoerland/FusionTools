"""Instellingen en logboek per gebruiker.

Ze staan buiten de add-in map, zodat een nieuwe versie van de add-in ze niet
overschrijft. Dezelfde plek als bij de Inventor-tools: MDE\\FusionTools.
"""

import datetime
import json
import os

MAP = os.path.join(os.environ.get("APPDATA", "."), "MDE", "FusionTools")
BESTAND = os.path.join(MAP, "instellingen.json")
LOG = os.path.join(os.environ.get("LOCALAPPDATA", "."), "MDE", "FusionTools", "fusiontools.log")


def laad():
    try:
        with open(BESTAND, encoding="utf-8") as bestand:
            return json.load(bestand)
    except (OSError, ValueError):
        return {}


def bewaar(instellingen):
    os.makedirs(MAP, exist_ok=True)
    with open(BESTAND, "w", encoding="utf-8") as bestand:
        json.dump(instellingen, bestand, indent=2, ensure_ascii=False)


def log(bericht):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as bestand:
            bestand.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {bericht}\n")
    except OSError:
        # Een logboek dat niet te schrijven is mag de add-in niet tegenhouden.
        pass


_werkmap = None


def werkmap(sub=""):
    """Een schrijfbare werkmap zonder spaties in het pad, met eventueel een submap.

    De tekstcommando's van Fusion (Electron.mfgexport, Electron.runScript)
    krijgen paden als los argument, en of ze aanhalingstekens begrijpen is
    onzeker. Bij een gebruikersnaam met een spatie (C:\\Users\\Jan Jansen) staat
    die spatie ook in %LOCALAPPDATA%. Daarom: eerst de gewone map, anders de
    korte 8.3-naam ervan, anders een map buiten het profiel.
    """
    global _werkmap
    if _werkmap is None:
        _werkmap = kies_werkmap(_kandidaten())
        log(f"Werkmap: {_werkmap}")
    pad = os.path.join(_werkmap, sub) if sub else _werkmap
    os.makedirs(pad, exist_ok=True)
    return pad


def _kandidaten():
    lokaal = os.path.join(os.environ.get("LOCALAPPDATA", "."), "MDE", "FusionTools", "werk")
    gebruiker = "".join(t for t in os.environ.get("USERNAME", "gebruiker") if t.isalnum()) or "gebruiker"
    return [
        lokaal,
        korte_naam(lokaal),
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "MDE", "FusionTools", "werk-" + gebruiker),
        os.path.join(r"C:\Users\Public", "MDE", "FusionTools", "werk-" + gebruiker),
    ]


def kies_werkmap(kandidaten):
    """De eerste kandidaat zonder spatie waarin een bestand te schrijven is.

    Lukt geen enkele, dan toch de eerste; de aanroeper zet aanhalingstekens om
    paden met spaties.
    """
    for pad in kandidaten:
        if not pad or " " in pad:
            continue
        try:
            os.makedirs(pad, exist_ok=True)
            proef = os.path.join(pad, ".proef")
            with open(proef, "w") as bestand:
                bestand.write("x")
            os.remove(proef)
            return pad
        except OSError:
            continue
    return kandidaten[0]


def palet_html(naam):
    """Het pad van een paletpagina voor palettes.add: een kopie in de werkmap
    zonder spaties, met schuine strepen.

    De ingebouwde browser wil schuine strepen (met backslashes geeft hij
    ERR_INVALID_URL), en of hij een spatie in het pad aankan is onzeker. De
    pagina wordt daarom bij elk gebruik uit de add-in map naar de werkmap
    gekopieerd, zodat een nieuwe versie van de add-in ook meteen geldt.
    """
    import shutil
    bron = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", naam)
    doel = os.path.join(werkmap("html"), naam)
    try:
        shutil.copyfile(bron, doel)
    except OSError as ex:
        log(f"Paletpagina niet te kopiëren naar {doel}: {ex}; de bron wordt gebruikt.")
        doel = bron
    return doel.replace("\\", "/")


def korte_naam(pad):
    """De 8.3-schrijfwijze van een pad (C:\\Users\\JANJAN~1\\...), of "" als die er niet is.

    Alleen voor een pad dat bestaat; de map wordt daarom eerst aangemaakt.
    """
    try:
        os.makedirs(pad, exist_ok=True)
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        kernel32.GetShortPathNameW.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(1024)
        lengte = kernel32.GetShortPathNameW(pad, buffer, len(buffer))
        return buffer.value if 0 < lengte < len(buffer) else ""
    except Exception:
        return ""
