import unittest
from unittest.mock import MagicMock
from print_queue import PrintQueue, QueueItem
from driver import ContinuousPrintDriver, Action as DA, Printer as DP
from mock_settings import MockSettings
import logging

logging.basicConfig(level=logging.DEBUG)


class Runner():
  def __init__(self):
    self.run_finish_script = MagicMock()
    self.start_print = MagicMock()
    self.cancel_print = MagicMock()
    self.clear_bed = MagicMock()
  


def setupTestQueueAndDriver(self, num_complete=0):
    self.s = MockSettings("q")
    self.q = PrintQueue(self.s, "q")
    self.q.assign(
        [
            QueueItem(
                "foo",
                "/foo.gcode",
                True,
                end_ts=1 if num_complete > 0 else None,
            ),
            QueueItem("bar", "/bar.gco", True, end_ts=2 if num_complete > 1 else None),
            QueueItem("baz", "/baz.gco", True, end_ts=3 if num_complete > 2 else None),
        ]
    )
    self.d = ContinuousPrintDriver(
        queue=self.q,
        script_runner=Runner(),
        logger=logging.getLogger(),
    )
    self.d.set_retry_on_pause(True)
    self.d.action(DA.DEACTIVATE, DP.IDLE)


class TestFromInitialState(unittest.TestCase):
    def setUp(self):
        setupTestQueueAndDriver(self, 0)

    def test_activate_not_printing(self):
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d.action(DA.TICK, DP.IDLE)
        self.d._runner.start_print.assert_called_once()
        self.assertEqual(self.d._runner.start_print.call_args[0][0], self.q[0])
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
        self.d.action(DA.SUCCESS, DP.IDLE, "otherprint.gcode") # -> success
        self.d.action(DA.TICK, DP.IDLE) # -> start_clearing

        self.assertEqual(self.q[0].end_ts, None) # Queue item not completed since print not in queue
        self.assertEqual(self.q[0].result, None)

        self.d.action(DA.TICK, DP.IDLE) # -> clearing
        self.d.action(DA.SUCCESS, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing

        # Non-queue print completion while the driver is active
        # should kick off a new print from the head of the queue
        self.d._runner.start_print.assert_called_once()
        self.assertEqual(self.d._runner.start_print.call_args[0][0], self.q[0])
      
    def test_completed_first_print(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.reset_mock()

        self.d._intent = self.q[0].path
        self.d._cur_path = self.d._intent

        self.d.action(DA.SUCCESS, DP.IDLE, self.d._intent) # -> success
        self.d.action(DA.TICK, DP.IDLE) # -> start_clearing
        self.d.action(DA.TICK, DP.IDLE) # -> clearing
        self.d._runner.clear_bed.assert_called_once()
        
        self.d.action(DA.SUCCESS, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.assert_called_once()
        self.assertEqual(self.d._runner.start_print.call_args[0][0], self.q[1])

    def test_start_clearing_waits_for_idle(self):
        self.d.state = self.d._state_start_clearing
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state, self.d._state_start_clearing)
        self.d._runner.clear_bed.assert_not_called()
        self.d.action(DA.TICK, DP.PAUSED)
        self.assertEqual(self.d.state, self.d._state_start_clearing)
        self.d._runner.clear_bed.assert_not_called()

class TestPartiallyComplete(unittest.TestCase):
    def setUp(self):
        setupTestQueueAndDriver(self, 1)

    def test_success(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.reset_mock()

        self.d._intent = self.q[1].path
        self.d._cur_path = self.d._intent

        self.d.action(DA.SUCCESS, DP.IDLE) # -> success
        self.d.action(DA.TICK, DP.IDLE) # -> start_clearing
        self.d.action(DA.TICK, DP.IDLE) # -> clearing
        self.d.action(DA.TICK, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.assert_called_once()
        self.assertEqual(self.d._runner.start_print.call_args[0][0], self.q[2])

    def test_success_after_queue_prepend_starts_prepended(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.reset_mock()
        n = QueueItem("new", "/new.gco", True)
        self.q.add([n], idx=0)

        self.d._intent = self.q[1].path
        self.d._cur_path = self.d._intent

        self.d.action(DA.SUCCESS, DP.IDLE) # -> success
        self.d.action(DA.TICK, DP.IDLE) # -> start_clearing
        self.d.action(DA.TICK, DP.IDLE) # -> clearing
        self.d.action(DA.TICK, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.assert_called_once
        self.assertEqual(self.d._runner.start_print.call_args[0][0], n)

    def test_paused_with_spaghetti_early_triggers_cancel(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing

        self.d._elapsed = lambda: 10
        self.d.action(DA.SPAGHETTI, DP.BUSY) # -> spaghetti_recovery
        self.d.action(DA.TICK, DP.PAUSED) # -> cancel + failure
        self.d._runner.cancel_print.assert_called()
        self.assertEqual(self.d.state, self.d._state_failure)

    def test_paused_with_spaghetti_late_waits_for_user(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing

        self.d._elapsed = lambda: self.d.retry_threshold_seconds + 1
        self.d.action(DA.SPAGHETTI, DP.BUSY) # -> printing (ignore spaghetti)
        self.d.action(DA.TICK, DP.PAUSED) # -> paused
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_paused)

    def test_paused_manually_early_waits_for_user(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing

        self.d._elapsed = lambda: 10
        self.d.action(DA.TICK, DP.PAUSED) # -> paused
        self.d.action(DA.TICK, DP.PAUSED) # stay in paused state
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_paused)

    def test_paused_manually_late_waits_for_user(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing

        self.d._elapsed = lambda: 1000
        self.d.action(DA.TICK, DP.PAUSED) # -> paused
        self.d.action(DA.TICK, DP.PAUSED) # stay in paused state
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_paused)

    def test_paused_on_temp_file_falls_through(self):
        self.d.state = self.d._state_clearing # -> clearing
        self.d.action(DA.TICK, DP.PAUSED)
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_clearing)

        self.d.state = self.d._state_finishing # -> finishing
        self.d.action(DA.TICK, DP.PAUSED) 
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state, self.d._state_finishing)

    def test_user_deactivate_sets_inactive(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.reset_mock()

        self.d.action(DA.DEACTIVATE, DP.IDLE) # -> inactive
        self.assertEqual(self.d.state, self.d._state_inactive)
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.q[1].result, None)

    def test_retry_after_failure(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries-2
        self.d.action(DA.TICK, DP.IDLE) # Start clearing
        self.assertEqual(self.d.retries, self.d.max_retries-1)
        self.assertEqual(self.d.state, self.d._state_start_clearing)

    def test_activate_clears_retries(self):
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.assertEqual(self.d.retries, 0)

    def test_failure_with_max_retries_sets_inactive(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.TICK, DP.IDLE) # -> inactive
        self.assertEqual(self.d.state, self.d._state_inactive)

    def test_resume_from_pause(self):
        self.d.state = self.d._state_paused
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state, self.d._state_printing)


class TestOnLastPrint(unittest.TestCase):
    def setUp(self):
        setupTestQueueAndDriver(self, 2)

    def test_completed_last_print(self):
        self.d.action(DA.ACTIVATE, DP.IDLE) # -> start_print
        self.d.action(DA.TICK, DP.IDLE) # -> printing
        self.d._runner.start_print.reset_mock()

        self.d._intent = self.q[-1].path
        self.d._cur_path = self.d._intent

        self.d.action(DA.SUCCESS, DP.IDLE, self.d._intent) # -> success
        self.d.action(DA.TICK, DP.IDLE) # -> start_finishing
        self.d.action(DA.TICK, DP.IDLE) # -> finishing
        self.d._runner.run_finish_script.assert_called()
        self.assertEqual(self.d.state, self.d._state_finishing)
        
        self.d.action(DA.TICK, DP.IDLE) # -> inactive
        self.assertEqual(self.d.state, self.d._state_inactive)
          
class TestMaterialConstraints(unittest.TestCase):
    def setUp(self):
        setupTestQueueAndDriver(self)

    def _setItemMaterials(self, m):
        self.q.assign([
              QueueItem("foo", "/foo.gcode", True, materials=m)
          ])
    
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

    def test_tool1mat_ok(self):
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
