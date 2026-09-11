"""CAM-jobs en de uitvoer van Electron.mfgexport, buiten Fusion te testen.

Fusion heeft een tekstcommando dat de CAM-processor zonder venster draait:

    Electron.mfgexport <uitvoermap> <job.cam>

Wat de verkenning daarover leerde (zie README):

- Het schrijft losse bestanden, geen zip, ook al zegt de job output_type zip.
- Ze komen niet in de opgegeven map maar ernaast: <bovenliggende map van
  uitvoermap>\\<jobnaam>\\<jobnaam>.gbr\\CAMOutputs\\... Daarom zoeken we de map
  CAMOutputs op in plaats van het pad te voorspellen.
- Alleen de secties gerber en drill leveren iets op. ODB++, afbeeldingen en
  tekeningen geven een foutvenster ("CAM files could not be created"); de
  assembly-sectie (BOM en pick-and-place) levert stilzwijgend niets. Daarom
  krijgt het commando een afgeslankte kopie van de job, en maakt de add-in de
  stuklijst en pick-and-place zelf.
"""

import json
import os
import re
import zipfile

# De secties die mfgexport wel aankan.
BRUIKBARE_UITVOER = ("gerber", "drill")

CAMOUTPUTS = "CAMOutputs"
ASSEMBLY = "Assembly"


def lijst(jobmap):
    """De .cam-bestanden in de jobmap, gesorteerd op naam. Leeg als de map er niet is."""
    try:
        namen = os.listdir(jobmap)
    except OSError:
        return []
    return sorted((os.path.join(jobmap, naam) for naam in namen if naam.lower().endswith(".cam")),
                  key=lambda pad: os.path.basename(pad).lower())


def standaard(jobs, koperlagen, laatste=None):
    """Welke job vooraf geselecteerd wordt.

    Eerst de job die bij het aantal koperlagen hoort (MDE_2_layer.cam bij 2),
    dan de laatst gebruikte, anders de eerste.
    """
    if not jobs:
        return None
    if koperlagen:
        patroon = re.compile(rf"(^|[^0-9]){koperlagen}[ _-]?layer", re.IGNORECASE)
        for job in jobs:
            if patroon.search(os.path.basename(job)):
                return job
    if laatste:
        for job in jobs:
            if os.path.normcase(job) == os.path.normcase(laatste):
                return job
    return jobs[0]


def slank(job_pad, doel_pad):
    """Schrijft een kopie van de job met alleen de secties die mfgexport aankan.

    Geeft de output_types terug die zijn weggelaten, zodat de gebruiker kan zien
    wat er niet uit dit kanaal komt.
    """
    with open(job_pad, encoding="utf-8") as bestand:
        job = json.load(bestand)

    weggelaten = []
    gehouden = []
    for uitvoer in job.get("outputs", []):
        soort = str(uitvoer.get("output_type", "")).lower()
        if soort in BRUIKBARE_UITVOER:
            gehouden.append(uitvoer)
        else:
            weggelaten.append(soort or "?")
    job["outputs"] = gehouden

    os.makedirs(os.path.dirname(doel_pad), exist_ok=True)
    with open(doel_pad, "w", encoding="utf-8") as bestand:
        json.dump(job, bestand, indent=2, ensure_ascii=False)
    return weggelaten


def zoek_camoutputs(wortel):
    """De map CAMOutputs ergens onder wortel, of None. Ongevoelig voor hoofdletters."""
    for map_, submappen, _ in os.walk(wortel):
        for sub in submappen:
            if sub.lower() == CAMOUTPUTS.lower():
                return os.path.join(map_, sub)
    return None


def bestanden_in(map_):
    """(relatief pad, grootte) van alle bestanden onder map_; om te zien of er nog geschreven wordt."""
    resultaat = []
    for wortel, _, namen in os.walk(map_):
        for naam in namen:
            pad = os.path.join(wortel, naam)
            try:
                grootte = os.path.getsize(pad)
            except OSError:
                grootte = -1
            resultaat.append((os.path.relpath(pad, map_), grootte))
    return sorted(resultaat)


def maak_zip(camoutputs, zip_pad):
    """Alles onder CAMOutputs in een zip, met dezelfde paden als de CAM-processor
    van Fusion (CAMOutputs/GerberFiles/..., CAMOutputs/Assembly/...)."""
    aantal = 0
    with zipfile.ZipFile(zip_pad, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for relatief, _ in bestanden_in(camoutputs):
            zf.write(os.path.join(camoutputs, relatief),
                     CAMOUTPUTS + "/" + relatief.replace(os.sep, "/"))
            aantal += 1
    return aantal
