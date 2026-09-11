"""Tests voor de pick-and-place, buiten Fusion te draaien:

    python -m unittest discover -s tests -v

De verwachte regels komen letterlijk uit een CPL die de CAM-processor van
Fusion zelf schreef voor het testboard, met de ruwe elementwaarden uit de
verkenning ernaast.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addin", "MdeFusionTools"))
import cpl  # noqa: E402


def plaatsing(naam, x, y, hoek, mirror, waarde, footprint, populate=True):
    return cpl.Plaatsing(naam, x, y, hoek, bool(mirror), waarde, footprint, populate)


# Uit verkenning.txt (naam | waarde | x | y | hoek | mirror | package) en de
# bijbehorende regels uit PnP_M-Pede Brake Add-On_CPL_front.csv van Fusion.
C1 = plaatsing("C1", 23774400, 17068800, 90.0, 0, "2.2nF 25V X7R 10%", "CAPC1005X60")
C4 = plaatsing("C4", 27188160, 13086080, 270.0, 0, "100uF 6.3v X7R", "CAPC3225X135")
D1 = plaatsing("D1", 12407742, 5312652, 180.0, 0, "CHIP-FLAT-G_0603-0.35MM", "LEDC1608X35N_FLAT-G")
J1 = plaatsing("J1", 29096882, 14996160, 270.0, 0, "", "009296002553906")
J2 = plaatsing("J2", 9147580, 5118880, 90.0, 1, "", "SOLDER_PADS_2.54_4_PIN")


class RegelTest(unittest.TestCase):

    def test_millimeters_met_twee_decimalen_en_aanhalingstekens_bij_spaties(self):
        self.assertEqual(cpl.regel(C1), 'C1,74.30,53.34,90.00,"2.2nF 25V X7R 10%",CAPC1005X60')
        self.assertEqual(cpl.regel(C4), 'C4,84.96,40.89,270.00,"100uF 6.3v X7R",CAPC3225X135')
        self.assertEqual(cpl.regel(D1), "D1,38.77,16.60,180.00,CHIP-FLAT-G_0603-0.35MM,LEDC1608X35N_FLAT-G")

    def test_lege_waarde_blijft_een_leeg_veld(self):
        self.assertEqual(cpl.regel(J1), "J1,90.93,46.86,270.00,,009296002553906")

    def test_komma_en_aanhalingsteken_in_een_veld(self):
        p = plaatsing("R1", 320000, 640000, 0.0, 0, '10k, 1% "dun"', "RESC")
        self.assertEqual(cpl.regel(p), 'R1,1.00,2.00,0.00,"10k, 1% ""dun""",RESC')


class RijenTest(unittest.TestCase):

    def test_splitst_op_zijde_en_sorteert_zoals_fusion(self):
        R2 = plaatsing("R2", 0, 0, 0.0, 0, "1M", "RESC")
        R10 = plaatsing("R10", 0, 0, 0.0, 0, "10k", "RESC")
        R1 = plaatsing("R1", 0, 0, 0.0, 0, "232k", "RESC")
        alles = [J2, R2, R10, C1, R1]

        self.assertEqual([p.naam for p in cpl.rijen(alles, achterkant=False)], ["C1", "R1", "R10", "R2"])
        self.assertEqual([p.naam for p in cpl.rijen(alles, achterkant=True)], ["J2"])

    def test_niet_geplaatste_elementen_vallen_weg_eigen_onderdelen_niet(self):
        weg = plaatsing("C9", 0, 0, 0.0, 0, "100nF", "CAPC", populate=False)
        MH1 = plaatsing("MH1", 2860800, 15022602, 0.0, 0, "PCB_MOUNT_3.2MM", "PCB_MOUNT_3.2MM")
        self.assertEqual([p.naam for p in cpl.rijen([weg, MH1], achterkant=False)], ["MH1"])


class SchrijfTest(unittest.TestCase):

    def test_bestand_heeft_kopregel_en_crlf(self):
        with tempfile.TemporaryDirectory() as map_:
            pad = os.path.join(map_, "PnP_Board_CPL_back.csv")
            cpl.schrijf(pad, [C1, J2], achterkant=True)
            with open(pad, "rb") as f:
                inhoud = f.read()
        self.assertEqual(inhoud, b"Name,X,Y,Angle,Value,Package\r\n"
                                 b"J2,28.59,16.00,90.00,,SOLDER_PADS_2.54_4_PIN\r\n")


if __name__ == "__main__":
    unittest.main()
