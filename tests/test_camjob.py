"""Tests voor het CAM-jobdeel, buiten Fusion te draaien:

    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addin", "MdeFusionTools"))
import camjob  # noqa: E402


def maak_job(pad, soorten=("odb++", "gerber", "image", "drill", "assembly", "drawing")):
    job = {
        "type": "Fusion Electronics CAM job",
        "output_type": "zip",
        "outputs": [{"output_type": soort, "filename_prefix": f"CAMOutputs/{soort}", "outputs": []}
                    for soort in soorten],
    }
    with open(pad, "w", encoding="utf-8") as f:
        json.dump(job, f)


class LijstEnKeuzeTest(unittest.TestCase):

    def test_lijst_geeft_alleen_cam_bestanden_gesorteerd(self):
        with tempfile.TemporaryDirectory() as map_:
            for naam in ("MDE_4_layer.cam", "notities.txt", "MDE_2_layer.CAM", "MDE_8_layer.cam"):
                open(os.path.join(map_, naam), "w").close()
            self.assertEqual([os.path.basename(p) for p in camjob.lijst(map_)],
                             ["MDE_2_layer.CAM", "MDE_4_layer.cam", "MDE_8_layer.cam"])

    def test_lijst_van_ontbrekende_map_is_leeg(self):
        self.assertEqual(camjob.lijst(os.path.join(tempfile.gettempdir(), "bestaat-niet-mde")), [])

    def test_standaard_kiest_op_aantal_koperlagen(self):
        jobs = [r"Z:\j\MDE_2_layer.cam", r"Z:\j\MDE_4_layer.cam", r"Z:\j\MDE_8_layer.cam"]
        self.assertEqual(camjob.standaard(jobs, 4), jobs[1])
        self.assertEqual(camjob.standaard(jobs, 2), jobs[0])

    def test_standaard_valt_terug_op_laatst_gebruikte_en_dan_de_eerste(self):
        jobs = [r"Z:\j\MDE_2_layer.cam", r"Z:\j\MDE_4_layer.cam"]
        self.assertEqual(camjob.standaard(jobs, 6, laatste=r"z:\J\mde_4_layer.cam"), jobs[1])
        self.assertEqual(camjob.standaard(jobs, 6), jobs[0])
        self.assertIsNone(camjob.standaard([], 2))


class SlankTest(unittest.TestCase):

    def test_houdt_alleen_gerber_en_drill(self):
        with tempfile.TemporaryDirectory() as map_:
            bron = os.path.join(map_, "MDE_2_layer.cam")
            doel = os.path.join(map_, "werk", "job", "MDE_2_layer.cam")
            maak_job(bron)

            weggelaten = camjob.slank(bron, doel)

            with open(doel, encoding="utf-8") as f:
                job = json.load(f)
            self.assertEqual([o["output_type"] for o in job["outputs"]], ["gerber", "drill"])
            self.assertEqual(weggelaten, ["odb++", "image", "assembly", "drawing"])
            self.assertEqual(job["type"], "Fusion Electronics CAM job")


class UitvoerTest(unittest.TestCase):

    def _maak_mfgexport_uitvoer(self, wortel):
        # Zo legt mfgexport het neer: <jobnaam>\<jobnaam>.gbr\CAMOutputs\GerberFiles\...
        gerber = os.path.join(wortel, "MDE_2_layer", "MDE_2_layer.gbr", "CAMOutputs", "GerberFiles")
        os.makedirs(gerber)
        with open(os.path.join(gerber, "copper_top_l1.gbr"), "w") as f:
            f.write("G04 gerber*\n")
        with open(os.path.join(gerber, "drill_1_64.xln"), "w") as f:
            f.write("M48\n")
        return os.path.join(wortel, "MDE_2_layer", "MDE_2_layer.gbr", "CAMOutputs")

    def test_zoekt_camoutputs_waar_mfgexport_hem_neerzet(self):
        with tempfile.TemporaryDirectory() as map_:
            werk = os.path.join(map_, "werk")
            verwacht = self._maak_mfgexport_uitvoer(werk)
            self.assertEqual(camjob.zoek_camoutputs(werk), verwacht)
            self.assertEqual([r for r, _ in camjob.bestanden_in(verwacht)],
                             [os.path.join("GerberFiles", "copper_top_l1.gbr"),
                              os.path.join("GerberFiles", "drill_1_64.xln")])

    def test_geen_camoutputs_geeft_none(self):
        with tempfile.TemporaryDirectory() as map_:
            self.assertIsNone(camjob.zoek_camoutputs(map_))

    def test_zip_heeft_de_paden_van_fusion(self):
        with tempfile.TemporaryDirectory() as map_:
            camoutputs = self._maak_mfgexport_uitvoer(map_)
            assembly = os.path.join(camoutputs, "Assembly")
            os.makedirs(assembly)
            open(os.path.join(assembly, "Board-BOM.csv"), "w").close()

            zip_pad = os.path.join(map_, "Board_2026-09-11.zip")
            aantal = camjob.maak_zip(camoutputs, zip_pad)

            self.assertEqual(aantal, 3)
            with zipfile.ZipFile(zip_pad) as zf:
                self.assertEqual(sorted(zf.namelist()), [
                    "CAMOutputs/Assembly/Board-BOM.csv",
                    "CAMOutputs/GerberFiles/copper_top_l1.gbr",
                    "CAMOutputs/GerberFiles/drill_1_64.xln",
                ])


if __name__ == "__main__":
    unittest.main()
