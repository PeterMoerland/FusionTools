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
        jobmap = os.path.join(basis, "jobs")
        uitmap = os.path.join(basis, "uit")
        markering = os.path.join(basis, "gestart.txt")

        def boom(wortelmap):
            regels = []
            for wortel, _, bestanden in os.walk(wortelmap):
                for b in bestanden:
                    pad = os.path.join(wortel, b)
                    st = os.stat(pad)
                    regels.append(f"  {time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}  "
                                  f"{st.st_size:>8} b  {os.path.relpath(pad, wortelmap)}")
            return regels or ["  (leeg)"]

        if not os.path.exists(markering):
            # Stap 1: schoon beginnen en een enkele export starten. De job staat op
            # een pad zonder spaties, de uitvoermap is een andere map dan die van de
            # job, zodat te zien is welke van de twee het commando gebruikt.
            shutil.rmtree(basis, ignore_errors=True)
            os.makedirs(jobmap)
            os.makedirs(uitmap)
            job = os.path.join(jobmap, "MDE_2_layer.cam")
            shutil.copy2(r"Z:\Fusion PCB\CAM processor job files\MDE_2_layer.cam", job)

            cmd = f"Electron.mfgexport {uitmap} {job}"
            log("STAP 1: export gestart")
            log("  " + cmd)
            begin = time.time()
            try:
                uit = app.executeTextCommand(cmd)
                log(f"  -> {uit!r}  (duur {time.time() - begin:.1f} s)")
            except Exception as ex:
                log(f"  EXCEPTION {type(ex).__name__}: {ex}")
            with open(markering, "w") as f:
                f.write(time.strftime("%H:%M:%S"))
            log("  Draai dit script over een halve minuut nog eens voor stap 2.")
        else:
            with open(markering) as f:
                log(f"STAP 2: export gestart om {f.read()}, nu {time.strftime('%H:%M:%S')}")
            log("Inhoud van de hele proefmap (tijd, grootte, pad):")
            regels = boom(basis)
            for r in regels:
                log(r)
            os.remove(markering)
            log("(markering verwijderd; een volgende run begint weer bij stap 1)")

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
