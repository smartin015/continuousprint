import unittest
import logging
from datetime import datetime
from unittest.mock import MagicMock
from .abstract import Strategy
from .lan import LANQueue
from ..storage.database import JobView

# logging.basicConfig(level=logging.DEBUG)


class LANQueueTest(unittest.TestCase):
    def setUp(self):
        self.ucb = MagicMock()
        self.fs = MagicMock()
        self.q = LANQueue(
            "ns",
            "localhost:1234",
            logging.getLogger(),
            Strategy.IN_ORDER,
            self.ucb,
            self.fs,
            dict(name="profile"),
            lambda path: path,
        )


class TestLANQueueNoConnection(LANQueueTest):
    def test_update_peer_state(self):
        self.q.update_peer_state("HI", {}, {}, {})  # No explosions? Good


class TestLANQueueConnected(LANQueueTest):
    def setUp(self):
        super().setUp()
        self.q.lan = MagicMock()
        self.q.lan.q = MagicMock()
        self.q.lan.q.getPeers.return_value = {
            "a": dict(fs_addr="123"),
        }

    def test_resolve_set_failed_bad_peer(self):
        with self.assertRaises(Exception):
            self.q.resolve_set("b", "hash", "path")

    def test_resolve_set(self):
        self.fs.fetch.return_value = "/dir/"
        self.assertEqual(self.q.resolve_set("a", "hash", "path"), "/dir/path")
        self.fs.fetch.assert_called_with("123", "hash", unpack=True)

    def test_submit_job(self):
        self.fs.post.return_value = "hash"
        j = JobView()
        j.id = 1
        j.name = "j1"
        j.sets = []
        j.count = 1
        j.draft = False
        j.created = 100
        j.remaining = 1
        j.acquired = False
        self.q.submit_job(j)
        self.fs.post.assert_called()
        self.q.lan.q.setJob.assert_called_with(
            "hash",
            {
                "name": "j1",
                "count": 1,
                "draft": False,
                "sets": [],
                "created": 100,
                "id": 1,
                "remaining": 1,
                "acquired": False,
            },
        )


class TestLANQueueWithJob(LANQueueTest):
    def setUp(self):
        pass

    def test_acquire_success(self):
        pass

    def test_acquire_failed(self):
        pass

    def test_acquire_failed_no_jobs(self):
        pass

    def test_release(self):
        pass

    def test_decrement_more_work(self):
        pass

    def test_decrement_no_more_work(self):
        pass

    def test_as_dict(self):
        pass
