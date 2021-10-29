import unittest
from unittest.mock import MagicMock
from print_queue import PrintQueue, QueueItem
from driver import ContinuousPrintDriver
from mock_settings import MockSettings
import logging
logging.basicConfig(level=logging.DEBUG)

def setupTestQueueAndDriver(self, num_complete):
    self.s = MockSettings("q")
    self.q = PrintQueue(self.s, "q")
    self.q.assign([
            QueueItem("foo", "/foo.gcode", True, end_ts = 1 if num_complete > 0 else None),
            QueueItem("bar", "/bar.gco", True, end_ts = 2 if num_complete > 1 else None),
            QueueItem("baz", "/baz.gco", True, end_ts = 3 if num_complete > 2 else None),
        ])
    self.d = ContinuousPrintDriver(
            queue = self.q,
            finish_script_fn = MagicMock(),
            start_print_fn = MagicMock(),
            cancel_print_fn = MagicMock(),
            logger = logging.getLogger())

def flush(d):
    while d.pending_actions() > 0:
        d.on_printer_ready()


class TestQueueManagerFromInitialState(unittest.TestCase):
    def setUp(self):
        setupTestQueueAndDriver(self, 0)

    def test_activate_not_printing(self):
        self.d.set_active()
        flush(self.d)
        self.d.start_print_fn.assert_called_once()
        self.assertEqual(self.d.start_print_fn.call_args[0][0], self.q[0])

    def test_activate_already_printing(self):
        self.d.set_active(printer_ready=False)
        self.d.start_print_fn.assert_not_called()

    def test_events_cause_no_action_when_inactive(self):
        def assert_nocalls():
            self.d.finish_script_fn.assert_not_called()
            self.d.start_print_fn.assert_not_called()
        self.d.on_print_success()
        assert_nocalls()
        self.d.on_print_failed()
        assert_nocalls()
        self.d.on_print_cancelled()
        assert_nocalls()
        self.d.on_print_paused(0)
        assert_nocalls()

    def test_completed_print_not_in_queue(self):
        self.d.set_active(printer_ready=False)
        self.d.on_print_success()
        flush(self.d)

        # Non-queue print completion while the driver is active
        # should kick off a new print from the head of the queue
        self.d.start_print_fn.assert_called_once()
        self.assertEqual(self.d.start_print_fn.call_args[0][0], self.q[0])

    def test_completed_first_print(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()

        self.d.on_print_success()
        flush(self.d)

        self.d.start_print_fn.assert_called_once()
        self.assertEqual(self.d.start_print_fn.call_args[0][0], self.q[1])


class TestQueueManagerPartiallyComplete(unittest.TestCase):
    def setUp(self):
        setupTestQueueAndDriver(self, 1)

    def test_success(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()

        self.d.on_print_success()
        flush(self.d)
        self.d.start_print_fn.assert_called_once()
        self.assertEqual(self.d.start_print_fn.call_args[0][0], self.q[2])

    def test_success_after_queue_prepend_starts_prepended(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()
        n = QueueItem("new", "/new.gco", True)
        self.q.add([n], idx=0)

        self.d.on_print_success()
        flush(self.d)
        self.d.start_print_fn.assert_called_once
        self.assertEqual(self.d.start_print_fn.call_args[0][0], n)


    def test_paused_early_triggers_cancel(self):
        self.d.set_active()

        self.d.on_print_paused(self.d.RETRY_THRESHOLD_SECONDS - 1)
        flush(self.d)
        self.d.cancel_print_fn.assert_called_once_with()

    def test_cancelled_triggers_retry(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()

        self.d.on_print_cancelled()
        flush(self.d)
        self.d.start_print_fn.assert_called_once()
        self.assertEqual(self.d.start_print_fn.call_args[0][0], self.q[1])
        self.assertEqual(self.d.retries, 1)

    def test_set_active_clears_retries(self):
        self.d.retries = self.d.MAX_RETRIES-1
        self.d.set_active()
        self.assertEqual(self.d.retries, 0)

    def test_cancelled_with_max_retries_sets_inactive(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()
        self.d.retries = self.d.MAX_RETRIES

        self.d.on_print_cancelled()
        flush(self.d)
        self.d.start_print_fn.assert_not_called()
        self.assertEqual(self.d.active, False)

    def test_paused_late_waits_for_user(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()

        self.d.on_print_paused(self.d.RETRY_THRESHOLD_SECONDS + 1)
        self.d.start_print_fn.assert_not_called()

    def test_failure_sets_inactive(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()

        self.d.on_print_failed()
        flush(self.d)
        self.d.start_print_fn.assert_not_called()
        self.assertEqual(self.d.active, False)


class TestQueueManagerOnLastPrint(unittest.TestCase):
    def setUp(self):
        setupTestQueueAndDriver(self, 2)

    def test_completed_last_print(self):
        self.d.set_active()
        self.d.start_print_fn.reset_mock()

        self.d.on_print_success()
        flush(self.d)
        self.d.finish_script_fn.assert_called_once_with()
        self.assertEqual(self.d.active, False)


if __name__ == "__main__":
    unittest.main()
