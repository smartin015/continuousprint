import unittest
import datetime
import time
from unittest.mock import MagicMock, ANY
from .driver import Driver, Action as DA, Printer as DP
from .data import CustomEvents
import logging
import traceback

# logging.basicConfig(level=logging.DEBUG)


class TestFromInactive(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d._runner.verify_active.return_value = (True, None)
        self.d.set_retry_on_pause(True)
        self.d.action(DA.DEACTIVATE, DP.IDLE)
        self.d._runner.run_script_for_event.reset_mock()
        item = MagicMock(path="asdf")  # return same item by default every time
        self.d.q.get_set_or_acquire.return_value = item
        self.d.q.get_set.return_value = item

    def test_activate_with_startup_script(self):
        self.d._runner.run_script_for_event.side_effect = ["foo.gcode", None]
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> activating
        self.d.q.begin_run.assert_not_called()
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_activating.__name__)
        self.d._runner.run_script_for_event.assert_called_with(CustomEvents.ACTIVATE)
        # Stays in activating while script is running
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state.__name__, self.d._state_activating.__name__)

        # Exits to start printing when script completes
        self.d.action(DA.SUCCESS, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)
        self.d._runner.start_print.assert_called()

    def test_activate_with_preprint_script(self):
        # First call is ACTIVATE, second call is PRINT_START
        self.d._runner.run_script_for_event.side_effect = [None, "foo.gcode", None]
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> preprint
        self.d.q.begin_run.assert_not_called()
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_preprint.__name__)
        self.d._runner.run_script_for_event.assert_called_with(CustomEvents.PRINT_START)
        # Stays in preprint while script is runnig
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state.__name__, self.d._state_preprint.__name__)

        # Exits to start printing when script completes
        self.d.action(DA.SUCCESS, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)
        self.d._runner.start_print.assert_called()

    def test_activate_not_yet_printing(self):
        self.d._runner.run_script_for_event.return_value = None
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_printing -> printing
        self.d.q.begin_run.assert_called()
        self.d._runner.start_print.assert_called_with(self.d.q.get_set.return_value)
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)
        self.d._runner.run_script_for_event.assert_called_with(CustomEvents.PRINT_START)

    def test_activate_already_printing(self):
        self.d._runner.run_script_for_event.return_value = None
        self.d.action(DA.ACTIVATE, DP.BUSY)
        self.d.action(DA.TICK, DP.BUSY)
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)
        self.d._runner.run_script_for_event.assert_called_with(CustomEvents.ACTIVATE)

    def test_events_cause_no_action_when_inactive(self):
        def assert_nocalls():
            self.d._runner.run_script_for_event.assert_not_called()
            self.d._runner.start_print.assert_not_called()

        for p in [DP.IDLE, DP.BUSY, DP.PAUSED]:
            for a in [DA.SUCCESS, DA.FAILURE, DA.TICK, DA.DEACTIVATE, DA.SPAGHETTI]:
                self.d._runner.run_script_for_event.reset_mock()
                self.d.action(a, p)
                assert_nocalls()
                self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_completed_print_not_in_queue(self):
        self.d._runner.run_script_for_event.return_value = None
        self.d.action(DA.ACTIVATE, DP.BUSY)  # -> start print -> printing
        self.d.action(DA.SUCCESS, DP.IDLE, "otherprint.gcode")  # -> success
        self.d.action(DA.TICK, DP.IDLE)  # -> start_clearing

        self.d.action(DA.TICK, DP.IDLE)  # -> clearing
        self.d.action(DA.SUCCESS, DP.IDLE)  # -> start_print
        self.d.action(DA.TICK, DP.IDLE)  # -> printing

        # Non-queue print completion while the driver is active
        # should kick off a new print from the head of the queue
        self.d._runner.start_print.assert_called_with(self.d.q.get_set.return_value)
        self.d.q.begin_run.assert_called_once()

        # Verify no end_run call anywhere in this process, since print was not in queue
        self.d.q.end_run.assert_not_called()

    def test_start_clearing_waits_for_idle(self):
        self.d.state = self.d._state_start_clearing
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)
        self.d._runner.run_script_for_event.assert_not_called()
        self.d.action(DA.TICK, DP.PAUSED)
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)
        self.d._runner.run_script_for_event.assert_not_called()

    def test_idle_while_printing(self):
        self.d.state = self.d._state_printing
        # First idle tick does nothing
        self.d.action(DA.TICK, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

        # Continued idleness triggers bed clearing and such
        self.d.printer_state_ts = time.time() - (Driver.PRINTING_IDLE_BREAKOUT_SEC + 1)
        self.d.action(DA.TICK, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)

    def test_retry_after_failure(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries - 2
        self.d.action(DA.TICK, DP.IDLE)  # Start clearing
        self.assertEqual(self.d.retries, self.d.max_retries - 1)
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)

    def test_activate_clears_retries(self):
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print
        self.assertEqual(self.d.retries, 0)

    def test_failure_with_max_retries_sets_inactive(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.TICK, DP.IDLE)  # -> inactive
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_resume_from_pause(self):
        self.d.state = self.d._state_paused
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_bed_clearing_failure(self):
        self.d.state = self.d._state_clearing
        self.d.action(DA.FAILURE, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_bed_clearing_cooldown_threshold(self):
        self.d.set_managed_cooldown(True, 20, 60)
        self.d.state = self.d._state_start_clearing
        self.d.action(DA.TICK, DP.IDLE, bed_temp=21)
        self.assertEqual(self.d.state.__name__, self.d._state_cooldown.__name__)
        self.d._runner.run_script_for_event.reset_mock()
        self.d.action(
            DA.TICK, DP.IDLE, bed_temp=21
        )  # -> stays in cooldown since bed temp too high
        self.assertEqual(self.d.state.__name__, self.d._state_cooldown.__name__)
        self.d._runner.run_script_for_event.assert_not_called()
        self.d.action(DA.TICK, DP.IDLE, bed_temp=19)  # -> exits cooldown
        self.assertEqual(self.d.state.__name__, self.d._state_clearing.__name__)
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.PRINT_SUCCESS
        )

    def test_bed_clearing_cooldown_timeout(self):
        self.d.set_managed_cooldown(True, 20, 60)
        self.d.state = self.d._state_start_clearing
        self.d.action(DA.TICK, DP.IDLE, bed_temp=21)
        self.assertEqual(self.d.state.__name__, self.d._state_cooldown.__name__)
        orig_start = self.d.cooldown_start
        self.d.cooldown_start = orig_start - 60 * 59  # Still within timeout range

        self.d._runner.run_script_for_event.reset_mock()
        self.d.action(DA.TICK, DP.IDLE, bed_temp=21)
        self.assertEqual(self.d.state.__name__, self.d._state_cooldown.__name__)
        self.d.cooldown_start = orig_start - 60 * 61
        self.d._runner.run_script_for_event.assert_not_called()
        self.d.action(DA.TICK, DP.IDLE, bed_temp=21)  # exit due to timeout
        self.assertEqual(self.d.state.__name__, self.d._state_clearing.__name__)
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.PRINT_SUCCESS
        )

    def test_finishing_failure(self):
        self.d.state = self.d._state_finishing
        self.d.action(DA.FAILURE, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_completed_last_print(self):
        self.d._runner.run_script_for_event.return_value = None
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.d._runner.start_print.reset_mock()

        self.d.action(
            DA.SUCCESS, DP.IDLE, path=self.d.q.get_set_or_acquire().path
        )  # -> success
        self.d.q.get_set_or_acquire.return_value = None  # Nothing more in the queue
        self.d.action(DA.TICK, DP.IDLE)  # -> start_finishing
        self.d.printer_state_ts = time.time() - (Driver.PRINTING_IDLE_BREAKOUT_SEC + 1)
        self.d.action(DA.TICK, DP.IDLE)  # -> finishing
        self.d._runner.run_script_for_event.assert_called_with(CustomEvents.FINISH)
        self.assertEqual(self.d.state.__name__, self.d._state_finishing.__name__)

        self.d.action(DA.TICK, DP.IDLE)  # -> idle
        self.assertEqual(self.d.state.__name__, self.d._state_idle.__name__)


class TestFromStartPrint(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d._runner.verify_active.return_value = (True, None)
        self.d.set_retry_on_pause(True)
        item = MagicMock(path="asdf")  # return same item by default every time
        self.d.q.get_set_or_acquire.return_value = item
        self.d.q.get_set.return_value = item
        self.d._runner.run_script_for_event.return_value = None
        self.d.action(DA.DEACTIVATE, DP.IDLE)
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.d._runner.run_script_for_event.reset_mock()

    def test_success(self):
        # Note: also implicitly tests when timelapse is disabled
        self.d._runner.start_print.reset_mock()

        self.d.action(
            DA.SUCCESS, DP.IDLE, path=self.d.q.get_set.return_value.path
        )  # -> success
        self.d.action(DA.TICK, DP.IDLE)  # -> start_clearing
        self.d.q.end_run.assert_called_once()
        item2 = MagicMock(path="basdf")
        self.d.q.get_set_or_acquire.return_value = (
            item2  # manually move the supervisor forward in the queue
        )
        self.d.q.get_set.return_value = item2

        self.d.action(DA.TICK, DP.IDLE)  # -> clearing
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.PRINT_SUCCESS
        )

        self.d.action(DA.SUCCESS, DP.IDLE)  # -> start_print -> printing
        self.d._runner.start_print.assert_called_with(item2)

    def test_success_waits_for_timelapse(self):
        now = time.time()
        self.d.action(
            DA.SUCCESS,
            DP.IDLE,
            path=self.d.q.get_set.return_value.path,
            timelapse_start_ts=now,
        )  # -> success, but wait for timelapse
        self.d.action(DA.TICK, DP.IDLE, timelapse_start_ts=now)  # -> still success
        self.assertEqual(self.d.state.__name__, self.d._state_success.__name__)

        item2 = MagicMock(path="basdf")
        self.d.q.get_set_or_acquire.return_value = (
            item2  # manually move the supervisor forward in the queue
        )
        self.d.q.get_set.return_value = item2

        self.d.action(DA.TICK, DP.IDLE)  # -> clearing
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)

    def test_success_timelapse_timeout(self):
        now = time.time()
        self.d.action(
            DA.SUCCESS,
            DP.IDLE,
            path=self.d.q.get_set.return_value.path,
            timelapse_start_ts=now - self.d.TIMELAPSE_WAIT_SEC - 1,
        )  # -> success, but wait for timelapse
        self.d.action(
            DA.TICK, DP.IDLE, timelapse_start_ts=now - self.d.TIMELAPSE_WAIT_SEC - 1
        )  # -> timeout to clearing
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)

    def test_paused_with_spaghetti_early_triggers_cancel(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now() - datetime.timedelta(seconds=10)
        )
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> spaghetti_recovery
        self.d.action(DA.TICK, DP.PAUSED)  # -> cancel + failure
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.PRINT_CANCEL
        )
        self.assertEqual(self.d.state.__name__, self.d._state_failure.__name__)

    def test_paused_with_spaghetti_late_waits_for_user(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now()
            - datetime.timedelta(seconds=self.d.retry_threshold_seconds + 1)
        )
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> printing (ignore spaghetti)
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d._runner.run_script_for_event.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_paused.__name__)

    def test_paused_manually_early_waits_for_user(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now() - datetime.timedelta(seconds=10)
        )
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d.action(DA.TICK, DP.PAUSED)  # stay in paused state
        self.d._runner.run_script_for_event.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_paused.__name__)

    def test_paused_manually_late_waits_for_user(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now() - datetime.timedelta(seconds=1000)
        )
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d.action(DA.TICK, DP.PAUSED)  # stay in paused state
        self.d._runner.run_script_for_event.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_paused.__name__)

    def test_paused_on_temp_file_falls_through(self):
        self.d.state = self.d._state_clearing  # -> clearing
        self.d.action(DA.TICK, DP.PAUSED)
        self.d._runner.run_script_for_event.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_clearing.__name__)

        self.d.state = self.d._state_finishing  # -> finishing
        self.d.action(DA.TICK, DP.PAUSED)
        self.d._runner.run_script_for_event.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_finishing.__name__)

    def test_user_deactivate_sets_inactive(self):
        self.d._runner.start_print.reset_mock()

        self.d.action(DA.DEACTIVATE, DP.IDLE)  # -> inactive
        self.d._runner.run_script_for_event.assert_called
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)
        self.d._runner.start_print.assert_not_called()
        self.d._runner.run_script_for_event.assert_called_with(CustomEvents.DEACTIVATE)
        self.d.q.end_run.assert_not_called()


