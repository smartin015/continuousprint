import unittest
from io import StringIO
from octoprint.printer import InvalidFileLocation, InvalidFileType
from collections import namedtuple
from unittest.mock import MagicMock, ANY, patch
from .script_runner import ScriptRunner
from .data import CustomEvents
from .storage.database_test import AutomationDBTest
from .storage import queries
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
        self.s._get_interpreter = lambda: (MagicMock(error=[]), StringIO(), StringIO())

    @patch("continuousprint.script_runner.genEventScript", return_value="foo")
    def test_run_script_for_event(self, ges):
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

    @patch("continuousprint.script_runner.genEventScript", return_value="")
    def test_run_script_for_event_cancel(self, ges):
        # Script run behavior is already tested in test_run_script_for_event
        self.s.run_script_for_event(CustomEvents.PRINT_CANCEL)
        self.s._printer.cancel_print.assert_called()

    @patch("continuousprint.script_runner.genEventScript", return_value="")
    def test_run_script_for_event_cooldown(self, ges):
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


class TestWithInterpreter(AutomationDBTest):
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
        self.s._execute_gcode = MagicMock()

    def test_injection(self):
        queries.assignAutomation(
            dict(foo="G0 X{direction}"),
            dict(bar="{'direction': 5}"),
            {CustomEvents.ACTIVATE.event: [dict(script="foo", preprocessor="bar")]},
        )
        self.s.run_script_for_event(CustomEvents.ACTIVATE)
        self.s._msg.assert_not_called()
        self.s._execute_gcode.assert_called_with(ANY, "G0 X5")

    def test_symbol_carryover(self):
        queries.assignAutomation(
            dict(s1="G0 X{direction}"),
            dict(p1="d=5; {'direction': d}", p2="d += 5; {'direction': d}"),
            {
                CustomEvents.ACTIVATE.event: [
                    dict(script="s1", preprocessor="p1"),
                    dict(script="s1", preprocessor="p2"),
                    dict(script="s1", preprocessor="p2"),
                ]
            },
        )
        self.s.run_script_for_event(CustomEvents.ACTIVATE)
        self.s._execute_gcode.assert_called_with(ANY, "G0 X5\nG0 X10\nG0 X15")

    def test_run_script_has_errors(self):
        queries.assignAutomation(
            dict(foo="G0 X20"),
            dict(bar="raise Exception('testing exception')"),
            {CustomEvents.ACTIVATE.event: [dict(script="foo", preprocessor="bar")]},
        )
        self.s.run_script_for_event(CustomEvents.ACTIVATE)
        self.s._execute_gcode.assert_called_with(ANY, "@pause")
        self.assertRegex(self.s._msg.call_args[0][0], "testing exception")

    def test_run_script_has_output(self):
        queries.assignAutomation(
            dict(foo="G0 X20"),
            dict(bar="print('test message')\nTrue"),
            {CustomEvents.ACTIVATE.event: [dict(script="foo", preprocessor="bar")]},
        )
        self.s.run_script_for_event(CustomEvents.ACTIVATE)
        self.s._execute_gcode.assert_called_with(ANY, "G0 X20")
        self.s._msg.assert_called_once()
        self.assertRegex(self.s._msg.call_args[0][0], "test message")

    def test_prev_symbols(self):
        queries.assignAutomation(
            dict(foo="G0 X20"),
            dict(bar="print(previous['printer_state'], previous['action'])\nTrue"),
            {CustomEvents.ACTIVATE.event: [dict(script="foo", preprocessor="bar")]},
        )
        self.s.set_current_symbols(dict(printer_state="IDLE", action="TICK"))
        self.s.run_script_for_event(CustomEvents.ACTIVATE)
        self.assertRegex(self.s._msg.call_args[0][0], "None None")
        self.s._msg.reset_mock()
        self.s.set_current_symbols(dict(printer_state="BUSY", action="TOCK"))
        self.s.run_script_for_event(CustomEvents.ACTIVATE)
        self.assertRegex(self.s._msg.call_args[0][0], "IDLE TICK")
        self.s._msg.reset_mock()
        self.s.run_script_for_event(CustomEvents.ACTIVATE)
        self.assertRegex(self.s._msg.call_args[0][0], "BUSY TOCK")
        self.s._msg.reset_mock()
