import unittest
from dataclasses import dataclass
from io import StringIO
from octoprint.printer import InvalidFileLocation, InvalidFileType
from octoprint.filemanager.destinations import FileDestinations
from collections import namedtuple
from unittest.mock import MagicMock, ANY, patch
from .script_runner import ScriptRunner
from .data import CustomEvents
from .storage.database_test import AutomationDBTest
from .storage import queries
from .storage.database import SetView
from .storage.lan import LANResolveError
import logging

# logging.basicConfig(level=logging.DEBUG)

LJ = namedtuple("Job", ["name"])


@dataclass
class LI(SetView):
    sd: bool = False
    path: str = "test.gcode"
    job: namedtuple = None

    def resolve(self, override=None):
        if getattr(self, "_resolved", None) is None:
            self._resolved = self.path
        return super().resolve(override)


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
        self.assertEqual(
            self.s.start_print(LI(False, "a.gcode", LJ("job1")), MagicMock()), True
        )
        self.s._printer.select_file.assert_called_with(
            "a.gcode",
            sd=False,
            printAfterSelect=True,
            user="foo",
        )
        self.s._fire_event.assert_called_with(CustomEvents.PRINT_START)

    def test_start_print_sd(self):
        self.assertEqual(
            self.s.start_print(LI(True, "a.gcode", LJ("job1")), MagicMock()), True
        )
        self.s._printer.select_file.assert_called_with(
            "a.gcode",
            sd=True,
            printAfterSelect=True,
            user="foo",
        )
        self.s._fire_event.assert_called_with(CustomEvents.PRINT_START)

    def test_start_print_lan_resolve_error(self):
        li = MagicMock(LI())
        li.resolve.side_effect = LANResolveError("testing error")
        self.assertEqual(self.s.start_print(li, MagicMock()), False)
        self.s._printer.select_file.assert_not_called()

    def test_start_print_invalid_location(self):
        self.s._printer.select_file.side_effect = InvalidFileLocation()
        self.assertEqual(
            self.s.start_print(LI(True, "a.gcode", LJ("job1")), MagicMock()), False
        )
        self.s._fire_event.assert_not_called()

    def test_start_print_invalid_filetype(self):
        self.s._printer.select_file.side_effect = InvalidFileType()
        self.assertEqual(
            self.s.start_print(LI(True, "a.gcode", LJ("job1")), MagicMock()), False
        )
        self.s._fire_event.assert_not_called()

    def test_start_print_stl_slicing_disabled(self):
        self.s._file_manager.slicing_enabled.return_value = False
        self.assertEqual(
            self.s.start_print(LI(True, "a.stl", LJ("job1")), MagicMock()), False
        )
        self.s._fire_event.assert_not_called()

    def test_start_print_stl_sd(self):
        self.s._file_manager.slicing_enabled.return_value = False
        self.s._file_manager.default_slicer.return_value = "DEFAULT_SLICER"
        self.assertEqual(
            self.s.start_print(LI(True, "a.stl", LJ("job1")), MagicMock()), False
        )
        self.s._fire_event.assert_not_called()

    def test_start_print_stl(self):
        cb = MagicMock()
        self.s._file_manager.slicing_enabled.return_value = True
        self.s._file_manager.default_slicer.return_value = "DEFAULT_SLICER"

        self.assertEqual(self.s.start_print(LI(False, "a.stl", LJ("job1")), cb), None)
        self.s._file_manager.slice.assert_called_with(
            "DEFAULT_SLICER",
            FileDestinations.LOCAL,
            "a.stl",
            FileDestinations.LOCAL,
            "a.gcode",
            callback=ANY,
        )
        self.s._printer.select_file.assert_not_called()

        # Test callbacks
        slice_cb = self.s._file_manager.slice.call_args[1]["callback"]
        slice_cb(_analysis="foo")
        cb.assert_called_with(success=True, error=None)
        self.s._printer.select_file.assert_called_with(
            "a.gcode",
            sd=False,
            printAfterSelect=True,
            user="foo",
        )
        cb.reset_mock()
        self.s._printer.select_file.reset_mock()

        slice_cb(_error="bar")
        cb.assert_called_with(success=False, error="bar")
        self.s._printer.select_file.assert_not_called()
        cb.reset_mock()

        slice_cb(_cancelled=True)
        cb.assert_called_with(success=False, error=ANY)
        self.s._printer.select_file.assert_not_called()
        cb.reset_mock()


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
