"""Tests voor het vervangen van de stuklijst in de CAM-zip:

    python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addin", "MdeFusionTools"))
import campakket  # noqa: E402

FUSION_BOM = b"Qty,Value,Device,Package,Parts\r\n1,Connector, 3 pos,X,Y,J5\r\n"
ONZE_BOM = '"Aantal","Referenties"\r\n"1","J5"\r\n'.encode("utf-8-sig")


def maak_cam_zip(pad, bom_naam="CAMOutputs/Assembly/M-Pede Brake Add-On-BOM.csv"):
    with zipfile.ZipFile(pad, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("CAMOutputs/GerberFiles/copper_top_l1.gbr", b"G04 gerber*\r\n")
        zf.writestr("CAMOutputs/GerberFiles/gerber_job.gbrjob", b"{}")
        zf.writestr("CAMOutputs/Assembly/PnP_M-Pede Brake Add-On_CPL_front.csv", b"cpl\r\n")
        if bom_naam:
            zf.writestr(bom_naam, FUSION_BOM)


class ZoekTest(unittest.TestCase):

    def test_vindt_de_stuklijst_ongeacht_hoofdletters(self):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "cam.zip")
            maak_cam_zip(pad, bom_naam="camoutputs/ASSEMBLY/Board-bom.CSV")
            self.assertEqual(campakket.zoek_bom_lid(pad), "camoutputs/ASSEMBLY/Board-bom.CSV")

    def test_geen_stuklijst_geeft_none(self):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "cam.zip")
            maak_cam_zip(pad, bom_naam=None)
            self.assertIsNone(campakket.zoek_bom_lid(pad))

    def test_half_geschreven_bestand_geeft_none(self):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "cam.zip")
            with open(pad, "wb") as f:
                f.write(b"PK\x03\x04 dit is geen complete zip")
            self.assertIsNone(campakket.zoek_bom_lid(pad))


class VervangTest(unittest.TestCase):

    def test_vervangt_alleen_de_stuklijst_en_laat_de_rest_staan(self):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "cam.zip")
            maak_cam_zip(pad)

            lid = campakket.vervang_bom(pad, ONZE_BOM)

            self.assertEqual(lid, "CAMOutputs/Assembly/M-Pede Brake Add-On-BOM.csv")
            with zipfile.ZipFile(pad) as zf:
                namen = sorted(zf.namelist())
                self.assertEqual(namen, sorted([
                    "CAMOutputs/GerberFiles/copper_top_l1.gbr",
                    "CAMOutputs/GerberFiles/gerber_job.gbrjob",
                    "CAMOutputs/Assembly/PnP_M-Pede Brake Add-On_CPL_front.csv",
                    "CAMOutputs/Assembly/M-Pede Brake Add-On-BOM.csv",
                ]))
                self.assertEqual(zf.read(lid), ONZE_BOM)
                self.assertEqual(zf.read("CAMOutputs/GerberFiles/copper_top_l1.gbr"), b"G04 gerber*\r\n")
                self.assertIsNone(zf.testzip())

            # Geen tijdelijk bestand achtergelaten.
            self.assertEqual(os.listdir(map_), ["cam.zip"])

    def test_zonder_stuklijst_blijft_de_zip_onaangeroerd(self):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "cam.zip")
            maak_cam_zip(pad, bom_naam=None)
            with open(pad, "rb") as f:
                voor = f.read()

            with self.assertRaises(ValueError):
                campakket.vervang_bom(pad, ONZE_BOM)

            with open(pad, "rb") as f:
                self.assertEqual(f.read(), voor)
            self.assertEqual(os.listdir(map_), ["cam.zip"])


class StabielTest(unittest.TestCase):

    def test_stabiel_als_grootte_gelijk_blijft(self):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "x.zip")
            with open(pad, "wb") as f:
                f.write(b"abc")
            stabiel, grootte = campakket.is_stabiel(pad, None)
            self.assertFalse(stabiel)
            stabiel, _ = campakket.is_stabiel(pad, grootte)
            self.assertTrue(stabiel)

    def test_ontbrekend_bestand_is_niet_stabiel(self):
        stabiel, grootte = campakket.is_stabiel(os.path.join(tempfile.gettempdir(), "bestaat-niet.zip"), None)
        self.assertFalse(stabiel)
        self.assertIsNone(grootte)


if __name__ == "__main__":
    unittest.main()
