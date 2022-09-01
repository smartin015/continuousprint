import unittest
import logging
import tempfile
from datetime import datetime
from unittest.mock import MagicMock
from .abstract import Strategy
from .abstract_test import (
    AbstractQueueTests,
    EditableQueueTests,
    testJob as makeAbstractTestJob,
)
from .lan import LANQueue
from ..storage.database import JobView, SetView
from peerprint.lan_queue_test import LANQueueLocalTest as PeerPrintLANTest

# logging.basicConfig(level=logging.DEBUG)


class LANQueueTest(unittest.TestCase, PeerPrintLANTest):
    def setUp(self):
        PeerPrintLANTest.setUp(self)  # Generate peerprint LANQueue as self.q
        self.q.q.syncPeer(
            dict(profile=dict(name="profile")), addr=self.q.q.addr
        )  # Helps pass validation
        ppq = self.q  # Rename to make way for CPQ LANQueue

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
            lambda path, sd: path,
        )
        self.q.lan = ppq
        self.q._path_exists = lambda p: True  # Override path check for validation


class TestAbstractImpl(AbstractQueueTests, LANQueueTest):
    def setUp(self):
        LANQueueTest.setUp(self)
        self.jid = self.q.import_job_from_view(makeAbstractTestJob(0))


class TestEditableImpl(EditableQueueTests, LANQueueTest):
    def setUp(self):
        LANQueueTest.setUp(self)
        self.jids = [
            self.q.import_job_from_view(makeAbstractTestJob(i))
            for i in range(EditableQueueTests.NUM_TEST_JOBS)
        ]


class TestLANQueueNoConnection(LANQueueTest):
    def test_update_peer_state(self):
        self.q.update_peer_state("HI", {}, {}, {})  # No explosions? Good


class TestLANQueueConnected(LANQueueTest):
    def setUp(self):
        super().setUp()
        self.q.lan = MagicMock()
        self.q.lan.q = MagicMock()
        self.q.lan.q.getPeers.return_value = {
            "a": dict(fs_addr="123", profile=dict(name="abc")),
        }

    def test_resolve_set_failed_bad_peer(self):
        with self.assertRaises(Exception):
            self.q.resolve_set("b", "hash", "path")

    def test_resolve_set(self):
        self.fs.fetch.return_value = "/dir/"
        self.assertEqual(self.q.resolve_set("a", "hash", "path"), "/dir/path")
        self.fs.fetch.assert_called_with("123", "hash", unpack=True)

    def _jbase(self, path="a.gcode"):
        j = JobView()
        j.id = 1
        j.name = "j1"
        s = SetView()
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

    def test_submit_job_file_missing(self):
        j = self._jbase()
        j.sets[0].profile_keys = "def,abc"
        result = self.q.submit_job(j)
        self.assertRegex(str(result), "file not found")
        self.fs.post.assert_not_called()

    def test_submit_job_no_profile(self):
        result = self.q.submit_job(self._jbase())
        self.assertRegex(str(result), "no assigned profile")
        self.fs.post.assert_not_called()

    def test_submit_job_no_match(self):
        j = self._jbase()
        j.sets[0].profile_keys = "def"
        result = self.q.submit_job(j)
        self.assertRegex(str(result), "no match for set")
        self.fs.post.assert_not_called()

    def test_submit_job(self):
        with tempfile.NamedTemporaryFile(suffix=".gcode") as f:
            self.fs.post.return_value = "hash"
            j = self._jbase(f.name)
            j.sets[0].profile_keys = "def,abc"
            self.q.submit_job(j)
            self.fs.post.assert_called()
            self.q.lan.q.setJob.assert_called_with(
                "hash",
                {
                    "name": "j1",
                    "count": 1,
                    "draft": False,
                    "sets": [
                        {
                            "path": f.name,
                            "count": 1,
                            "materials": [],
                            "profiles": ["def", "abc"],
                            "id": 2,
                            "rank": 1,
                            "sd": False,
                            "remaining": 1,
                            "completed": 0,
                        }
                    ],
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