class MaterialTest(unittest.TestCase):
    """Test harness for testing material & spool checking"""

    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        self.d._runner.run_script_for_event.return_value = None
        self.d.action(DA.DEACTIVATE, DP.IDLE)

    def _setItemMaterials(self, m):
        item = MagicMock()
        item.materials.return_value = m
        self.d.q.get_set.return_value = item
        self.d.q.get_set_or_acquire.return_value = item


class TestSpoolVerification(MaterialTest):
    def testNotOK(self):
        self._setItemMaterials(["tool1mat"])
        for retval, expr in (
            (
                dict(
                    misconfig=True,
                    nospool=[],
                    notenough=[],
                ),
                "missing metadata",
            ),
            (
                dict(
                    misconfig=False,
                    nospool=[1, 2, 3],
                    notenough=[],
                ),
                "do not have a spool",
            ),
            (
                dict(
                    misconfig=False,
                    nospool=[],
                    notenough=[dict(toolIndex=0, spoolName="spool")],
                ),
                "not enough filament",
            ),
        ):
            with self.subTest(retval=retval, expr=expr):
                self.d._runner.verify_active.return_value = (False, retval)
                self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool1mat"])
                self.d._runner.start_print.assert_not_called()
                self.assertEqual(
                    self.d.state.__name__, self.d._state_awaiting_material.__name__
                )
                self.assertRegex(self.d.status, expr)

    def testOK(self):
        self._setItemMaterials(["tool1mat"])
        self.d._runner.verify_active.return_value = (True, {})
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool1mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)


