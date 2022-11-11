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
from .wan import PeerPrintQueue, ValidationError
from ..storage.database import JobView, SetView

# logging.basicConfig(level=logging.DEBUG)


class CodecTest(unittest.TestCase):
    def test_json_encode_decode(self):
        data = dict(a=5, b="foo", c=dict(d=True))

        got, protocol = Codec.encode(data)
        self.assertEqual(type(got), bytes)
        self.assertEqual(protocol, Codec.PROTOCOL_JSON)

        got = Codec.decode(got, protocol)
        self.assertEqual(got, data)

    def test_decode_unknown_protocol(self):
        self.assertEqual(Codec.decode("", Codec.PROTOCOL_JSON), None)


class WANQueueTest(unittest.TestCase):
    def setUp(self):
        PeerPrintWANTest.setUp(self)  # Generate peerprint WANQueue as self.q
        self.q.q.syncPeer(
            dict(profile=dict(name="profile")), addr=self.q.q.addr
        )  # Helps pass validation
        ppq = self.q  # Rename to make way for CPQ WANQueue

        self.ucb = MagicMock()
        self.fs = MagicMock()
        self.q = WANQueue(
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


class TestAbstractImpl(AbstractQueueTests, WANQueueTest):
    def setUp(self):
        WANQueueTest.setUp(self)
        self.jid = self.q.import_job_from_view(makeAbstractTestJob(0))


class TestEditableImpl(EditableQueueTests, WANQueueTest):
    def setUp(self):
        WANQueueTest.setUp(self)
        self.jids = [
            self.q.import_job_from_view(makeAbstractTestJob(i))
            for i in range(EditableQueueTests.NUM_TEST_JOBS)
        ]


class TestWANQueueNoConnection(WANQueueTest):
    def test_update_peer_state(self):
        self.q.update_peer_state("HI", {}, {}, {})  # No explosions? Good


class DummyQueue:
    name = "lantest"


class TestWANQueueConnected(WANQueueTest):
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
        j = JobView()
        j.id = 1
        j.name = "j1"
        j.queue = DummyQueue()
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


class TestWANQueueWithJob(WANQueueTest):
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
