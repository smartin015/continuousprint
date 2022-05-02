import unittest
from unittest.mock import MagicMock
from .supervisor import Supervisor

DUMMY_SET = "TEST"


class MockQueries:
    def __init__(self):
        self.getNextSetInQueue = MagicMock(return_value=DUMMY_SET)
        self.beginRun = MagicMock()
        self.endRun = MagicMock()


class TestSupervisor(unittest.TestCase):
    def setUp(self):
        self.queries = MockQueries()
        self.s = Supervisor(self.queries, "QUEUE")

    def testGetAssignment(self):
        self.assertEqual(self.s.get_assignment(), DUMMY_SET)

    def testBeginRun(self):
        self.s.begin_run()
        self.queries.beginRun.assert_called_with(DUMMY_SET)

    def testEndRunWithoutBegin(self):
        self.s.end_run("result")
        self.queries.endRun.assert_not_called()

    def testEndRun(self):
        r = self.s.begin_run()
        self.s.end_run("result")
        self.queries.endRun.assert_called_with(r, "result")
