import unittest
from octoprint.printer import InvalidFileLocation, InvalidFileType
from collections import namedtuple
from unittest.mock import MagicMock
from .script_runner import ScriptRunner
from .data import CustomEvents
import logging

# logging.basicConfig(level=logging.DEBUG)

LI = namedtuple("LocalItem", ["sd", "path", "job"])
LJ = namedtuple("Job", ["name"])


class TestScriptRunner(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.s = ScriptRunner(
            msg=MagicMock(),
            file_manager=MagicMock(),
            logger=logging.getLogger(),
            printer=MagicMock(),
            refresh_ui_state=MagicMock(),
            fire_event=MagicMock(),
        )
        self.s._get_user = lambda: "foo"
        self.s._wrap_stream = MagicMock(return_value=None)
        self.s._get_interpreter = lambda: None

    def test_run_script_for_event(self):
        # Note: default scripts are populated on db_init for FINISH and PRINT_SUCCESS
        self.s.run_script_for_event(CustomEvents.FINISH)
        self.s._file_manager.add_file.assert_called()
        self.s._printer.select_file.assert_called_with(
            "ContinuousPrint/tmp/continuousprint_finish.gcode",
            sd=False,
            printAfterSelect=True,
            user="foo",
        )
        self.s._fire_event.assert_called_with(CustomEvents.FINISH)

    def test_run_script_for_event_cancel(self):
        # Script run behavior is already tested in test_run_script_for_event
        self.s.run_script_for_event(CustomEvents.PRINT_CANCEL)
        self.s._printer.cancel_print.assert_called()

    def test_run_script_for_event_cooldown(self):
        # Script run behavior is already tested in test_run_script_for_event
        self.s.run_script_for_event(CustomEvents.COOLDOWN)
        self.s._printer.set_temperature.assert_called_with("bed", 0)

    def test_start_print_local(self):
        self.assertEqual(self.s.start_print(LI(False, "a.gcode", LJ("job1"))), True)
        self.s._printer.select_file.assert_called_with(
            "a.gcode",
            sd=False,
            printAfterSelect=True,
            user="foo",
        )
        self.s._fire_event.assert_called_with(CustomEvents.PRINT_START)

    def test_start_print_sd(self):
        self.assertEqual(self.s.start_print(LI(True, "a.gcode", LJ("job1"))), True)
        self.s._printer.select_file.assert_called_with(
            "a.gcode",
            sd=True,
            printAfterSelect=True,
            user="foo",
        )
        self.s._fire_event.assert_called_with(CustomEvents.PRINT_START)

    def test_start_print_lan(self):
        class NetItem:
            path = "a.gcode"
            job = LJ("job1")
            sd = False

            def resolve(self):
                return "net/a.gcode"

        self.assertEqual(self.s.start_print(NetItem()), True)
        self.s._printer.select_file.assert_called_with(
            "net/a.gcode",
            sd=False,
            printAfterSelect=True,
            user="foo",
        )
        self.s._fire_event.assert_called_with(CustomEvents.PRINT_START)

    def test_start_print_invalid_location(self):
        self.s._printer.select_file.side_effect = InvalidFileLocation()
        self.assertEqual(self.s.start_print(LI(True, "a.gcode", LJ("job1"))), False)
        self.s._fire_event.assert_not_called()

    def test_start_print_invalid_filetype(self):
        self.s._printer.select_file.side_effect = InvalidFileType()
        self.assertEqual(self.s.start_print(LI(True, "a.gcode", LJ("job1"))), False)
        self.s._fire_event.assert_not_called()
