import unittest
import logging
import tempfile
from datetime import datetime
from unittest.mock import MagicMock
from .base import Strategy
from .base_test import (
    AbstractQueueTests,
    EditableQueueTests,
    testJob as makeAbstractTestJob,
)
from .net import NetworkQueue, ValidationError
from ..storage.peer import PeerJobView, PeerSetView

logging.basicConfig(level=logging.DEBUG)


class NetworkQueueTest(unittest.TestCase):
    def setUp(self):
        self.ucb = MagicMock()
        self.fs = MagicMock()
        self.fs.fetch.return_value = "asdf.gcode"
        self.srv = MagicMock()
        self.q = NetworkQueue(
            "ns",
            self.srv,
            logging.getLogger(),
            Strategy.IN_ORDER,
            self.ucb,
            self.fs,
            dict(name="profile"),
            lambda path, sd: path,
        )

        # To pass validation, need a peer with the right profile
        self.srv.stream_peers.return_value = [
            dict(name="testpeer", profile=dict(name="profile"))
        ]
        self.q._path_exists = lambda p: True  # Override path check for validation


class TestAbstractImpl(AbstractQueueTests, NetworkQueueTest):
    def setUp(self):
        NetworkQueueTest.setUp(self)
        self.jid = self.q.import_job_from_view(makeAbstractTestJob(0, cls=PeerJobView))


class TestEditableImpl(EditableQueueTests, NetworkQueueTest):
    def setUp(self):
        NetworkQueueTest.setUp(self)
        self.jids = [
            self.q.import_job_from_view(makeAbstractTestJob(i, cls=PeerJobView))
            for i in range(EditableQueueTests.NUM_TEST_JOBS)
        ]


class TestNetworkQueueNoConnection(NetworkQueueTest):
    def test_update_peer_state(self):
        self.q.update_peer_state("HI", {}, {}, {})  # No explosions? Good


class DummyQueue:
    name = "lantest"


class TestNetworkQueueConnected(NetworkQueueTest):
    def setUp(self):
        super().setUp()
        self.q.lan = MagicMock()
        self.q.lan.q = MagicMock()
        self.q.lan.q.hasJob.return_value = False  # For UUID generation
        self.q.lan.q.getPeers.return_value = {
            "a": dict(fs_addr="123", profile=dict(name="abc")),
        }

    def test_get_gjob_dirpath_failed_bad_peer(self):
        with self.assertRaises(Exception):
            self.q.get_gjob_dirpath("b", "hash")

    def test_get_gjob_dirpath(self):
        self.fs.fetch.return_value = "/dir/"
        self.assertEqual(self.q.get_gjob_dirpath("a", "hash"), "/dir/")
        self.fs.fetch.assert_called_with("123", "hash", unpack=True)

    def _jbase(self, path="a.gcode"):
        j = PeerJobView()
        j.id = 1
        j.name = "j1"
        j.queue = DummyQueue()
        s = PeerSetView()
        s.path = path
        s.id = 2
        s.sd = False
        s.count = 1
        s.remaining = 1
        s.completed = 0
        s.profile_keys = ""
        s.rank = 1
        s.material_keys = ""
        j.sets = [s]
        j.count = 1
        j.draft = False
        j.created = 100
        j.remaining = 1
        j.acquired = False
        return j

    def test_validation_file_missing(self):
        j = self._jbase()
        j.sets[0].profile_keys = "def,abc"
        self.q._path_exists = lambda p: False  # Override path check for validation
        with self.assertRaisesRegex(ValidationError, "file not found"):
            self.q.import_job_from_view(j)
        self.fs.post.assert_not_called()

    def test_validation_no_profile(self):
        with self.assertRaisesRegex(ValidationError, "no assigned profile"):
            self.q.import_job_from_view(self._jbase())
        self.fs.post.assert_not_called()

    def test_validation_no_match(self):
        j = self._jbase()
        j.sets[0].profile_keys = "def"
        with self.assertRaisesRegex(ValidationError, "no match for set"):
            self.q.import_job_from_view(j)
        self.fs.post.assert_not_called()


class TestNetworkQueueWithJob(NetworkQueueTest):
    def setUp(self):
        self.skipTest("TODO")

    def test_acquire_success(self):
        self.skipTest("TODO")

    def test_acquire_failed(self):
        self.skipTest("TODO")

    def test_acquire_failed_no_jobs(self):
        self.skipTest("TODO")

    def test_release(self):
        self.skipTest("TODO")

    def test_decrement_more_work(self):
        self.skipTest("TODO")

    def test_decrement_no_more_work(self):
        self.skipTest("TODO")

    def test_as_dict(self):
        self.skipTest("TODO")
