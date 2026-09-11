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
