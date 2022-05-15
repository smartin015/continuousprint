import unittest
import logging
from unittest.mock import MagicMock
from .queues import AbstractQueue, LocalQueue, LANQueue, MultiQueue, Strategy, QueueData
from .storage.database import Job, Set, Run
from dataclasses import dataclass

logging.basicConfig(level=logging.DEBUG)


class TestLocalQueueInOrderNoInitialJob(unittest.TestCase):
    def setUp(self):
        queries = MagicMock()
        queries.getAcquired.return_value = (None, None, None)
        self.q = LocalQueue(queries, "testQueue", Strategy.IN_ORDER)

    def test_acquire_success(self):
        self.q.queries.getNextJobInQueue.return_value = "testjob"
        self.q.queries.acquireJob.return_value = True
        self.q.queries.getAcquired.return_value = (1, 2, 3)
        self.assertEqual(self.q.acquire(), True)
        self.assertEqual(self.q.get_job(), 1)
        self.assertEqual(self.q.get_set(), 2)

    def test_acquire_failed(self):
        self.q.queries.getNextJobInQueue.return_value = "testjob"
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
        queries = MagicMock()
        queries.getAcquired.return_value = (1, 2, None)
        self.q = LocalQueue(queries, "testQueue", Strategy.IN_ORDER)

    def test_init_already_acquired(self):
        self.assertEqual(self.q.get_job(), 1)
        self.assertEqual(self.q.get_set(), 2)

    def test_acquire_2x(self):
        # Second acquire should do nothing, return True
        self.q.queries.getNextJobInQueue.return_value = None
        self.assertEqual(self.q.acquire(), True)
        self.q.queries.acquireJob.assert_not_called()
        self.assertEqual(self.q.get_job(), 1)
        self.assertEqual(self.q.get_set(), 2)

    def test_release(self):
        self.q.release()
        self.q.queries.release.assert_called_with(1, 2)
        self.assertEqual([self.q.get_job(), self.q.get_set()], [None, None])

    def test_decrement(self):
        self.q.decrement()
        self.q.queries.decrement.assert_called_with(1, 2)

    def as_dict(self):
        self.q.queries.begin_run.return_value = 4
        self.q.begin_run()  # Trigger active_set
        self.q.queries.getJobsAndSets.return_value = []
        self.q.set = Mock(id=2)
        self.assertEqual(
            self.q.as_dict(),
            QueueData(name="testQueue", strategy="IN_ORDER", jobs=[], active_set=2),
        )


class TestLANQueueNoConnection(unittest.TestCase):
    def setUp(self):
        self.ucb = MagicMock()
        self.q = LANQueue(
            "ns",
            "localhost:1234",
            "basedir",
            logging.getLogger(),
            Strategy.IN_ORDER,
            self.ucb,
        )

    def test_update_peer_state(self):
        self.q.update_peer_state("HI", {})  # No explosions? Good


class TestLANQueueConnected(unittest.TestCase):
    def setUP(self):
        self.ucb = MagicMock()
        self.q = LANQueue(
            "ns",
            "localhost:1234",
            "basedir",
            logging.getLogger(),
            Strategy.IN_ORDER,
            self.ucb,
        )
        self.q.lan = MagicMock()
        self.q.lan.q = MagicMock()


class TestMultiQueue(unittest.TestCase):
    def setUp(self):
        self.q = MultiQueue(MagicMock(), Strategy.IN_ORDER)

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
