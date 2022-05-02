import unittest
from unittest.mock import ANY
import logging
import datetime
import tempfile
import os
import time

from .database import Job, Set, Run, Queue, init as init_db
from ..storage import queries as q

QNAME = "default"

logging.basicConfig(level=logging.DEBUG)


class TestEmptyQueue(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        init_db(self.tmpdir.name + "queues.sqlite3", initial_data_path=None)

    def tearDown(self):
        # Trigger teardown of temp directory
        with self.tmpdir as _:
            pass

    def testGettersReturnEmpty(self):
        self.assertEqual(list(q.getJobsAndSets(QNAME)), [])
        self.assertEqual(q.getNextSetInQueue(QNAME), None)

    def testAppendSet(self):
        # Initial append creates a job to live in
        self.assertEqual(
            q.appendSet(
                QNAME, "", dict(path="a.gcode", sd=False, material="", count=1)
            ),
            dict(job_id=1, set_=ANY),
        )

        # Subsequent appends reuse this job since it has the same job name
        self.assertEqual(
            q.appendSet(
                QNAME, "", dict(path="a.gcode", sd=False, material="", count=1)
            ),
            dict(job_id=1, set_=ANY),
        )
        self.assertEqual(
            q.appendSet(
                QNAME, "", dict(path="a.gcode", sd=False, material="", count=1)
            ),
            dict(job_id=1, set_=ANY),
        )

        # Append with a different job name creates a new job
        self.assertEqual(
            q.appendSet(
                QNAME, "j2", dict(path="a.gcode", sd=False, material="", count=1)
            ),
            dict(job_id=2, set_=ANY),
        )

    def testNewEmptyJob(self):
        q.newEmptyJob(QNAME)
        self.assertEqual(len(q.getJobsAndSets(QNAME)), 1)

    def testRemoveDoesNothing(self):
        self.assertEqual(
            q.removeJobsAndSets(job_ids=[1, 2, 3], set_ids=[1, 2, 3]),
            dict(jobs_deleted=0, sets_deleted=0),
        )

    def testReplenishSilentOnFailedLookup(self):
        q.replenish([1, 2, 3], [4, 5, 6])


class TestSingleItemQueue(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        init_db(self.tmpdir.name + "queues.sqlite3", initial_data_path=None)
        q.appendSet(QNAME, "j1", dict(path="a.gcode", sd=False, material="", count=1))

    def tearDown(self):
        # Trigger teardown of temp directory
        with self.tmpdir as _:
            pass

    def testGetJobsAndSets(self):
        js = list(q.getJobsAndSets(QNAME))
        self.assertEqual(len(js), 1)
        self.assertEqual(js[0].as_dict()["name"], "j1")

    def testNextSetInQueue(self):
        self.assertEqual(q.getNextSetInQueue(QNAME).as_dict()["path"], "a.gcode")

    def testUpdateJob(self):
        q.updateJob(1, dict(name="jj", count=5))
        j = q.getJobsAndSets(QNAME)[0]
        self.assertEqual(j.name, "jj")
        self.assertEqual(j.count, 5)

    def testUpdateSet(self):
        q.updateSet(1, dict(count=500))
        s = q.getJobsAndSets(QNAME)[0].sets[0]
        self.assertEqual(s.count, 500)

    def testRemoveJob(self):
        q.removeJobsAndSets([1], [])
        self.assertEqual(len(q.getJobsAndSets(QNAME)), 0)  # No jobs or sets

    def testJobIdsConsistent(self):
        q.removeJobsAndSets([1], [])
        j = q.newEmptyJob("default")
        self.assertNotEqual(
            j.id, 1
        )  # Original job ID is not reused even when it's deleted

    def testRemoveSet(self):
        q.removeJobsAndSets([], [1])
        j = q.getJobsAndSets(QNAME)[0]
        # Job persists, but no set
        self.assertEqual(j.name, "j1")
        self.assertEqual(j.sets, [])

    def testRunBeginEnd(self):
        s = q.getNextSetInQueue(QNAME)
        self.assertEqual(Run.select().count(), 0)
        r = q.beginRun(s)
        self.assertEqual(r.path, "a.gcode")
        self.assertEqual(r.job, s.job)
        q.endRun(s, r, "success")
        self.assertEqual(r.result, "success")

        # Since single job count with single set count, both should be 0 when set is completed
        self.assertEqual(s.remaining, 0)
        self.assertEqual(s.job.remaining, 0)

    def testRunEndFailureKeepsRemaining(self):
        s1 = q.getNextSetInQueue(QNAME)
        rem = s1.remaining
        r = q.beginRun(s1)
        q.endRun(s1, r, "failure")

        s2 = q.getNextSetInQueue(QNAME)
        self.assertEqual(s2.id, s1.id)
        self.assertEqual(s2.remaining, rem)

    def testGetNextSetInQueueParameterized(self):
        cases = [  # set/job remaining before and after retrieval, plus whether a result is retrieved
            [(1, 1), (1, 1), True],
            [(0, 1), (0, 0), False],
            [(0, 2), (1, 1), True],
            [(1, 0), (1, 0), True],
        ]
        s = q.getNextSetInQueue(QNAME)
        j = s.job
        for before, after, notNone in cases:
            with self.subTest(
                f"with set.remaining={before[0]}, job.remaining={before[1]}"
            ):
                s.remaining = before[0]
                s.count = max(before[0], 1)
                s.save()
                j.remaining = before[1]
                j.count = max(before[1], 1)
                j.save()

                result = q.getNextSetInQueue(QNAME)
                if notNone:
                    self.assertEqual(result.remaining, after[0])
                    self.assertEqual(result.job.remaining, after[1])
                else:
                    self.assertEqual(result, None)

    def testRunSuccessParameterized(self):
        cases = [  # set/job remaining before and after success
            [(1, 1), (0, 0)],
            [(2, 1), (1, 1)],
            [(1, 2), (1, 1)],
            [(0, 1), (0, 0)],
            [(1, 0), (0, 0)],
        ]
        s = q.getNextSetInQueue(QNAME)
        j = s.job
        for before, after in cases:
            with self.subTest(
                f"with set.remaining={before[0]}, job.remaining={before[1]}"
            ):
                s.remaining = before[0]
                s.count = max(before[0], 1)
                s.save()
                j.remaining = before[1]
                j.count = max(before[1], 1)
                j.save()

                r = q.beginRun(s)
                q.endRun(s, r, "success")

                s = Set.get(id=s.id)
                j = Job.get(id=j.id)
                self.assertEqual(s.remaining, after[0])
                self.assertEqual(j.remaining, after[1])

    def testReplenish(self):
        s = q.getNextSetInQueue(QNAME)
        j = s.job

        s.remaining = 0
        j.remaining = 0
        q.replenish([j.id], [s.id])
        self.assertEqual(Set.get(id=s.id).remaining, 1)
        self.assertEqual(Job.get(id=j.id).remaining, 1)

    def testUpdateJobCount(self):
        j = Job.get(id=1)
        for before, after in [
            ((1, 1), (2, 2)),
            ((2, 2), (1, 1)),
            ((2, 1), (1, 1)),
            ((2, 1), (3, 2)),
            ((5, 3), (2, 2)),
        ]:
            with self.subTest(f"(count,remaining) {before} -> {after}"):
                j.count = before[0]
                j.remaining = before[1]
                j.save()

                q.updateJob(j.id, dict(count=after[0]))
                j2 = Job.get(id=j.id)
                self.assertEqual(j2.count, after[0])
                self.assertEqual(j2.remaining, after[1])

    def testUpdateSetCount(self):
        j = Job.get(id=1)
        s = Set.get(id=1)
        for before, after in [
            # (set count, set remaining, job remaining)
            ((1, 1, 1), (2, 2, 1)),
            ((2, 2, 1), (1, 1, 1)),
            ((4, 2, 1), (3, 2, 1)),
            ((1, 1, 0), (2, 2, 1)),  # Set now runnable, so refresh job
            ((2, 0, 0), (1, 0, 0)),  # Set no remaining, so don't refresh job
        ]:
            with self.subTest(
                f"(set.count,set.remaining,job.remaining) {before} -> {after}"
            ):
                s.count = before[0]
                s.remaining = before[1]
                s.save()
                j.remaining = before[2]
                j.count = max(before[2], 1)
                j.save()

                q.updateSet(s.id, dict(count=after[0]))
                s2 = Set.get(id=s.id)
                self.assertEqual(s2.count, after[0])
                self.assertEqual(s2.remaining, after[1])
                self.assertEqual(s2.job.remaining, after[2])


class TestMultiItemQueue(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        init_db(self.tmpdir.name + "queues.sqlite3", initial_data_path=None)

        def testLex():
            t = time.time()
            i = 0
            while True:
                yield (t + 100 * i)
                i += 1

        lexGen = testLex()

        def lex():
            return next(lexGen)

        for jname, path in [
            ("j1", "a.gcode"),
            ("j1", "b.gcode"),
            ("j2", "c.gcode"),
            ("j2", "d.gcode"),
        ]:
            q.appendSet(
                QNAME, jname, dict(path=path, sd=False, material="", count=1), lex=lex
            )

    def tearDown(self):
        # Trigger teardown of temp directory
        with self.tmpdir as _:
            pass

    def testMoveJobFirstToLast(self):
        q.moveJob(1, 2)
        self.assertEqual([j.id for j in q.getJobsAndSets(QNAME, lexOrder=True)], [2, 1])

    def testMoveJobLastToFirst(self):
        q.moveJob(2, -1)
        self.assertEqual([j.id for j in q.getJobsAndSets(QNAME, lexOrder=True)], [2, 1])

    def testMoveSetFirstToLast(self):
        q.moveSet(1, 2, 1)
        set_order = [
            s["id"]
            for j in q.getJobsAndSets(QNAME, lexOrder=True)
            for s in j.as_dict()["sets"]
        ]
        self.assertEqual(set_order, [2, 1, 3, 4])

    def testMoveSetLastToFirst(self):
        q.moveSet(2, -1, 1)
        set_order = [
            s["id"]
            for j in q.getJobsAndSets(QNAME, lexOrder=True)
            for s in j.as_dict()["sets"]
        ]
        self.assertEqual(set_order, [2, 1, 3, 4])

    def testMoveSetDiffJob(self):
        q.moveSet(1, 3, 2)
        set_order = [
            s["id"]
            for j in q.getJobsAndSets(QNAME, lexOrder=True)
            for s in j.as_dict()["sets"]
        ]
        self.assertEqual(set_order, [2, 3, 1, 4])

    def testMoveSetNewJob(self):
        q.moveSet(1, -1, -1)
        set_order = [
            s["id"]
            for j in q.getJobsAndSets(QNAME, lexOrder=True)
            for s in j.as_dict()["sets"]
        ]
        self.assertEqual(set_order, [2, 3, 4, 1])

    def testGetNextSetAfterSuccess(self):
        s = q.getNextSetInQueue(QNAME)
        r = q.beginRun(s)
        q.endRun(s, r, "success")
        s2 = q.getNextSetInQueue(QNAME)
        self.assertNotEqual(s2.id, s.id)

    def testGetHistoryNoRuns(self):
        self.assertEqual(q.getHistory(), [])

    def testGetHistory(self):
        s = q.getNextSetInQueue(QNAME)
        r = q.beginRun(s)
        q.endRun(s, r, "success")
        s = q.getNextSetInQueue(QNAME)
        r = q.beginRun(s)
        self.assertEqual(
            q.getHistory(),
            [
                # Unfinished run references b.gcode, comes first in list (ascending timestamp sort order)
                {
                    "end": None,
                    "job_id": 1,
                    "job_name": "j1",
                    "result": None,
                    "run_id": 2,
                    "set_path": "b.gcode",
                    "start": ANY,
                },
                {
                    "end": ANY,
                    "job_id": 1,
                    "job_name": "j1",
                    "result": "success",
                    "run_id": 1,
                    "set_path": "a.gcode",
                    "start": ANY,
                },
            ],
        )

    def testClearHistory(self):
        s = q.getNextSetInQueue(QNAME)
        q.beginRun(s)
        self.assertNotEqual(Run.select().count(), 0)
        q.clearHistory()
        self.assertEqual(Run.select().count(), 0)
