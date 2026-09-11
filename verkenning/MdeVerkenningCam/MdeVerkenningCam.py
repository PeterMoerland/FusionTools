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
        for cmd in ("?", "Electron.?", "Commands.?", "Electron::CAMProcessor ?", "Toolkit.cmdList"):
            log(f"executeTextCommand({cmd!r}):")
            try:
                uit = app.executeTextCommand(cmd)
                uit = uit if uit is not None else "<None>"
                if len(uit) > 4000:
                    uit = uit[:4000] + f"\n  ... ({len(uit)} tekens in totaal)"
                for regel in str(uit).splitlines() or ["<leeg>"]:
                    log("  " + regel)
            except Exception as ex:
                log(f"  EXCEPTION {type(ex).__name__}: {ex}")
            log()

        # 3. Als het tekstcommando geen dialoog opende, dan via de commandodefinitie.
        log("(CAMExport niet opnieuw gestart; dat is al aangetoond)")

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
