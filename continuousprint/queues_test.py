import unittest
from .queues import AbstractQueue


class MockQueue(AbstractQueue):
    def __init__(self, peek, acq):
        super().__init__()
        self.peek = peek
        self.acq = acq

    def peek_job(self):
        return self.peek

    def acquire_job(self, j):
        return self.acq

class MockSet(
mockset = {"sets": [{"remaining": 1}]}

class TestGetAssignmentFromInit(unittest.TestCase):

    def test_success(self):
        mq = MockQueue(mockset, True)
        self.assertEqual(mq.get_assignment(), "a")

    def test_acquire_failed(self):
        mq = MockQueue("a", False)
        self.assertEqual(mq.get_assignment(), None)

    def test_peek_failed(self):
        mq = MockQueue(None, True)
        self.assertEqual(mq.get_assignment(), None)
