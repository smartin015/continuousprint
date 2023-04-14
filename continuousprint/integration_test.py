import unittest
import json
import datetime
import time
import tempfile
from unittest.mock import MagicMock, ANY
from .driver import Driver, Action as DA, Printer as DP
from pathlib import Path
import logging
import traceback
from .storage.database_test import DBTest
from .storage.database import DEFAULT_QUEUE, MODELS, populate_queues
from .storage import queries
from .storage.peer import PeerJobView, PeerQueueView
from .queues.multi import MultiQueue
from .queues.local import LocalQueue
from .queues.net import NetworkQueue
from .queues.base import Strategy
from .data import CustomEvents
from .script_runner import ScriptRunner
from peewee import SqliteDatabase
from collections import defaultdict
from peerprint.server_test import MockServer

# logging.basicConfig(level=logging.DEBUG)


class IntegrationTest(DBTest):
    def setUp(self):
        super().setUp()

        def onupdate():
            pass

        self.mq = MultiQueue(queries, Strategy.IN_ORDER, onupdate)
        self.mq.add(self.lq.ns, self.lq)
        self.d = Driver(
            queue=self.mq,
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )

        # Bypass running of scripts on activate, start print, deactivate etc.
        self.d._runner.run_script_for_event.return_value = None
        self.d._runner.verify_active.return_value = (True, None)

        # Default to succeeding when activating print
        self.d._runner.set_active.return_value = True

        self.d.set_retry_on_pause(True)
        self.d.action(DA.DEACTIVATE, DP.IDLE)

    def assert_from_printing_state(self, want_path, finishing=False):
        # With the driver in state "start_print", run through the usual chain of events
        # to cause a print to be kicked off and completed.
        # The end state calls are asserted for clearing / finishing depending on the value of `finishing`.
        try:
            self.d._runner.start_print.assert_called()
            self.assertEqual(self.d._runner.start_print.call_args[0][0].path, want_path)
            self.d._runner.start_print.reset_mock()

            self.d.action(
                DA.SUCCESS, DP.IDLE, path=self.d.q.get_set_or_acquire().path
            )  # -> success

            if not finishing:
                self.d.action(DA.TICK, DP.IDLE)  # -> start_clearing
                self.assertEqual(
                    self.d.state.__name__, self.d._state_start_clearing.__name__
                )
                self.d.action(DA.TICK, DP.IDLE)  # -> clearing
                self.d._runner.run_script_for_event.assert_called_with(
                    CustomEvents.PRINT_SUCCESS
                )
                self.d._runner.run_script_for_event.reset_mock()
                self.d.action(DA.SUCCESS, DP.IDLE)  # -> start_print
            else:  # Finishing
                self.d.action(DA.TICK, DP.IDLE)  # -> start_finishing
                self.assertEqual(
                    self.d.state.__name__, self.d._state_start_finishing.__name__
                )
                self.d.action(DA.TICK, DP.IDLE)  # -> finishing
                self.d._runner.run_script_for_event.assert_called_with(
                    CustomEvents.FINISH
                )
                self.d._runner.run_script_for_event.reset_mock()
                self.d.action(DA.SUCCESS, DP.IDLE)  # -> inactive
                self.assertEqual(self.d.state.__name__, self.d._state_idle.__name__)
        except AssertionError as e:
            raise AssertionError(
                f"Expecting start_print={want_path}, finishing={finishing}"
            ) from e


