import unittest
import logging
from unittest.mock import MagicMock
from .abstract import Strategy
from .multi import MultiQueue

# logging.basicConfig(level=logging.DEBUG)


class TestMultiQueue(unittest.TestCase):
    def setUp(self):
        def onupdate():
            pass

        self.q = MultiQueue(MagicMock(), Strategy.IN_ORDER, onupdate)

    def test_begin_run(self):
        self.q.active_queue = MagicMock()
        self.q.begin_run()
        self.q.queries.beginRun.assert_called()

    def test_begin_run_not_acquired(self):
        self.assertEqual(self.q.begin_run(), None)
        self.q.queries.beginRun.assert_not_called()

    def test_end_run_not_acquired(self):
        self.assertEqual(self.q.end_run("result"), None)
        self.q.queries.endRun.assert_not_called()

    def test_end_run_no_begin(self):
        self.q.end_run("result")
        self.q.queries.endRun.assert_not_called()

    def test_end_run_different_next(self):
        self.q.run = 4
        self.q.active_queue = MagicMock()
        self.q.end_run("result")
        self.q.queries.endRun.assert_called()
        self.q.active_queue.decrement.assert_called()

    def test_end_run_same_next(self):
        self.q.run = 4
        self.q.active_queue = MagicMock()
        self.q.queries.getNextJobInQueue.return_value = self.q.job
        self.q.end_run("result")
        self.q.queries.endRun.assert_called()
        self.q.queries.release.assert_not_called()
