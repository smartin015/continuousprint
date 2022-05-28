import unittest
import logging
from unittest.mock import MagicMock
from .abstract import Strategy, QueueData
from .local import LocalQueue
from dataclasses import dataclass, asdict

# logging.basicConfig(level=logging.DEBUG)


class TestLocalQueueInOrderNoInitialJob(unittest.TestCase):
    def setUp(self):
        queries = MagicMock()
        queries.getAcquiredJob.return_value = None
        self.q = LocalQueue(
            queries, "testQueue", Strategy.IN_ORDER, dict(name="profile"), MagicMock()
        )

    def test_acquire_success(self):
        j = MagicMock()
        s = MagicMock()
        j.next_set.return_value = s
        self.q.queries.getNextJobInQueue.return_value = j
        self.q.queries.acquireJob.return_value = True
        self.assertEqual(self.q.acquire(), True)
        self.assertEqual(self.q.get_job(), j)
        self.assertEqual(self.q.get_set(), s)

    def test_acquire_failed(self):
        self.q.queries.getNextJobInQueue.return_value = "doesntmatter"
        self.q.queries.acquireJob.return_value = False
        self.assertEqual(self.q.acquire(), False)
        self.assertEqual(self.q.get_job(), None)

    def test_acquire_failed_no_jobs(self):
        self.q.queries.getNextJobInQueue.return_value = None
        self.assertEqual(self.q.acquire(), False)

    def test_as_dict(self):
        self.assertEqual(
            self.q.as_dict(),
            dict(
                name="testQueue",
                strategy="IN_ORDER",
                jobs=[],
                active_set=None,
                addr=None,
                peers=[],
            ),
        )


class TestLocalQueueInOrderInitial(unittest.TestCase):
    def setUp(self):
        queries = MagicMock(name="queries")
        self.j = MagicMock(name="j")
        self.s = MagicMock(name="s")
        self.ns = MagicMock(name="ns")
        self.j.next_set.side_effect = [self.s, self.ns]
        queries.getAcquiredJob.return_value = self.j
        self.q = LocalQueue(
            queries, "testQueue", Strategy.IN_ORDER, dict(name="profile"), MagicMock()
        )

    def test_init_already_acquired(self):
        self.assertEqual(self.q.get_job(), self.j)
        self.assertEqual(self.q.get_set(), self.s)

    def test_acquire_2x(self):
        # Second acquire should do nothing, return True
        self.q.queries.getNextJobInQueue.return_value = None
        self.assertEqual(self.q.acquire(), True)
        self.q.queries.acquireJob.assert_not_called()
        self.assertEqual(self.q.get_job(), self.j)
        self.assertEqual(self.q.get_set(), self.s)

    def test_release(self):
        self.q.release()
        self.q.queries.releaseJob.assert_called_with(self.j)
        self.assertEqual([self.q.get_job(), self.q.get_set()], [None, None])

    def test_decrement_more_work(self):
        self.s.decrement.return_value = True
        self.q.decrement()
        self.s.decrement.assert_called()
        self.assertEqual(self.q.get_set(), self.ns)

    def test_decrement_no_more_work(self):
        self.s.decrement.return_value = False
        self.q.decrement()
        self.q.queries.releaseJob.assert_called_with(self.j)
        self.assertEqual(self.q.get_set(), None)
        self.assertEqual(self.q.get_job(), None)

    def as_dict(self):
        self.q.queries.begin_run.return_value = 4
        self.q.queries.getJobsAndSets.return_value = []
        self.q.set = MagicMock(id=2)
        self.assertDictEqual(
            self.q.as_dict(),
            asdict(
                QueueData(name="testQueue", strategy="IN_ORDER", jobs=[], active_set=2)
            ),
        )
