import unittest
import logging
from ..storage.database_test import DBTest
from ..storage import queries
from unittest.mock import MagicMock
from .abstract import Strategy, QueueData
from .abstract_test import (
    AbstractQueueTests,
    EditableQueueTests,
    testJob as makeAbstractTestJob,
)
from .local import LocalQueue
from dataclasses import dataclass, asdict

logging.basicConfig(level=logging.DEBUG)


class TestAbstractImpl(AbstractQueueTests, DBTest):
    # See abstract_test.py for actual test cases
    def setUp(self):
        DBTest.setUp(self)
        self.q = LocalQueue(
            queries,
            "local",
            Strategy.IN_ORDER,
            dict(name="profile"),
            MagicMock(),
            MagicMock(),
        )
        self.jid = self.q.import_job_from_view(makeAbstractTestJob(0))
        self.q._set_path_exists = lambda p: True


class TestEditableImpl(EditableQueueTests, DBTest):
    # See abstract_test.py for actual test cases
    def setUp(self):
        DBTest.setUp(self)
        self.q = LocalQueue(
            queries,
            "local",
            Strategy.IN_ORDER,
            dict(name="profile"),
            MagicMock(),
            MagicMock(),
        )
        self.jids = [
            self.q.import_job_from_view(makeAbstractTestJob(i))
            for i in range(EditableQueueTests.NUM_TEST_JOBS)
        ]
        self.q._set_path_exists = lambda p: True


class TestLocalQueueInOrderNoInitialJob(unittest.TestCase):
    def setUp(self):
        queries = MagicMock()
        queries.getAcquiredJob.return_value = None
        self.q = LocalQueue(
            queries,
            "testQueue",
            Strategy.IN_ORDER,
            dict(name="profile"),
            MagicMock(),
            MagicMock(),
        )

    def test_acquire_failed(self):
        self.q.queries.getNextJobInQueue.return_value = "doesntmatter"
        self.q.queries.acquireJob.return_value = False
        self.assertEqual(self.q.acquire(), False)
        self.assertEqual(self.q.get_job(), None)

    def test_acquire_failed_no_jobs(self):
        self.q.queries.getNextJobInQueue.return_value = None
        self.assertEqual(self.q.acquire(), False)


class TestLocalQueueInOrderInitial(unittest.TestCase):
    def setUp(self):
        queries = MagicMock(name="queries")
        self.j = MagicMock(name="j")
        self.s = MagicMock(name="s")
        self.ns = MagicMock(name="ns")
        self.j.next_set.side_effect = [self.s, self.ns]
        queries.getAcquiredJob.return_value = self.j
        self.q = LocalQueue(
            queries,
            "testQueue",
            Strategy.IN_ORDER,
            dict(name="profile"),
            MagicMock(),
            MagicMock(),
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
        self.q.queries.getNextJobInQueue.return_value = self.j
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


# TODO test mv_job
# TODO test import_job

# TODO test SD card behavior on importing/exporting and printing
# class TestSD(unittest.TestCase):
#    def testSDExport(self):
#        raise NotImplementedError
#
#    def testSDImport(self):
#        raise NotImplementedError
#
#    def testSDPrintExists(self):
#        raise NotImplementedError
