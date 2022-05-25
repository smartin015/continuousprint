import unittest
import datetime
import time
from unittest.mock import MagicMock, ANY
from .driver import Driver, Action as DA, Printer as DP
import logging
import traceback

logging.basicConfig(level=logging.DEBUG)


class TestFromInactive(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        self.d.action(DA.DEACTIVATE, DP.IDLE)
        item = MagicMock(path="asdf")  # return same item by default every time
        self.d.q.get_set_or_acquire.return_value = item
        self.d.q.get_set.return_value = item

    def test_activate_not_yet_printing(self):
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_printing -> printing
        self.d.q.begin_run.assert_called()
        self.d._runner.start_print.assert_called_with(self.d.q.get_set.return_value)
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_activate_already_printing(self):
        self.d.action(DA.ACTIVATE, DP.BUSY)
        self.d.action(DA.TICK, DP.BUSY)
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_events_cause_no_action_when_inactive(self):
        def assert_nocalls():
            self.d._runner.run_finish_script.assert_not_called()
            self.d._runner.start_print.assert_not_called()

        for p in [DP.IDLE, DP.BUSY, DP.PAUSED]:
            for a in [DA.SUCCESS, DA.FAILURE, DA.TICK, DA.DEACTIVATE, DA.SPAGHETTI]:
                self.d.action(a, p)
                assert_nocalls()
                self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_completed_print_not_in_queue(self):
        self.d.action(DA.ACTIVATE, DP.BUSY)  # -> start print -> printing
        self.d.action(DA.SUCCESS, DP.IDLE, "otherprint.gcode")  # -> success
        self.d.action(DA.TICK, DP.IDLE)  # -> start_clearing

        self.d.action(DA.TICK, DP.IDLE)  # -> clearing
        self.d.action(DA.SUCCESS, DP.IDLE)  # -> start_print
        self.d.action(DA.TICK, DP.IDLE)  # -> printing

        # Non-queue print completion while the driver is active
        # should kick off a new print from the head of the queue
        self.d._runner.start_print.assert_called_with(self.d.q.get_set.return_value)
        self.d.q.begin_run.assert_called_once()

        # Verify no end_run call anywhere in this process, since print was not in queue
        self.d.q.end_run.assert_not_called()

    def test_start_clearing_waits_for_idle(self):
        self.d.state = self.d._state_start_clearing
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)
        self.d._runner.clear_bed.assert_not_called()
        self.d.action(DA.TICK, DP.PAUSED)
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)
        self.d._runner.clear_bed.assert_not_called()

    def test_retry_after_failure(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries - 2
        self.d.action(DA.TICK, DP.IDLE)  # Start clearing
        self.assertEqual(self.d.retries, self.d.max_retries - 1)
        self.assertEqual(self.d.state.__name__, self.d._state_start_clearing.__name__)

    def test_activate_clears_retries(self):
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print
        self.assertEqual(self.d.retries, 0)

    def test_failure_with_max_retries_sets_inactive(self):
        self.d.state = self.d._state_failure
        self.d.retries = self.d.max_retries - 1
        self.d.action(DA.TICK, DP.IDLE)  # -> inactive
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_resume_from_pause(self):
        self.d.state = self.d._state_paused
        self.d.action(DA.TICK, DP.BUSY)
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_bed_clearing_failure(self):
        self.d.state = self.d._state_clearing
        self.d.action(DA.FAILURE, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_finishing_failure(self):
        self.d.state = self.d._state_finishing
        self.d.action(DA.FAILURE, DP.IDLE)
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)

    def test_completed_last_print(self):
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.d._runner.start_print.reset_mock()

        self.d.action(
            DA.SUCCESS, DP.IDLE, path=self.d.q.get_set_or_acquire().path
        )  # -> success
        self.d.q.get_set_or_acquire.return_value = None  # Nothing more in the queue
        self.d.action(DA.TICK, DP.IDLE)  # -> start_finishing
        self.d.action(DA.TICK, DP.IDLE)  # -> finishing
        self.d._runner.run_finish_script.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_finishing.__name__)

        self.d.action(DA.TICK, DP.IDLE)  # -> inactive
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)