class TestLocalQueue(IntegrationTest):
    """A simple in-memory integration test between DB storage layer, queuing layer, and driver."""

    def newQueue(self):
        lq = LocalQueue(
            queries,
            DEFAULT_QUEUE,
            Strategy.IN_ORDER,
            dict(name="profile"),
            MagicMock(),
            MagicMock(),
        )
        # Override path existence
        lq._set_path_exists = lambda p: True
        return lq

    def setUp(self):
        self.lq = self.newQueue()
        super().setUp()

    def test_retries_failure(self):
        queries.appendSet(
            DEFAULT_QUEUE, "", dict(path="j1.gcode", sd=False, material="", count=1)
        )
        queries.updateJob(1, dict(draft=False))
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> spaghetti_recovery
        self.d.action(DA.TICK, DP.PAUSED)  # -> cancel + failure
        self.d._runner.run_script_for_event.assert_called_with(
            CustomEvents.PRINT_CANCEL
        )
        self.assertEqual(self.d.state.__name__, self.d._state_failure.__name__)

    def test_multi_job(self):
        queries.appendSet(
            DEFAULT_QUEUE,
            "",
            dict(path="j1.gcode", sd=False, material="", profile="", count=1),
        )
        queries.appendSet(
            DEFAULT_QUEUE,
            "",
            dict(path="j2.gcode", sd=False, material="", profile="", count=1),
        )
        queries.updateJob(1, dict(count=2, remaining=2, draft=False))
        queries.updateJob(2, dict(draft=False))

        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assert_from_printing_state("j1.gcode")
        self.assert_from_printing_state("j1.gcode")
        self.assert_from_printing_state("j2.gcode", finishing=True)

    def test_goes_back_when_new_job_prepended(self):
        queries.appendSet(
            DEFAULT_QUEUE,
            "",
            dict(path="j1.gcode", sd=False, material="", profile="", count=1),
        )
        queries.appendSet(
            DEFAULT_QUEUE,
            "",
            dict(path="j2.gcode", sd=False, material="", profile="", count=2),
        )
        queries.updateJob(2, dict(draft=False))

        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        queries.updateJob(1, dict(draft=False))  # now j1 is available for prinitng
        self.assert_from_printing_state("j2.gcode")
        self.assert_from_printing_state("j1.gcode")
        self.assert_from_printing_state("j2.gcode", finishing=True)

    def test_completes_job_in_order(self):
        queries.appendSet(
            DEFAULT_QUEUE,
            "",
            dict(
                path="a.gcode",
                sd=False,
                material="",
                profile="",
                count=2,
                id="set_a",
                manifest="foo",
            ),
        )
        queries.appendSet(
            DEFAULT_QUEUE,
            "1",
            dict(
                path="b.gcode",
                sd=False,
                material="",
                profile="",
                count=1,
                id="set_b",
                manifest="foo",
            ),
        )
        queries.updateJob(1, dict(draft=False))

        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assertEqual(self.d.state, self.d._state_printing)
        self.assert_from_printing_state("a.gcode")
        self.assert_from_printing_state("a.gcode")
        self.assert_from_printing_state("b.gcode", finishing=True)


class TestDriver(DBTest):
    def setUp(self):
        super().setUp()

        def onupdate():
            pass

        self.fm = MagicMock()
        self.s = ScriptRunner(
            msg=MagicMock(),
            file_manager=self.fm,
            get_key=MagicMock(),
            slicing_manager=MagicMock(),
            logger=logging.getLogger(),
            printer=MagicMock(),
            refresh_ui_state=MagicMock(),
            fire_event=MagicMock(),
            spool_manager=None,
        )
        self.s._get_user = lambda: "foo"
        self.s._wrap_stream = MagicMock(return_value=None)
        self.mq = MultiQueue(queries, Strategy.IN_ORDER, onupdate)
        self.d = Driver(
            queue=self.mq,
            script_runner=self.s,
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)

    def _setup_condition(self, cond, path=None):
        self.d.state = self.d._state_inactive
        queries.assignAutomation(
            dict(foo="G0 X20"),
            dict(bar=cond),
            {CustomEvents.ACTIVATE.event: [dict(script="foo", preprocessor="bar")]},
        )
        self.d.action(DA.ACTIVATE, DP.IDLE, path=path)

    def test_conditional_true(self):
        self._setup_condition("2 + 2 == 4")
        self.assertEqual(self.d.state.__name__, self.d._state_activating.__name__)

    def test_conditional_false(self):
        self._setup_condition("2 + 2 == 5")
        self.assertEqual(self.d.state.__name__, self.d._state_idle.__name__)

    def test_conditional_error(self):
        self._setup_condition("1 / 0")
        # Pauses via script run
        self.assertEqual(self.d.state.__name__, self.d._state_activating.__name__)

    def test_conditional_print_volume(self):
        depthpath = "metadata['analysis']['dimensions']['depth']"
        self.fm.file_exists.return_value = True
        self.fm.has_analysis.return_value = True
        self.fm.get_metadata.return_value = dict(
            analysis=dict(dimensions=dict(depth=39))
        )

        self._setup_condition(f"{depthpath} < 40", path="foo.gcode")
        self.assertEqual(self.d.state.__name__, self.d._state_activating.__name__)

        self._setup_condition(f"{depthpath} > 39", path="foo.gcode")
        self.assertEqual(self.d.state.__name__, self.d._state_idle.__name__)

    def test_external_symbols(self):
        self.s.set_external_symbols(dict(foo="bar"))
        self._setup_condition("external['foo'] == 'bar'", path="foo.gcode")
        self.assertEqual(self.d.state.__name__, self.d._state_activating.__name__)


