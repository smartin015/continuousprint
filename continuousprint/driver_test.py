import unittest
import time
from unittest.mock import MagicMock, ANY
from .driver import Driver, Action as DA, Printer as DP
import logging

logging.basicConfig(level=logging.DEBUG)


class TestFromInactive(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        self.d.action(DA.DEACTIVATE, DP.IDLE)
        item = MagicMock(path="asdf")  # return same item by default every time
        self.d.q.get_set_or_acquire.return_value = item
        self.d.q.get_set.return_value = item

    def test_activate_not_printing(self):
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE)

        self.d.q.begin_run.assert_called()
        self.d._runner.start_print.assert_called_with(self.d.q.get_set.return_value)
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_activate_already_printing(self):
        self.d.action(DA.ACTIVATE, DP.BUSY)
        self.d.action(DA.TICK, DP.BUSY)
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_events_cause_no_action_when_inactive(self):
        def assert_nocalls():
            self.d._runner.run_finish_script.assert_not_called()
            self.d._runner.start_print.assert_not_called()

        for p in [DP.IDLE, DP.BUSY, DP.PAUSED]:
            for a in [DA.SUCCESS, DA.FAILURE, DA.TICK, DA.DEACTIVATE, DA.SPAGHETTI]:
                self.d.action(a, p)
                assert_nocalls()
                self.assertEqual(self.d.state, self.d._state_inactive)

    def test_completed_print_not_in_queue(self):
        self.d.action(DA.ACTIVATE, DP.BUSY)
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
        self.assertEqual(self.d.state, self.d._state_start_clearing)
        self.d._runner.clear_bed.assert_not_called()
        self.d.action(DA.TICK, DP.PAUSED)
        self.assertEqual(self.d.state, self.d._state_start_clearing)
        self.d._runner.clear_bed.assert_not_called()

    def test_retry_after_failure(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries - 2
        self.d.action(DA.TICK, DP.IDLE)  # Start clearing
        self.assertEqual(self.d.retries, self.d.max_retries - 1)
        self.assertEqual(self.d.state, self.d._state_start_clearing)

    def test_activate_clears_retries(self):
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print
        self.assertEqual(self.d.retries, 0)

    def test_failure_with_max_retries_sets_inactive(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.TICK, DP.IDLE)  # -> inactive
        self.assertEqual(self.d.state, self.d._state_inactive)

    def test_resume_from_pause(self):
        self.d.state = self.d._state_paused
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_bed_clearing_failure(self):
        self.d.state = self.d._state_clearing
        self.d.action(DA.FAILURE, DP.IDLE)
        self.assertEqual(self.d.state, self.d._state_inactive)

    def test_finishing_failure(self):
        self.d.state = self.d._state_finishing
        self.d.action(DA.FAILURE, DP.IDLE)
        self.assertEqual(self.d.state, self.d._state_inactive)

    def test_completed_last_print(self):
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print
        self.d.action(DA.TICK, DP.IDLE)  # -> printing
        self.d._runner.start_print.reset_mock()

        self.d.action(
            DA.SUCCESS, DP.IDLE, path=self.d.q.get_set_or_acquire().path
        )  # -> success
        self.d.q.get_set_or_acquire.return_value = None  # Nothing more in the queue
        self.d.action(DA.TICK, DP.IDLE)  # -> start_finishing
        self.d.action(DA.TICK, DP.IDLE)  # -> finishing
        self.d._runner.run_finish_script.assert_called()
        self.assertEqual(self.d.state, self.d._state_finishing)

        self.d.action(DA.TICK, DP.IDLE)  # -> inactive
        self.assertEqual(self.d.state, self.d._state_inactive)


class TestFromStartPrint(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        item = MagicMock(path="asdf")  # return same item by default every time
        self.d.q.get_set_or_acquire.return_value = item
        self.d.q.get_set.return_value = item
        self.d.action(DA.DEACTIVATE, DP.IDLE)
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print

    def test_success(self):
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print
        self.d.action(DA.TICK, DP.IDLE)  # -> printing
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
        self.d._runner.clear_bed.assert_called_once()

        self.d.action(DA.SUCCESS, DP.IDLE)  # -> start_print
        self.d.action(DA.TICK, DP.IDLE)  # -> printing
        self.d._runner.start_print.assert_called_with(item2)

    def test_paused_with_spaghetti_early_triggers_cancel(self):
        self.d.action(DA.TICK, DP.IDLE)  # -> printing

        self.d.q.get_run.return_value = MagicMock(started=time.time() - 10)
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> spaghetti_recovery
        self.d.action(DA.TICK, DP.PAUSED)  # -> cancel + failure
        self.d._runner.cancel_print.assert_called()
        self.assertEqual(self.d.state, self.d._state_failure)

    def test_paused_with_spaghetti_late_waits_for_user(self):
        self.d.action(DA.TICK, DP.IDLE)  # -> printing

        self.d.q.get_run.return_value = MagicMock(
            started=time.time() - self.d.retry_threshold_seconds - 1
        )
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> printing (ignore spaghetti)
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_paused)

    def test_paused_manually_early_waits_for_user(self):
        self.d.action(DA.TICK, DP.IDLE)  # -> printing

        self.d.q.get_run.return_value = MagicMock(
            started=time.time() - self.d.retry_threshold_seconds - 10
        )
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d.action(DA.TICK, DP.PAUSED)  # stay in paused state
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_paused)

    def test_paused_manually_late_waits_for_user(self):
        self.d.action(DA.TICK, DP.IDLE)  # -> printing

        self.d.q.get_run.return_value = MagicMock(started=time.time() - 1000)
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d.action(DA.TICK, DP.PAUSED)  # stay in paused state
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_paused)

    def test_paused_on_temp_file_falls_through(self):
        self.d.state = self.d._state_clearing  # -> clearing
        self.d.action(DA.TICK, DP.PAUSED)
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_clearing)

        self.d.state = self.d._state_finishing  # -> finishing
        self.d.action(DA.TICK, DP.PAUSED)
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_finishing)

    def test_user_deactivate_sets_inactive(self):
        self.d.action(DA.TICK, DP.IDLE)  # -> printing
        self.d._runner.start_print.reset_mock()

        self.d.action(DA.DEACTIVATE, DP.IDLE)  # -> inactive
        self.assertEqual(self.d.state, self.d._state_inactive)
        self.d._runner.start_print.assert_not_called()
        self.d.q.end_run.assert_not_called()


class TestMaterialConstraints(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        self.d.action(DA.DEACTIVATE, DP.IDLE)

    def _setItemMaterials(self, m):
        item = MagicMock()
        item.materials.return_value = m
        self.d.q.get_set.return_value = item
        self.d.q.get_set_or_acquire.return_value = item

    def test_empty(self):
        self._setItemMaterials([])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_none(self):
        self._setItemMaterials([None])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_tool1mat_none(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE)
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_start_print)

    def test_tool1mat_wrong(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE, materials=["tool0bad"])
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_start_print)

    def test_tool1mat_ok(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE, materials=["tool1mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_tool2mat_ok(self):
        self._setItemMaterials([None, "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE, materials=[None, "tool2mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_tool1mat_tool2mat_ok(self):
        self._setItemMaterials(["tool1mat", "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE, materials=["tool1mat", "tool2mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state, self.d._state_printing)

    def test_tool1mat_tool2mat_reversed(self):
        self._setItemMaterials(["tool1mat", "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE, materials=["tool2mat", "tool1mat"])
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_start_print)


if __name__ == "__main__":
    unittest.main()