class TestFromStartPrint(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        item = MagicMock(path="asdf")  # return same item by default every time
        self.d.q.get_set_or_acquire.return_value = item
        self.d.q.get_set.return_value = item
        self.d.action(DA.DEACTIVATE, DP.IDLE)
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing

    def test_success(self):
        self.d._runner.start_print.reset_mock()

        self.d.action(
            DA.SUCCESS, DP.IDLE, path=self.d.q.get_set.return_value.path
        )  # -> success
        self.d.action(DA.TICK, DP.IDLE)  # -> start_clearing
        self.d.q.end_run.assert_called_once()
        item2 = MagicMock(path="basdf")
        self.d.q.get_set_or_acquire.return_value = (
            item2  # manually move the supervisor forward in the queue
        )
        self.d.q.get_set.return_value = item2

        self.d.action(DA.TICK, DP.IDLE)  # -> clearing
        self.d._runner.clear_bed.assert_called_once()

        self.d.action(DA.SUCCESS, DP.IDLE)  # -> start_print -> printing
        self.d._runner.start_print.assert_called_with(item2)

    def test_paused_with_spaghetti_early_triggers_cancel(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now() - datetime.timedelta(seconds=10)
        )
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> spaghetti_recovery
        self.d.action(DA.TICK, DP.PAUSED)  # -> cancel + failure
        self.d._runner.cancel_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_failure.__name__)

    def test_paused_with_spaghetti_late_waits_for_user(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now()
            - datetime.timedelta(seconds=self.d.retry_threshold_seconds + 1)
        )
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> printing (ignore spaghetti)
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_paused.__name__)

    def test_paused_manually_early_waits_for_user(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now() - datetime.timedelta(seconds=10)
        )
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d.action(DA.TICK, DP.PAUSED)  # stay in paused state
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_paused.__name__)

    def test_paused_manually_late_waits_for_user(self):
        self.d.q.get_run.return_value = MagicMock(
            start=datetime.datetime.now() - datetime.timedelta(seconds=1000)
        )
        self.d.action(DA.TICK, DP.PAUSED)  # -> paused
        self.d.action(DA.TICK, DP.PAUSED)  # stay in paused state
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_paused.__name__)

    def test_paused_on_temp_file_falls_through(self):
        self.d.state = self.d._state_clearing  # -> clearing
        self.d.action(DA.TICK, DP.PAUSED)
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_clearing.__name__)

        self.d.state = self.d._state_finishing  # -> finishing
        self.d.action(DA.TICK, DP.PAUSED)
        self.d._runner.cancel_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_finishing.__name__)

    def test_user_deactivate_sets_inactive(self):
        self.d._runner.start_print.reset_mock()

        self.d.action(DA.DEACTIVATE, DP.IDLE)  # -> inactive
        self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)
        self.d._runner.start_print.assert_not_called()
        self.d.q.end_run.assert_not_called()



class TestProfileConstraints(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            profiles=["A", "B"],
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        self.d.action(DA.DEACTIVATE, DP.IDLE)

    def _setItemProfiles(self, m):
        item = MagicMock()
        item.profiles.return_value = m
        self.d.q.get_set.return_value = item
        self.d.q.get_set_or_acquire.return_value = item

    def test_empty(self):
        self._setItemProfiles([])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_incompatible(self):
        self._setItemProfiles(['C'])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)