class TestNetworkQueue(IntegrationTest):
    """A simple in-memory integration test between DB storage layer, queuing layer, and driver."""

    def setUp(self):
        # Manually construct and mock out the base implementation
        def onupdate():
            pass

        fs = MagicMock()
        fs.fetch.return_value = "foo.gcode"

        self.srv = MockServer([])
        pp = MagicMock()
        type(pp.get_plugin()).client = self.srv
        type(pp.get_plugin()).fileshare = fs
        type(pp.get_plugin()).printer_name = "test_printer"
        self.lq = NetworkQueue(
            "LAN",
            pp,
            logging.getLogger("lantest"),
            Strategy.IN_ORDER,
            onupdate,
            dict(name="profile"),
            lambda path: path,
        )
        self.lq._server_id = self.srv.get_id(self.lq.ns)
        super().setUp()

    def test_completes_job_in_order(self):
        self.srv.set_record(
            self.lq.ns,
            uuid="uuid1",
            manifest=json.dumps(
                dict(
                    id="uuid1",
                    name="j1",
                    created=0,
                    sets=[
                        dict(
                            path="a.gcode",
                            count=1,
                            remaining=1,
                            id="set0",
                            metadata="1",
                        ),
                        dict(
                            path="b.gcode",
                            count=1,
                            remaining=1,
                            id="set1",
                            metadata="2",
                        ),
                    ],
                    count=1,
                    remaining=1,
                    peer_="foo",  # TODO - should probably rely on creator
                )
            ),
            rank=dict(),
        )
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assert_from_printing_state("a.gcode")
        self.assert_from_printing_state("b.gcode", finishing=True)

    def test_multi_job(self):
        for name in ("j1", "j2"):
            self.srv.set_record(
                self.lq.ns,
                uuid=f"{name}_id",
                manifest=json.dumps(
                    dict(
                        id=f"{name}_id",
                        name=name,
                        created=0,
                        sets=[
                            dict(
                                path=f"{name}.gcode",
                                count=1,
                                remaining=1,
                                id=f"{name}_set0",
                                metadata="1",
                            )
                        ],
                        count=1,
                        remaining=1,
                        peer_="foo",  # TODO - should probably rely on creator
                    )
                ),
                rank=dict(),
            )
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assert_from_printing_state("j1.gcode")
        self.assert_from_printing_state("j2.gcode", finishing=True)