class TestMaterialConstraints(MaterialTest):
    def setUp(self):
        super().setUp()
        self.d._runner.verify_active.return_value = (True, None)  # No spoolmanager

    def _setItemMaterials(self, m):
        item = MagicMock()
        item.materials.return_value = m
        self.d.q.get_set.return_value = item
        self.d.q.get_set_or_acquire.return_value = item

    def test_empty(self):
        self._setItemMaterials([])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_none(self):
        self._setItemMaterials([None])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool1mat_none(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_not_called()
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.AWAITING_MATERIAL
        )
        self.assertEqual(
            self.d.state.__name__, self.d._state_awaiting_material.__name__
        )

    def test_tool1mat_wrong(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool0bad"])
        self.d._runner.start_print.assert_not_called()
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.AWAITING_MATERIAL
        )
        self.assertEqual(
            self.d.state.__name__, self.d._state_awaiting_material.__name__
        )

    def test_tool1mat_ok(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool1mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool2mat_ok(self):
        self._setItemMaterials([None, "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=[None, "tool2mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool1mat_tool2mat_ok(self):
        self._setItemMaterials(["tool1mat", "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool1mat", "tool2mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool1mat_tool2mat_reversed(self):
        self._setItemMaterials(["tool1mat", "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool2mat", "tool1mat"])
        self.d._runner.start_print.assert_not_called()
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.AWAITING_MATERIAL
        )
        self.assertEqual(
            self.d.state.__name__, self.d._state_awaiting_material.__name__
        )

    def test_recovery(self):
        self._setItemMaterials(["tool0mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool0bad"])
        self.assertEqual(
            self.d.state.__name__, self.d._state_awaiting_material.__name__
        )

        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool0mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)
