"""Tweede verkenning: is de CAM-export vanuit een add-in te starten?

De exportManager van de API kan geen Gerber. Fusion heeft wel een interne
tekstcommando-interface (Application.executeTextCommand) en de CAM-export
bestaat als commando: Electron::CAMExport. Dit script probeert dat commando op
de twee manieren die de API biedt en legt vast wat er gebeurt. Wat er op het
scherm verschijnt, ziet de gebruiker; dit rapport legt vast wat de API zegt.
"""

import os
import traceback

import adsk.core

RAPPORT = os.path.join(os.environ.get("LOCALAPPDATA", "."), "MDE", "FusionTools", "verkenning-cam.txt")


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    regels = []

    def log(tekst=""):
        regels.append(tekst)

    try:
        log(f"Actief product: {app.activeProduct.productType if app.activeProduct else '-'}")
        log()

        # 1. Welke Electron-commando's zijn er precies, met hun huidige staat.
        log("Electron-commando's:")
        defs = ui.commandDefinitions
        for i in range(defs.count):
            d = defs.item(i)
            if d.id.startswith("Electron::"):
                # Niet elk commando heeft een controlDefinition; sommige geven een
                # InternalValidationError. Dat mag de rest niet tegenhouden.
                try:
                    ctrl = d.controlDefinition
                    staat = f"enabled={ctrl.isEnabled} visible={ctrl.isVisible}"
                except Exception as ex:
                    staat = f"(geen controlDefinition: {type(ex).__name__})"
                log(f"  {d.id}  |  {d.name}  |  {staat}")
        log()

        # 2. Tekstcommando's die iets zeggen over wat er beschikbaar is. Onbekende
        #    commando's geven een foutmelding terug in plaats van een exception;
        #    die tekst is op zichzelf informatief.
        import shutil, time
        basis = os.path.join(os.environ.get("LOCALAPPDATA", "."), "MDE", "FusionTools", "mfgexport-proef")
        shutil.rmtree(basis, ignore_errors=True)
        os.makedirs(basis, exist_ok=True)

        # De job gekopieerd naar een pad zonder spaties, voor het geval de parser
        # op spaties splitst en aanhalingstekens niet begrijpt.
        job_origineel = r"Z:\Fusion PCB\CAM processor job files\MDE_2_layer.cam"
        job_kort = os.path.join(basis, "MDE_2_layer.cam")
        shutil.copy2(job_origineel, job_kort)

        varianten = [
            ("A: geen quotes, job zonder spaties",
             lambda m: f"Electron.mfgexport {m} {job_kort}"),
            ("B: geen quotes, schuine strepen",
             lambda m: f"Electron.mfgexport {m.replace(chr(92), '/')} {job_kort.replace(chr(92), '/')}"),
            ("C: quotes om beide, job zonder spaties",
             lambda m: f'Electron.mfgexport "{m}" "{job_kort}"'),
            ("D: geen quotes om map, quotes om job met spaties",
             lambda m: f'Electron.mfgexport {m} "{job_origineel}"'),
        ]

        for letter, (naam, bouw) in zip("ABCD", varianten):
            uitmap = os.path.join(basis, "uit_" + letter)
            os.makedirs(uitmap, exist_ok=True)
            cmd = bouw(uitmap)
            log(f"{naam}")
            log(f"  {cmd}")
            begin = time.time()
            try:
                uit = app.executeTextCommand(cmd)
                log(f"  -> {uit!r}  (duur {time.time() - begin:.1f} s)")
            except Exception as ex:
                log(f"  EXCEPTION {type(ex).__name__}: {ex}  (duur {time.time() - begin:.1f} s)")
            gevonden = []
            for wortel, _, bestanden in os.walk(uitmap):
                for b in bestanden:
                    pad = os.path.join(wortel, b)
                    gevonden.append(f"{os.path.relpath(pad, uitmap)} ({os.path.getsize(pad)} b)")
            log("  inhoud: " + (", ".join(gevonden) if gevonden else "(leeg)"))
            log()

    except Exception:
        log()
        log("FOUT:")
        log(traceback.format_exc())

    os.makedirs(os.path.dirname(RAPPORT), exist_ok=True)
    with open(RAPPORT, "w", encoding="utf-8") as bestand:
        bestand.write("\n".join(regels))

    ui.messageBox(
        "Rapport weggeschreven naar:\n" + RAPPORT +
        "\n\nIs er een CAM-dialoog geopend? Zo ja: welke job stond er voorgeselecteerd?",
        "MDE verkenning CAM")
