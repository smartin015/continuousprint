import unittest
from ..data import GCODE_SCRIPTS, PRINTER_PROFILES


class TestGCODEScripts(unittest.TestCase):
    def test_has_all_fields(self):
        for k, v in GCODE_SCRIPTS.items():
            with self.subTest(script=k):
                self.assertEqual(
                    sorted(v.keys()),
                    sorted(["description", "gcode", "name", "version"]),
                )


class TestPrinterProfiles(unittest.TestCase):
    def test_has_all_fields(self):
        for k, v in PRINTER_PROFILES.items():
            with self.subTest(profile=k):
                self.assertEqual(
                    sorted(v.keys()),
                    sorted(
                        [
                            "name",
                            "make",
                            "model",
                            "width",
                            "depth",
                            "height",
                            "formFactor",
                            "selfClearing",
                            "defaults",
                            "extra_tags",
                        ]
                    ),
                )
                self.assertEqual(
                    sorted(v["defaults"].keys()), sorted(["clearBed", "finished"])
                )

    def test_referential_integrity(self):
        for k, v in PRINTER_PROFILES.items():
            for s in ["clearBed", "finished"]:
                with self.subTest(profile=k, script=s):
                    self.assertNotEqual(GCODE_SCRIPTS.get(v["defaults"][s]), None)
