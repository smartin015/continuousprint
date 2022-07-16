import unittest
from octoprint.printer import InvalidFileLocation, InvalidFileType
from collections import namedtuple
from unittest.mock import MagicMock
from .script_runner import ScriptRunner
import logging

logging.basicConfig(level=logging.DEBUG)

LI = namedtuple("LocalItem", ["sd", "path", "job"])
LJ = namedtuple("Job", ["name"])


class TestScriptRunner(unittest.TestCase):
    def setUp(self):
        self.s = ScriptRunner(
            msg=MagicMock(),
            get_key=MagicMock(),
            file_manager=MagicMock(),
            logger=logging.getLogger(),
            printer=MagicMock(),
            refresh_ui_state=MagicMock(),
        )
        self.s._wrap_stream = MagicMock(return_value=None)

    def test_run_finish_script(self):
        self.s.run_finish_script()
        self.s._file_manager.add_file.assert_called()
        self.s._printer.select_file.assert_called_with(
            "ContinuousPrint/cp_queue_finished_script.gcode",
            sd=False,
            printAfterSelect=True,
        )

    def test_cancel_print(self):
        self.s.cancel_print()
        self.s._printer.cancel_print.assert_called()

    def test_clear_bed(self):
        self.s.clear_bed()
        self.s._printer.select_file.assert_called_with(
            "ContinuousPrint/cp_bed_clearing_script.gcode",
            sd=False,
            printAfterSelect=True,
        )

    def test_start_print_local(self):
        self.assertEqual(self.s.start_print(LI(False, "a.gcode", LJ("job1"))), True)
        self.s._printer.select_file.assert_called_with(
            "a.gcode", sd=False, printAfterSelect=True
        )

    def test_start_print_sd(self):
        self.assertEqual(self.s.start_print(LI(True, "a.gcode", LJ("job1"))), True)
        self.s._printer.select_file.assert_called_with(
            "a.gcode", sd=True, printAfterSelect=True
        )

    def test_start_print_lan(self):
        class NetItem:
            path = "a.gcode"
            job = LJ("job1")
            sd = False

            def resolve(self):
                return "net/a.gcode"

        self.assertEqual(self.s.start_print(NetItem()), True)
        self.s._printer.select_file.assert_called_with(
            "net/a.gcode", sd=False, printAfterSelect=True
        )

    def test_start_print_invalid_location(self):
        self.s._printer.select_file.side_effect = InvalidFileLocation()
        self.assertEqual(self.s.start_print(LI(True, "a.gcode", LJ("job1"))), False)

    def test_start_print_invalid_filetype(self):
        self.s._printer.select_file.side_effect = InvalidFileType()
        self.assertEqual(self.s.start_print(LI(True, "a.gcode", LJ("job1"))), False)
