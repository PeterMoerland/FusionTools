"""De standaardcomponenten ophalen bij de MDE-app.

    GET https://everything.mde-automation.nl/mde/api/componenten
    X-Sleutel: <gedeelde sleutel>

Het antwoord is een JSON-lijst met per component gpn, soort (R/C), grootte,
waardeBasis, waardeTekst, tolerantie, vermogen, spanning, dielectricum en
omschrijving. De tabel is klein en verandert zelden; hij wordt in een keer
opgehaald en een paar minuten in het geheugen gehouden.

Alleen de standaardbibliotheek: requests is in Fusion niet gegarandeerd. Het
https-certificaat komt van de interne CA van MDE; Python op Windows leest de
certificaatwinkel van Windows, waar dat certificaat op elke werkplek in staat.
Staat het er niet, dan kan een pad naar mde-root.crt worden meegegeven.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request

STANDAARD_URL = "https://everything.mde-automation.nl/mde/api/componenten"
CACHE_SECONDEN = 5 * 60
TIMEOUT_SECONDEN = 10


class ComponentenFout(Exception):
    """Een melding voor de gebruiker; de oorzaak staat in de tekst."""


_cache = {"url": None, "tijd": 0, "lijst": None}


def haal(url, sleutel, certificaat=None, vernieuw=False):
    """Alle standaardcomponenten als lijst van dicts. Gooit ComponentenFout."""
    url = url or STANDAARD_URL
    if not vernieuw and _cache["lijst"] is not None and _cache["url"] == url \
            and time.time() - _cache["tijd"] < CACHE_SECONDEN:
        return _cache["lijst"]

    if not sleutel:
        raise ComponentenFout("Er is nog geen componentensleutel ingesteld.")

    aanvraag = urllib.request.Request(url, headers={"X-Sleutel": sleutel, "Accept": "application/json"})
    context = ssl.create_default_context()
    # Het bedrijfscertificaat (de Caddy-root van de MDE-app) gaat met de add-in
    # mee, zodat het niet op elke pc in de Windows-winkel hoeft te staan.
    meegeleverd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "mde-root.crt")
    if os.path.isfile(meegeleverd):
        try:
            context.load_verify_locations(meegeleverd)
        except (OSError, ssl.SSLError):
            pass
    if certificaat:
        try:
            context.load_verify_locations(certificaat)
        except (OSError, ssl.SSLError) as ex:
            raise ComponentenFout(f"Certificaat niet te laden: {certificaat} ({ex})")

    try:
        with urllib.request.urlopen(aanvraag, context=context, timeout=TIMEOUT_SECONDEN) as antwoord:
            gegevens = json.loads(antwoord.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        if ex.code == 401:
            raise ComponentenFout("Componentensleutel onjuist (401).")
        if ex.code == 404:
            raise ComponentenFout("Componentendatabase niet beschikbaar (404): het endpoint staat uit "
                                  "of de database is onbereikbaar.")
        raise ComponentenFout(f"De MDE-app antwoordde met fout {ex.code}.")
    except urllib.error.URLError as ex:
        reden = getattr(ex, "reason", ex)
        if isinstance(reden, ssl.SSLCertVerificationError):
            raise ComponentenFout("Het certificaat van de MDE-app wordt niet vertrouwd. Installeer mde-root.crt "
                                  "in Windows of stel het pad ernaar in (componenten_certificaat).")
        raise ComponentenFout(f"De MDE-app is niet bereikbaar: {reden}")
    except (ValueError, OSError) as ex:
        raise ComponentenFout(f"Antwoord van de MDE-app niet te lezen: {ex}")

    if not isinstance(gegevens, list):
        raise ComponentenFout("Onverwacht antwoord van de MDE-app (geen lijst).")

    _cache.update(url=url, tijd=time.time(), lijst=gegevens)
    return gegevens


def vergeet():
    _cache.update(url=None, tijd=0, lijst=None)