class TestMaterialConstraints(unittest.TestCase):
    def setUp(self):
        self.d = Driver(
            queue=MagicMock(),
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
        self.d.set_retry_on_pause(True)
        self.d.action(DA.DEACTIVATE, DP.IDLE)

    def _setItemMaterials(self, m):
        item = MagicMock()
        item.materials.return_value = m
        self.d.q.get_set.return_value = item
        self.d.q.get_set_or_acquire.return_value = item

    def test_empty(self):
        self._setItemMaterials([])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_none(self):
        self._setItemMaterials([None])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool1mat_none(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE)
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_start_print.__name__)

    def test_tool1mat_wrong(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool0bad"])
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_start_print.__name__)

    def test_tool1mat_ok(self):
        self._setItemMaterials(["tool1mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool1mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool2mat_ok(self):
        self._setItemMaterials([None, "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=[None, "tool2mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool1mat_tool2mat_ok(self):
        self._setItemMaterials(["tool1mat", "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool1mat", "tool2mat"])
        self.d._runner.start_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_printing.__name__)

    def test_tool1mat_tool2mat_reversed(self):
        self._setItemMaterials(["tool1mat", "tool2mat"])
        self.d.action(DA.ACTIVATE, DP.IDLE, materials=["tool2mat", "tool1mat"])
        self.d._runner.start_print.assert_not_called()
        self.assertEqual(self.d.state.__name__, self.d._state_start_print.__name__)


from .storage.database_test import DBTest
from .storage.database import DEFAULT_QUEUE, MODELS, populate as populate_db
from .storage import queries
from .queues import MultiQueue, LocalQueue, LANQueue, Strategy
from peewee import SqliteDatabase
from collections import defaultdict


class IntegrationTest(DBTest):
    def newQueue(self):
        raise NotImplementedError

    def setUp(self):
        super().setUp()

        def onupdate():
            pass

        self.lq = self.newQueue()
        self.mq = MultiQueue(queries, Strategy.IN_ORDER, onupdate)
        self.mq.add(self.lq.ns, self.lq, testing=True)
        self.d = Driver(
            queue=self.mq,
            script_runner=MagicMock(),
            logger=logging.getLogger(),
        )
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
                self.d._runner.clear_bed.assert_called()
                self.d._runner.clear_bed.reset_mock()
                self.d.action(DA.TICK, DP.IDLE)  # -> start_print
            else:  # Finishing
                self.d.action(DA.TICK, DP.IDLE)  # -> start_finishing
                self.assertEqual(
                    self.d.state.__name__, self.d._state_start_finishing.__name__
                )
                self.d.action(DA.TICK, DP.IDLE)  # -> finishing
                self.d._runner.run_finish_script.assert_called()
                self.d._runner.run_finish_script.reset_mock()
                self.d.action(DA.TICK, DP.IDLE)  # -> inactive
                self.assertEqual(self.d.state.__name__, self.d._state_inactive.__name__)
        except AssertionError as e:
            raise AssertionError(
                f"Expecting start_print={want_path}, finishing={finishing}"
            ) from e


class LocalQueueIntegrationTest(IntegrationTest):
    """A simple in-memory integration test between DB storage layer, queuing layer, and driver."""

    def newQueue(self):
        return LocalQueue(queries, DEFAULT_QUEUE, Strategy.IN_ORDER)

    def test_retries_failure(self):
        queries.appendSet(
            DEFAULT_QUEUE, "", dict(path="j1.gcode", sd=False, material="", count=1)
        )
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.d.action(DA.SPAGHETTI, DP.BUSY)  # -> spaghetti_recovery
        self.d.action(DA.TICK, DP.PAUSED)  # -> cancel + failure
        self.d._runner.cancel_print.assert_called()
        self.assertEqual(self.d.state.__name__, self.d._state_failure.__name__)

    def test_multi_job(self):
        queries.appendSet(
            DEFAULT_QUEUE, "", dict(path="j1.gcode", sd=False, material="", count=1)
        )
        queries.appendSet(
            DEFAULT_QUEUE, "", dict(path="j2.gcode", sd=False, material="", count=1)
        )
        queries.updateJob(1, dict(count=2, remaining=2))

        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assert_from_printing_state("j1.gcode")
        self.assert_from_printing_state("j1.gcode")
        self.assert_from_printing_state("j2.gcode", finishing=True)

    def test_completes_job_in_order(self):
        queries.appendSet(
            DEFAULT_QUEUE, "", dict(path="a.gcode", sd=False, material="", count=2)
        )
        queries.appendSet(
            DEFAULT_QUEUE, "1", dict(path="b.gcode", sd=False, material="", count=1)
        )

        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assert_from_printing_state("a.gcode")
        self.assert_from_printing_state("a.gcode")
        self.assert_from_printing_state("b.gcode", finishing=True)


class LocalLockManager:
    def __init__(self, locks, ns):
        self.locks = locks
        self.selfID = ns

    def getPeerLocks(self):
        result = defaultdict(list)
        for lk, p in self.locks.items():
            result[p].append(lk)
        print("getPeerLocks", result)
        return result

    def tryAcquire(self, k, sync=None, timeout=None):
        if self.locks.get(k) is not None and self.locks[k] != self.selfID:
            return False
        self.locks[k] = self.selfID
        return True

    def release(self, k):
        self.locks.pop(k, None)


class IntegrationTestLANQueue(IntegrationTest):
    """A simple in-memory integration test between DB storage layer, queuing layer, and driver."""

    def newQueue(self):
        def onupdate():
            pass

        lq = LANQueue(
            "LAN",
            "asdf:12345",
            None,
            logging.getLogger("lantest"),
            Strategy.IN_ORDER,
            onupdate,
        )
        return lq

    def setUp(self):
        super().setUp()
        self.lq.lan.q.locks = LocalLockManager(dict(), "lq")

    def test_completes_job_in_order(self):
        self.lq.lan.q.setJob(
            "bsdf",
            dict(
                name="j1",
                sets=[
                    dict(path="a.gcode", count=1, remaining=1),
                    dict(path="b.gcode", count=1, remaining=1),
                ],
                count=1,
                remaining=1,
            ),
        )
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assert_from_printing_state("a.gcode")
        self.assert_from_printing_state("b.gcode", finishing=True)

    def test_multi_job(self):
        for name in ("j1", "j2"):
            self.lq.lan.q.setJob(
                f"{name}_hash",
                dict(
                    name=name,
                    sets=[dict(path=f"{name}.gcode", count=1, remaining=1)],
                    count=1,
                    remaining=1,
                ),
            )
        self.d.action(DA.ACTIVATE, DP.IDLE)  # -> start_print -> printing
        self.assert_from_printing_state("j1.gcode")
        self.assert_from_printing_state("j2.gcode", finishing=True)


class IntegrationTestMultiDriverLANQueue(unittest.TestCase):
    def setUp(self):
        NPEERS = 2
        self.dbs = [SqliteDatabase(":memory:") for i in range(NPEERS)]

        def onupdate():
            pass

        self.locks = {}
        self.peers = []
        for i, db in enumerate(self.dbs):
            with db.bind_ctx(MODELS):
                populate_db()
            lq = LANQueue(
                "LAN",
                f"peer{i}:{12345+i}",
                None,
                logging.getLogger(f"peer{i}:LAN"),
                Strategy.IN_ORDER,
                onupdate,
            )
            mq = MultiQueue(queries, Strategy.IN_ORDER, onupdate)
            mq.add(lq.ns, lq, testing=True)
            d = Driver(
                queue=mq,
                script_runner=MagicMock(),
                logger=logging.getLogger(f"peer{i}:Driver"),
            )
            d.set_retry_on_pause(True)
            d.action(DA.DEACTIVATE, DP.IDLE)
            lq.lan.q.locks = LocalLockManager(self.locks, f"peer{i}")
            if i > 0:
                lq.lan.q.peers = self.peers[0][2].lan.q.peers
                lq.lan.q.jobs = self.peers[0][2].lan.q.jobs
            self.peers.append((d, mq, lq, db))

    def test_ordered_acquisition(self):
        logging.info("============ BEGIN TEST ===========")
        self.assertEqual(len(self.peers), 2)
        (d1, _, lq1, db1) = self.peers[0]
        (d2, _, lq2, db2) = self.peers[1]
        for name in ("j1", "j2", "j3"):
            lq1.lan.q.setJob(
                f"{name}_hash",
                dict(
                    name=name,
                    sets=[
                        dict(path=f"{name}.gcode", count=1, remaining=1),
                    ],
                    count=1,
                    remaining=1,
                ),
            )

        # Activating peer0 causes it to acquire j1 and begin printing its file
        with db1.bind_ctx(MODELS):
            d1.action(DA.ACTIVATE, DP.IDLE)  # -> start_printing -> printing
            d1._runner.start_print.assert_called()
            self.assertEqual(d1._runner.start_print.call_args[0][0].path, "j1.gcode")
            self.assertEqual(self.locks["j1_hash"], "peer0")
            d1._runner.start_print.reset_mock()

        # Activating peer1 causes it to skip j1, acquire j2 and begin printing its file
        with db2.bind_ctx(MODELS):
            d2.action(DA.ACTIVATE, DP.IDLE)  # -> start_printing -> printing
            d2._runner.start_print.assert_called()
            self.assertEqual(d2._runner.start_print.call_args[0][0].path, "j2.gcode")
            d2._runner.start_print.reset_mock()

        # When peer0 finishes it decrements the job and releases it, then acquires j3 and begins work
        with db1.bind_ctx(MODELS):
            d1.action(DA.SUCCESS, DP.IDLE, path="j1.gcode")  # -> success
            d1.action(DA.TICK, DP.IDLE)  # -> start_clearing
            d1.action(DA.TICK, DP.IDLE)  # -> clearing
            d1.action(DA.TICK, DP.IDLE)  # -> start_print
            self.assertEqual(d1._runner.start_print.call_args[0][0].path, "j3.gcode")
            self.assertEqual(self.locks["j3_hash"], "peer0")
            d1._runner.start_print.reset_mock()

        # When peer1 finishes it decrements j2 and releases it, then goes idle as j3 is already acquired
        with db2.bind_ctx(MODELS):
            d2.action(DA.SUCCESS, DP.IDLE, path="j2.gcode")  # -> success
            d2.action(DA.TICK, DP.IDLE)  # -> start_finishing
            d2.action(DA.TICK, DP.IDLE)  # -> finishing
            d2.action(DA.TICK, DP.IDLE)  # -> active
            self.assertEqual(d2.state.__name__, d2._state_inactive.__name__)


if __name__ == "__main__":
    unittest.main()