class TestMultiDriverNetworkQueue(unittest.TestCase):
    def setUp(self):
        NPEERS = 2
        self.dbs = [SqliteDatabase(":memory:") for i in range(NPEERS)]

        def onupdate():
            pass

        fs = MagicMock()
        fs.fetch.return_value = "foo.gcode"
        self.srv = MockServer([])
        self.peers = []
        for i, db in enumerate(self.dbs):
            pp = MagicMock()
            type(pp.get_plugin()).client = self.srv
            type(pp.get_plugin()).fileshare = fs
            type(pp.get_plugin()).printer_name = f"peer{i}"

            with db.bind_ctx(MODELS):
                populate_queues()
            lq = NetworkQueue(
                "LAN",
                pp,
                logging.getLogger(f"peer{i}:LAN"),
                Strategy.IN_ORDER,
                onupdate,
                dict(name="profile"),
                lambda path, sd: path,
            )
            lq._server_id = self.srv.get_id(lq.ns)

            mq = MultiQueue(queries, Strategy.IN_ORDER, onupdate)
            mq.add(lq.ns, lq)
            d = Driver(
                queue=mq,
                script_runner=MagicMock(),
                logger=logging.getLogger(f"peer{i}:Driver"),
            )
            d._runner.verify_active.return_value = (True, None)
            d._runner.run_script_for_event.return_value = None
            d._runner.set_active.return_value = True
            d.set_retry_on_pause(True)
            d.action(DA.DEACTIVATE, DP.IDLE)
            self.peers.append((d, mq, lq, db))

        for i, p in enumerate(self.peers):
            self.srv.set_status(
                "LAN",
                name=f"peer{i}",
                printers=[
                    dict(name=f"printer{i}", profile=dict(name="profile")),
                ],
            )

    def test_ordered_acquisition(self):
        logging.info("============ BEGIN TEST ===========")
        self.assertEqual(len(self.peers), 2)
        (d1, _, lq1, db1) = self.peers[0]
        (d2, _, lq2, db2) = self.peers[1]
        for name in ("j1", "j2", "j3"):
            lq1.set_job(
                f"{name}_hash",
                dict(
                    id=f"{name}_hash",
                    name=name,
                    created=0,
                    sets=[
                        dict(
                            path=f"{name}.gcode",
                            count=1,
                            remaining=1,
                            id=f"{name}_s0",
                            metadata="foo",
                        ),
                    ],
                    count=1,
                    remaining=1,
                    peer_="test",
                ),
            )

        logging.info(
            "Activating peer0 causes it to acquire j1 and begin printing its file"
        )
        with db1.bind_ctx(MODELS):
            d1.action(DA.ACTIVATE, DP.IDLE)  # -> start_printing -> printing
            d1._runner.start_print.assert_called()
            self.assertEqual(d1._runner.start_print.call_args[0][0].path, "j1.gcode")
            self.assertEqual(lq2._get_job("j1_hash")["acquired_by"], "peer0")
            d1._runner.start_print.reset_mock()

        logging.info(
            "Activating peer1 causes it to skip j1, acquire j2 and begin printing its file"
        )
        with db2.bind_ctx(MODELS):
            d2.action(DA.ACTIVATE, DP.IDLE)  # -> start_printing -> printing
            d2._runner.start_print.assert_called()
            self.assertEqual(d2._runner.start_print.call_args[0][0].path, "j2.gcode")
            d2._runner.start_print.reset_mock()

        logging.info(
            "When peer0 finishes it decrements the job and releases it, then acquires j3 and begins work"
        )
        with db1.bind_ctx(MODELS):
            d1.action(DA.SUCCESS, DP.IDLE, path="j1.gcode")  # -> success
            d1.action(DA.TICK, DP.IDLE)  # -> start_clearing
            d1.action(DA.TICK, DP.IDLE)  # -> clearing
            d1.action(DA.SUCCESS, DP.IDLE)  # -> start_print
            self.assertEqual(d1._runner.start_print.call_args[0][0].path, "j3.gcode")
            self.assertEqual(lq2._get_job("j3_hash")["acquired_by"], "peer0")
            d1._runner.start_print.reset_mock()

        logging.info(
            "When peer1 finishes it decrements j2 and releases it, then goes idle as j3 is already acquired"
        )
        with db2.bind_ctx(MODELS):
            d2.action(DA.SUCCESS, DP.IDLE, path="j2.gcode")  # -> success
            d2.action(DA.TICK, DP.IDLE)  # -> start_finishing
            d2.action(DA.TICK, DP.IDLE)  # -> finishing
            d2.action(DA.SUCCESS, DP.IDLE)  # -> idle
            self.assertEqual(d2.state.__name__, d2._state_idle.__name__)

    def test_non_local_edit(self):
        # Editing a file on a remote peer should fetch and unpack the manifest file,
        # then apply the new changes and re-pack it before posting it again
        (d1, _, lq1, db1) = self.peers[0]
        (d2, _, lq2, db2) = self.peers[1]
        with tempfile.TemporaryDirectory() as tdir:
            (Path(tdir) / "test.gcode").touch()
            j = PeerJobView()
            j.load_dict(
                dict(
                    id="jobhash",
                    name="job",
                    created=0,
                    sets=[
                        dict(
                            id="sethash",
                            path="test.gcode",
                            count=1,
                            remaining=1,
                            profiles=["profile"],
                            metadata="foo",
                        ),
                    ],
                    count=1,
                    remaining=1,
                    peer_=None,
                ),
                PeerQueueView(lq1),
            )
            lq1._fileshare.post.return_value = "post_cid"
            lq1._path_on_disk = lambda p, sd: str(Path(tdir) / p)
            logging.info("Initial job insertion into lq2")
            lq1.import_job_from_view(j, j.id)
            lq1._fileshare.post.reset_mock()

            logging.info("lq2 edits the job with mocked fileshare unpacking")
            lq2._fileshare.fetch.return_value = str(Path(tdir) / "unpack/")
            (Path(tdir) / "unpack").mkdir()
            lq2dest = Path(tdir) / "unpack/test.gcode"
            lq2dest.touch()
            lq2.edit_job("jobhash", dict(draft=True))

            lq2._fileshare.post.assert_called_once()

            # Uses resolved file path
            c = lq2._fileshare.post.call_args[0]
            self.assertEqual(c[1], {str(lq2dest): str(lq2dest)})


if __name__ == "__main__":
    unittest.main()
