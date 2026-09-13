"""Tests voor de stuklijst, buiten Fusion te draaien:

    python -m unittest discover -s tests -v
"""

import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addin", "MdeFusionTools"))
import bom  # noqa: E402


def deel(naam, waarde, footprint, populate=True, **attributen):
    return bom.Onderdeel(naam, waarde, footprint, populate, attributen)


class BouwTest(unittest.TestCase):

    def test_groepeert_op_waarde_footprint_en_mpn(self):
        regels = bom.bouw([
            deel("R10", "10k", "RESC1005X40", MPN="A"),
            deel("R2", "10k", "RESC1005X40", MPN="A"),
            deel("R3", "10k", "RESC1005X40", MPN="B"),
        ])
        self.assertEqual([(r.aantal, r.referenties) for r in regels],
                         [(2, ["R2", "R10"]), (1, ["R3"])])

    def test_eigen_onderdelen_en_niet_geplaatste_vallen_weg(self):
        regels = bom.bouw([
            deel("MH1", "PCB_MOUNT", "PCB_MOUNT_3.2MM", MANUFACTURER="MDE"),
            deel("J3", "BK+", "SOLDER_PADS", MANUFACTURER="mde"),
            deel("C9", "100nF", "CAPC1005X60", populate=False, MPN="X"),
            deel("C1", "100nF", "CAPC1005X60", MPN="X"),
        ])
        self.assertEqual([r.referenties for r in regels], [["C1"]])

    def test_leeg_attribuut_wordt_aangevuld_uit_ander_element(self):
        regels = bom.bouw([
            deel("C1", "1u", "CAPC", MPN="M", MANUFACTURER=""),
            deel("C2", "1u", "CAPC", MPN="M", MANUFACTURER="Murata"),
        ])
        self.assertEqual(regels[0].attributen["MANUFACTURER"], "Murata")

    def test_volgorde_is_natuurlijk_op_eerste_referentie(self):
        regels = bom.bouw([
            deel("R10", "a", "f", MPN="1"),
            deel("C2", "b", "f", MPN="2"),
            deel("R9", "c", "f", MPN="3"),
        ])
        self.assertEqual([r.referenties[0] for r in regels], ["C2", "R9", "R10"])


class SchrijfTest(unittest.TestCase):

    def _schrijf_en_lees(self, regels):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "bom.csv")
            bom.schrijf(pad, regels)
            with open(pad, encoding="utf-8-sig", newline="") as f:
                rijen = list(csv.reader(f))
            with open(pad, encoding="utf-8-sig") as f:
                ruw = f.read()
        return rijen, ruw

    def test_komma_en_aanhalingsteken_blijven_in_hun_kolom(self):
        omschrijving = 'Connector, 3 pos, 1.25mm "GH" series, right angle'
        regels = bom.bouw([deel("J5", "BM03B-GHS", "CONN", MPN="BM03B-GHS-TBT(LF)(SN)(N)",
                                DESCRIPTION=omschrijving)])
        rijen, _ = self._schrijf_en_lees(regels)

        self.assertEqual(rijen[0], list(bom.KOPREGEL))
        self.assertEqual(len(rijen[1]), len(bom.KOPREGEL))
        kolom = dict(zip(bom.KOPREGEL, rijen[1]))
        self.assertEqual(kolom["DESCRIPTION"], omschrijving)
        self.assertEqual(kolom["QTY"], "1")

    def test_ruwe_regel_is_gequote_waar_nodig(self):
        regels = bom.bouw([deel("R1", "10k, 1%", "RESC", MPN="M")])
        _, ruw = self._schrijf_en_lees(regels)
        self.assertIn('"10k, 1%"', ruw.splitlines()[1])

    def test_elk_veld_staat_tussen_aanhalingstekens(self):
        regels = bom.bouw([deel("C4", "100uF", "CAPC3225X135", MPN="885012109004", PACKAGE_SIZE="0402")])
        _, ruw = self._schrijf_en_lees(regels)

        for regel in ruw.splitlines():
            # Elke regel begint en eindigt met een aanhalingsteken, en tussen de
            # velden staat precies "," - dan is elk veld gequote.
            self.assertTrue(regel.startswith('"') and regel.endswith('"'), regel)
            self.assertEqual(regel.count('","'), len(bom.KOPREGEL) - 1, regel)

        self.assertIn('"885012109004"', ruw)
        self.assertIn('"0402"', ruw)
        self.assertIn('"1"', ruw)  # ook het aantal

    def test_jlcpcb_drie_kolommen_plus_mpn_alles_gequote(self):
        regels = bom.bouw([
            deel("C2", "100nF", "CAPC1005X60", MPN="CL05B104KO5NNNC"),
            deel("C9", "100nF", "CAPC1005X60", MPN="CL05B104KO5NNNC"),
            deel("C1", "100uF", "CAPC3225X135", MPN="885012109004"),
            deel("R1", "10k, 1%", "RESC1005X40"),
        ])
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "jlc.csv")
            bom.schrijf_jlcpcb(pad, regels)
            with open(pad, "rb") as f:
                ruw = f.read()
        tekst = ruw.decode("utf-8")

        self.assertFalse(ruw.startswith(b"\xef\xbb\xbf"), "geen byte order mark voor JLCPCB")
        self.assertEqual(tekst.splitlines(), [
            '"Comment","Designator","Footprint","MPN"',
            '"100uF","C1","CAPC3225X135","885012109004"',
            '"100nF","C2, C9","CAPC1005X60","CL05B104KO5NNNC"',
            '"10k, 1%","R1","RESC1005X40",""',
        ])

    def test_micro_teken_overleeft_de_rondgang(self):
        regels = bom.bouw([deel("C1", "2.2µF 100V", "CAPC", MPN="M")])
        rijen, _ = self._schrijf_en_lees(regels)
        self.assertEqual(dict(zip(bom.KOPREGEL, rijen[1]))["Value"], "2.2µF 100V")


if __name__ == "__main__":
    unittest.main()
