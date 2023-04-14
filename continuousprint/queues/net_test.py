import unittest
import json
import logging
import tempfile
from datetime import datetime
from unittest.mock import MagicMock
from .base import Strategy
from .base_test import (
    AbstractQueueTests,
    EditableQueueTests,
    testJob as makeAbstractTestJob,
    DummyQueue,
)
from .net import NetworkQueue, ValidationError
from ..storage.peer import PeerJobView, PeerSetView, PeerQueueView
from peerprint.server_test import MockServer

# logging.basicConfig(level=logging.DEBUG)


class NetworkQueueTest(unittest.TestCase):
    def setUp(self):
        self.ucb = MagicMock()
        self.fs = MagicMock()
        self.fs.fetch.return_value = "asdf.gcode"
        self.fs.post.return_value = "CIDHASH"
        self.cli = MockServer(
            [
                # To pass validation, need a peer that has a printer with the right profile
                dict(
                    name="testpeer",
                    printers=[
                        dict(
                            name="testprinter", profile=json.dumps(dict(name="profile"))
                        ),
                    ],
                )
            ]
        )
        pp = MagicMock()
        pp.get_plugin.return_value = MagicMock(
            client=self.cli,
            fileshare=self.fs,
        )
        self.q = NetworkQueue(
            "ns",
            pp,
            logging.getLogger(),
            Strategy.IN_ORDER,
            self.ucb,
            dict(name="profile"),
            lambda path, sd: path,
        )
        self.q._server_id = "testid"

        self.q._path_exists = lambda p: True  # Override path check for validation


class TestAbstractImpl(AbstractQueueTests, NetworkQueueTest):
    def setUp(self):
        NetworkQueueTest.setUp(self)
        self.jid = self.q.import_job_from_view(makeAbstractTestJob(0, cls=PeerJobView))
        self.j = self.q.get_job_view(self.jid)


class TestEditableImpl(EditableQueueTests, NetworkQueueTest):
    def setUp(self):
        NetworkQueueTest.setUp(self)
        self.jids = [
            self.q.import_job_from_view(makeAbstractTestJob(i, cls=PeerJobView))
            for i in range(EditableQueueTests.NUM_TEST_JOBS)
        ]
        self.cls = PeerJobView
        self.qcls = DummyQueue

    def test_mv_job_no_before_id(self):
        self.skipTest("TODO")


class TestNetworkQueue(NetworkQueueTest):
    def test_get_gjob_dirpath(self):
        self.fs.fetch.return_value = "/dir/"
        self.assertEqual(self.q.get_gjob_dirpath("hash"), "/dir/")
        self.fs.fetch.assert_called_with("hash", unpack=True)

    def _jbase(self, path="a.gcode"):
        j = PeerJobView()
        j.id = 1
        j.name = "j1"
        j.queue = PeerQueueView(MagicMock(ns="lantest"))
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
        j.sets[0].profile_keys = "brofile,profile"
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
        j.sets[0].profile_keys = "brofile"
        with self.assertRaisesRegex(ValidationError, "no match for set"):
            self.q.import_job_from_view(j)
        self.fs.post.assert_not_called()

    def test_resolved_paths_before_edit(self):
        self.fs.fetch.return_value = "/resolvedir/"
        jid = self.q.import_job_from_view(makeAbstractTestJob(0, cls=PeerJobView))
        self.q.edit_job(jid, dict(draft=True))
        j = self.q.get_job_view(jid)
        # Paths include resolved gjob directory
        self.assertEqual(j.sets[0].path, "/resolvedir/set0.gcode")
