"""Tests voor de werkmap zonder spaties, buiten Fusion te draaien:

    python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addin", "MdeFusionTools"))
import instellingen  # noqa: E402


class WerkmapTest(unittest.TestCase):

    def test_slaat_paden_met_spatie_over(self):
        with tempfile.TemporaryDirectory() as map_:
            met_spatie = os.path.join(map_, "Jan Jansen", "werk")
            zonder = os.path.join(map_, "JANJAN~1", "werk")
            self.assertEqual(instellingen.kies_werkmap([met_spatie, "", zonder]), zonder)
            self.assertTrue(os.path.isdir(zonder))
            self.assertEqual(os.listdir(zonder), [], "het proefbestand is weer weg")

    def test_valt_terug_op_de_eerste_als_niets_lukt(self):
        met_spatie = os.path.join(tempfile.gettempdir(), "Jan Jansen", "werk")
        onmogelijk = os.path.join("Q:", os.sep, "bestaat", "niet")
        self.assertEqual(instellingen.kies_werkmap([met_spatie, onmogelijk]), met_spatie)

    def test_korte_naam_van_een_bestaande_map(self):
        with tempfile.TemporaryDirectory() as map_:
            lang = os.path.join(map_, "Jan Jansen", "werk")
            kort = instellingen.korte_naam(lang)
            if kort:
                # Op een volume met 8.3-namen bevat de korte naam geen spatie meer.
                self.assertNotIn(" ", kort)
                self.assertTrue(os.path.isdir(kort))
            # Zonder 8.3-namen op dit volume is "" een geldig antwoord.

        self.assertEqual(instellingen.korte_naam(""), "")


if __name__ == "__main__":
    unittest.main()
