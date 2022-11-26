import unittest
from io import StringIO
from ..data import GCODE_SCRIPTS, PRINTER_PROFILES, PREPROCESSORS
from asteval import Interpreter


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


def test_preprocessor(name):
    def preprocessor_decorator(func):
        def testcase(self):
            def runInterp(symtable):
                stdout = StringIO()
                interp = Interpreter(writer=stdout)
                for (k, v) in symtable.items():
                    interp.symtable[k] = v
                return interp(PREPROCESSORS[name]["body"], raise_errors=True), stdout

            return func(self, runInterp)

        testcase._preprocessor_name = name
        return testcase

    return preprocessor_decorator


class TestPreprocessors(unittest.TestCase):
    def test_all_preprocessors_tested(self):
        tested = set()
        for k in dir(TestPreprocessors):
            v = getattr(TestPreprocessors, k)
            if hasattr(v, "_preprocessor_name"):
                tested.add(v._preprocessor_name)
        self.assertEqual(tested, set([p["name"] for p in PREPROCESSORS.values()]))

    def test_has_all_fields(self):
        for k, v in PREPROCESSORS.items():
            with self.subTest(preprocessor=k):
                self.assertEqual(
                    sorted(v.keys()),
                    sorted(["body", "name"]),
                )

    @test_preprocessor("If the bed temperature is >40C")
    def test_bed_temp(self, pp):
        self.assertEqual(pp(dict(current=dict(bed_temp=40)))[0], False)
        self.assertEqual(pp(dict(current=dict(bed_temp=41)))[0], True)

    @test_preprocessor('If print filename ends in "_special.gcode"')
    def test_filename_special(self, pp):
        self.assertEqual(pp(dict(current=dict(path="foo.gcode")))[0], False)
        self.assertEqual(pp(dict(current=dict(path="foo_special.gcode")))[0], True)

    @test_preprocessor("If print will be at least 10mm high")
    def test_print_height(self, pp):
        self.assertEqual(
            pp(dict(metadata=dict(analysis=dict(dimensions=dict(height=9)))))[0], False
        )
        self.assertEqual(
            pp(dict(metadata=dict(analysis=dict(dimensions=dict(height=10)))))[0], True
        )

    @test_preprocessor("If print takes on average over an hour to complete")
    def test_avg_print_time(self, pp):
        self.assertEqual(
            pp(
                dict(
                    metadata=dict(statistics=dict(averagePrintTime=dict(_default=500)))
                )
            )[0],
            False,
        )
        self.assertEqual(
            pp(
                dict(
                    metadata=dict(
                        statistics=dict(averagePrintTime=dict(_default=60 * 60 + 1))
                    )
                )
            )[0],
            True,
        )

    @test_preprocessor("If print has failed more than 10% of the time")
    def test_failure_rate(self, pp):
        history = [dict(success=False)]
        for i in range(10):
            history.append(dict(success=True))
        self.assertEqual(pp(dict(metadata=dict(history=history)))[0], False)
        history.append(dict(success=False))
        self.assertEqual(pp(dict(metadata=dict(history=history)))[0], True)

    @test_preprocessor("Also notify of bed temperature")
    def test_notify(self, pp):
        result, stdout = pp(dict(current=dict(bed_temp=1)))
        stdout.seek(0)
        self.assertEqual(stdout.read(), "Preprocessor says the bed temperature is 1\n")

    @test_preprocessor("Error and pause if bed is >60C")
    def test_error(self, pp):
        self.assertEqual(pp(dict(current=dict(bed_temp=1)))[0], True)
        with self.assertRaisesRegex(Exception, "600C"):
            pp(dict(current=dict(bed_temp=600)))

    @test_preprocessor("If starting from idle (first run, or ran finished script)")
    def test_from_idle(self, pp):
        self.assertEqual(
            pp(
                dict(
                    current=dict(state="_state_clearing"),
                )
            )[0],
            False,
        )
        self.assertEqual(
            pp(
                dict(
                    current=dict(state="_state_inactive"),
                )
            )[0],
            True,
        )
        self.assertEqual(
            pp(
                dict(
                    current=dict(state="_state_idle"),
                )
            )[0],
            True,
        )
