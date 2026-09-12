"""Tests voor de controle op standaardcomponenten, buiten Fusion te draaien:

    python -m unittest discover -s tests -v

De waardes komen van het testboard (verkenning.txt); de standaardcomponenten
zijn nagemaakt naar het antwoord van api/componenten.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addin", "MdeFusionTools"))
import standaard  # noqa: E402


def comp(gpn, soort, grootte, basis, tekst, tolerantie=None, vermogen=None, spanning=None, dielectricum=None):
    return {"gpn": gpn, "soort": soort, "grootte": grootte, "waardeBasis": basis, "waardeTekst": tekst,
            "tolerantie": tolerantie, "vermogen": vermogen, "spanning": spanning,
            "dielectricum": dielectricum, "omschrijving": f"{tekst} {soort} {grootte}"}


COMPONENTEN = [
    comp("GPC0402104", "C", "0402", 1e-07, "100 nF", tolerantie="10", spanning="16V", dielectricum="X7R"),
    comp("GPC0402104H", "C", "0402", 1e-07, "100 nF", tolerantie="10", spanning="50V", dielectricum="X7R"),
    comp("GPC0402222", "C", "0402", 2.2e-09, "2.2 nF", tolerantie="10", spanning="50V", dielectricum="X7R"),
    comp("GPC0603104", "C", "0603", 1e-07, "100 nF", tolerantie="10", spanning="50V", dielectricum="X7R"),
    comp("GPC1210226", "C", "1210", 2.2e-05, "22 uF", tolerantie="10", spanning="25V", dielectricum="X5R"),
    comp("GPR0402103", "R", "0402", 10000, "10 k", tolerantie="1", vermogen="1/16W"),
    comp("GPR0402472", "R", "0402", 4700, "4.7 k", tolerantie="1", vermogen="1/16W"),
    comp("GPR0402221", "R", "0402", 220, "220", tolerantie="1", vermogen="1/16W"),
    comp("GPR04022743", "R", "0402", 27400, "27.4 k", tolerantie="1", vermogen="1/16W"),
    comp("GPR0603105", "R", "0603", 1e6, "1 M", tolerantie="1", vermogen="1/10W"),
]


class SoortEnGrootteTest(unittest.TestCase):

    def test_soort_uit_naam_of_footprint(self):
        self.assertEqual(standaard.soort_van("R12", "RESC1005X40"), "R")
        self.assertEqual(standaard.soort_van("C4", "CAPC3225X135"), "C")
        self.assertEqual(standaard.soort_van("U1", "SOIC127P600X175-8N"), "")
        self.assertEqual(standaard.soort_van("X1", "CAPC1005X60"), "C")

    def test_grootte_uit_package_size_of_footprint(self):
        self.assertEqual(standaard.grootte_van("0402", "RESC1005X40"), "0402")
        self.assertEqual(standaard.grootte_van("", "RESC1005X40"), "0402")
        self.assertEqual(standaard.grootte_van("", "CAPC1608X85"), "0603")
        self.assertEqual(standaard.grootte_van("", "CAPC3225X135"), "1210")
        self.assertEqual(standaard.grootte_van("", "SOIC127P600X175-8N"), "")


class OntleedTest(unittest.TestCase):

    def test_weerstandswaardes(self):
        gevallen = {
            "10k": 10000, "4k7 1/4w": 4700, "220": 220, "27.4k 1/16W 1%": 27400,
            "1M 1/16W 1%": 1e6, "0R": 0, "2R2": 2.2, "1k5": 1500, "100": 100, "47R": 47,
            "10 k": 10000, "4,7k": 4700,
        }
        for tekst, verwacht in gevallen.items():
            with self.subTest(tekst=tekst):
                self.assertAlmostEqual(standaard.ontleed_waarde("R", tekst).basis, verwacht, delta=verwacht * 1e-9 + 1e-12)

    def test_condensatorwaardes(self):
        gevallen = {
            "100nF 16V X7R 10%": 1e-7, "2200pF 16V X7R 10%": 2.2e-9, "56pF 50V X7R 10%": 56e-12,
            "2.2uF 100V X7R 10%": 2.2e-6, "100uF 6.3v X7R": 100e-6, "2n2": 2.2e-9, "100 nF": 1e-7,
            "4.7µF": 4.7e-6, "1u": 1e-6,
        }
        for tekst, verwacht in gevallen.items():
            with self.subTest(tekst=tekst):
                self.assertAlmostEqual(standaard.ontleed_waarde("C", tekst).basis, verwacht, delta=verwacht * 1e-9)

    def test_kenmerken(self):
        k = standaard.ontleed_waarde("C", "100nF 6.3v X7R 10%")
        self.assertEqual((k.spanning, k.dielectricum, k.tolerantie), (6.3, "X7R", 10))
        k = standaard.ontleed_waarde("R", "4k7 1/4w 5%")
        self.assertEqual((k.vermogen, k.tolerantie), (0.25, 5))
        k = standaard.ontleed_waarde("R", "10k")
        self.assertEqual((k.vermogen, k.tolerantie, k.spanning), (None, None, None))

    def test_onleesbaar(self):
        self.assertIsNone(standaard.ontleed_waarde("R", "").basis)
        self.assertIsNone(standaard.ontleed_waarde("C", "PCB_MOUNT").basis)
        self.assertIsNone(standaard.ontleed_waarde("R", "DNP").basis)


class KandidatenTest(unittest.TestCase):

    def test_precies_passend_staat_bovenaan(self):
        k = standaard.ontleed_waarde("C", "100nF 16V X7R 10%")
        lijst = standaard.kandidaten("C", "0402", k, COMPONENTEN)
        self.assertEqual([c.gpn for c in lijst], ["GPC0402104", "GPC0402104H"])
        self.assertEqual(lijst[0].opmerkingen, [])

    def test_lagere_spanning_krijgt_opmerking_en_zakt(self):
        k = standaard.ontleed_waarde("C", "100nF 25V X7R 10%")
        lijst = standaard.kandidaten("C", "0402", k, COMPONENTEN)
        self.assertEqual(lijst[0].gpn, "GPC0402104H")
        self.assertIn("spanning 16V lager dan 25V", lijst[1].opmerkingen)

    def test_andere_maat_of_waarde_past_niet(self):
        k = standaard.ontleed_waarde("C", "100nF")
        self.assertEqual([c.gpn for c in standaard.kandidaten("C", "0805", k, COMPONENTEN)], [])
        k = standaard.ontleed_waarde("R", "10k")
        self.assertEqual([c.gpn for c in standaard.kandidaten("R", "0402", k, COMPONENTEN)], ["GPR0402103"])
        k = standaard.ontleed_waarde("R", "12k")
        self.assertEqual(standaard.kandidaten("R", "0402", k, COMPONENTEN), [])

    def test_vermogen_en_tolerantie(self):
        k = standaard.ontleed_waarde("R", "4k7 1/4w")
        lijst = standaard.kandidaten("R", "0402", k, COMPONENTEN)
        self.assertEqual(lijst[0].gpn, "GPR0402472")
        self.assertIn("vermogen 1/16W lager dan 0.25W", lijst[0].opmerkingen)

        k = standaard.ontleed_waarde("R", "27.4k 1/16W 1%")
        lijst = standaard.kandidaten("R", "0402", k, COMPONENTEN)
        self.assertEqual(lijst[0].gpn, "GPR04022743")
        self.assertEqual(lijst[0].opmerkingen, [])


class TabelFormatenTest(unittest.TestCase):
    """De schrijfwijzen zoals api/componenten ze werkelijk levert."""

    def test_vermogen_in_milliwatt_past_bij_breuk_op_het_board(self):
        tabel = [comp("GPR0402103", "R", "0402", 10000, "10 k", tolerantie="1", vermogen="62.5mW", spanning="50V"),
                 comp("GPR0603103", "R", "0603", 10000, "10 k", tolerantie="1", vermogen="100mW", spanning="75V")]
        k = standaard.ontleed_waarde("R", "10k 1/16W 1%")
        lijst = standaard.kandidaten("R", "0402", k, tabel)
        self.assertEqual(lijst[0].opmerkingen, [])
        self.assertEqual(lijst[0].score, 4)

        k = standaard.ontleed_waarde("R", "10k 1/4W")
        lijst = standaard.kandidaten("R", "0402", k, tabel)
        self.assertEqual(lijst[0].opmerkingen, ["vermogen 62.5mW lager dan 0.25W"])

    def test_vermogen_op_het_board_in_milliwatt_of_met_spatie(self):
        self.assertAlmostEqual(standaard.ontleed_waarde("R", "10k 62.5mW").vermogen, 0.0625)
        self.assertAlmostEqual(standaard.ontleed_waarde("R", "10k 0.1W").vermogen, 0.1)
        self.assertAlmostEqual(standaard._watt("1/10 W"), 0.1)
        self.assertAlmostEqual(standaard._watt("100 mW"), 0.1)
        self.assertIsNone(standaard._watt(None))

    def test_dielectricum_als_lijst_en_np0_is_c0g(self):
        tabel = [comp("GPC0402220", "C", "0402", 22e-12, "22 pF", tolerantie="5", spanning="50V", dielectricum="C0G, NP0"),
                 comp("GPC0402220X", "C", "0402", 22e-12, "22 pF", tolerantie="10", spanning="50V", dielectricum="X7R")]
        k = standaard.ontleed_waarde("C", "22pF 50V NP0 5%")
        lijst = standaard.kandidaten("C", "0402", k, tabel)
        self.assertEqual(lijst[0].gpn, "GPC0402220")
        self.assertEqual(lijst[0].opmerkingen, [])
        self.assertIn("dielectricum X7R i.p.v. C0G", lijst[1].opmerkingen)

    def test_absolute_tolerantie_in_pf_geeft_geen_opmerking(self):
        tabel = [comp("GPC04020R5", "C", "0402", 5e-13, "0,5 pF", tolerantie="±0.1pF", spanning="50V",
                      dielectricum="C0G, NP0")]
        k = standaard.ontleed_waarde("C", "0.5pF 50V C0G 10%")
        lijst = standaard.kandidaten("C", "0402", k, tabel)
        self.assertEqual(lijst[0].opmerkingen, [])

    def test_spanning_met_komma_of_spatie(self):
        tabel = [comp("GPC0805107", "C", "0805", 1e-4, "100 uF", tolerantie="20", spanning="6,3V", dielectricum="X5R"),
                 comp("GPC0805107B", "C", "0805", 1e-4, "100 uF", tolerantie="20", spanning="6.3 V", dielectricum="X5R")]
        k = standaard.ontleed_waarde("C", "100uF 6.3v X5R")
        lijst = standaard.kandidaten("C", "0805", k, tabel)
        self.assertEqual([c.opmerkingen for c in lijst], [[], []])


class ControleerTest(unittest.TestCase):

    def _onderdelen(self):
        O = standaard.Onderdeel
        return [
            O("C7", "100nF 16V", "CAPC1005X60", mpn="CL05B104KO5NNNC", package_size="0402"),
            O("C1", "2.2nF 25V X7R 10%", "CAPC1005X60", mpn="CL05B222KB5NNNC", gpn="GPC0402222"),
            O("C4", "100uF 6.3v X7R", "CAPC3225X135", mpn="885012109004", package_size="1210"),
            O("R9", "10k", "RESC1005X40", mpn=""),
            O("R12", "4k7 1/4w", "RESC1005X40", mpn="RC0402FR-074K7L"),
            O("R99", "DNP", "RESC1005X40"),
            O("U1", "STM32C011J4M6", "SOIC127P600X175-8N", mpn="STM32C011J4M6"),
            O("C8", "100nF", "CAPC1005X60", populate=False),
        ]

    def test_status_per_onderdeel(self):
        uitkomsten = standaard.controleer(self._onderdelen(), COMPONENTEN)
        per_naam = {u.naam: u for u in uitkomsten}

        self.assertEqual([u.naam for u in uitkomsten], ["C1", "C4", "C7", "R9", "R12", "R99"])
        self.assertEqual(per_naam["C1"].status, "standaard")
        self.assertEqual(per_naam["C7"].status, "voorstel")
        self.assertEqual(per_naam["C7"].voorstel, "GPC0402104")
        self.assertEqual(per_naam["C4"].status, "geen")
        self.assertEqual(per_naam["R9"].status, "voorstel")
        self.assertEqual(per_naam["R9"].voorstel, "GPR0402103")
        self.assertEqual(per_naam["R12"].status, "voorstel")
        self.assertIn("vermogen", per_naam["R12"].toelichting)
        self.assertEqual(per_naam["R99"].status, "onleesbaar")
        self.assertNotIn("U1", per_naam)
        self.assertNotIn("C8", per_naam)


class ScriptTest(unittest.TestCase):

    def test_attribute_regels(self):
        regels = standaard.script_regels([("R9", "GPR0402103"), ("C7", "GPC0402104"), ("", "X"), ("R1", "")])
        self.assertEqual(regels, ["ATTRIBUTE R9 GPN 'GPR0402103';", "ATTRIBUTE C7 GPN 'GPC0402104';"])


if __name__ == "__main__":
    unittest.main()
