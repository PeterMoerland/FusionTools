"""De zip die de CAM-processor oplevert: de stuklijst erin vervangen.

Dit deel kent Fusion niet en is buiten Fusion te testen. Een zip laat zich niet
ter plekke wijzigen; het bestand wordt opnieuw opgebouwd met alle leden behalve
de stuklijst, en die komt er onder dezelfde naam met onze inhoud bij. Zo merkt
wat de zip verder leest er niets van.
"""

import os
import shutil
import tempfile
import zipfile

# Zo heet de stuklijst die de CAM-job schrijft: %ASSEMBLYPREFIX/%N-BOM.csv, met
# ASSEMBLYPREFIX = CAMOutputs/Assembly. De vergelijking is ongevoelig voor
# hoofdletters en voor het scheidingsteken.
BOM_MAP = "camoutputs/assembly/"
BOM_ACHTERVOEGSEL = "-bom.csv"


def zoek_bom_lid(zip_pad):
    """De naam van het stuklijstlid in de zip, of None als die er niet in zit.

    Geeft ook None als het bestand (nog) geen geldige zip is; dat gebeurt terwijl
    Fusion er nog aan schrijft.
    """
    try:
        with zipfile.ZipFile(zip_pad) as zf:
            for naam in zf.namelist():
                genormaliseerd = naam.replace("\\", "/").lower()
                if genormaliseerd.startswith(BOM_MAP) and genormaliseerd.endswith(BOM_ACHTERVOEGSEL):
                    return naam
    except (zipfile.BadZipFile, OSError):
        return None
    return None


def vervang_bom(zip_pad, bom_bytes):
    """Vervangt de stuklijst in de zip door bom_bytes. Geeft de lidnaam terug.

    Herschrijft naar een tijdelijk bestand naast de zip en zet dat er pas over
    heen als het compleet is, zodat een fout halverwege de oorspronkelijke zip
    niet beschadigt.
    """
    lid = zoek_bom_lid(zip_pad)
    if lid is None:
        raise ValueError("De zip bevat geen stuklijst onder CAMOutputs/Assembly.")

    map_ = os.path.dirname(os.path.abspath(zip_pad))
    handle, tijdelijk = tempfile.mkstemp(prefix=".mde-", suffix=".zip", dir=map_)
    os.close(handle)

    try:
        with zipfile.ZipFile(zip_pad) as bron, \
                zipfile.ZipFile(tijdelijk, "w", compression=zipfile.ZIP_DEFLATED) as doel:
            for info in bron.infolist():
                if info.filename == lid:
                    continue
                # De oorspronkelijke ZipInfo meenemen houdt tijdstempels en
                # bestandsattributen zoals ze waren.
                doel.writestr(info, bron.read(info.filename))

            doel.writestr(lid, bom_bytes)

        shutil.move(tijdelijk, zip_pad)
    except Exception:
        try:
            os.remove(tijdelijk)
        except OSError:
            pass
        raise

    return lid


def is_stabiel(pad, vorige_grootte):
    """Of een bestand sinds de vorige meting niet meer gegroeid is.

    Fusion schrijft de zip in stappen; pas als de grootte gelijk blijft en het
    bestand als zip te openen is, is hij af.
    """
    try:
        grootte = os.path.getsize(pad)
    except OSError:
        return False, None
    return (grootte == vorige_grootte and grootte > 0), grootte
