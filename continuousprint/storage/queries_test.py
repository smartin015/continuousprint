import unittest
from unittest.mock import ANY
import logging
import datetime
import tempfile
import os
import time

# logging.basicConfig(level=logging.DEBUG)

from .database import (
    Job,
    Set,
    Run,
    Queue,
    init as init_db,
    DEFAULT_QUEUE,
    ARCHIVE_QUEUE,
)
from .database_test import DBTest
from ..storage import queries as q


class TestEmptyQueue(DBTest):
    def setUp(self):
        super().setUp()

    def testGettersReturnEmpty(self):
        self.assertEqual(list(q.getJobsAndSets(DEFAULT_QUEUE)), [])
        self.assertEqual(q.getNextJobInQueue(DEFAULT_QUEUE), None)
        self.assertEqual(q.getAcquired(), (None, None, None))

    def testAppendSet(self):
        # Initial append creates a job to live in
        self.assertEqual(
            q.appendSet(
                DEFAULT_QUEUE, "", dict(path="a.gcode", sd=False, material="", count=1)
            ),
            dict(job_id=1, set_=ANY),
        )

        # Subsequent append creates new job since name is still empty
        self.assertEqual(
            q.appendSet(
                DEFAULT_QUEUE, "", dict(path="a.gcode", sd=False, material="", count=1)
            ),
            dict(job_id=2, set_=ANY),
        )

        # Append with a different job name creates a new job
        self.assertEqual(
            q.appendSet(
                DEFAULT_QUEUE,
                "j2",
                dict(path="a.gcode", sd=False, material="", count=1),
            ),
            dict(job_id=3, set_=ANY),
        )
        # Append with that same job name appends to that job
        self.assertEqual(
            q.appendSet(
                DEFAULT_QUEUE,
                "j2",
                dict(path="a.gcode", sd=False, material="", count=1),
            ),
            dict(job_id=3, set_=ANY),
        )

    def testNewEmptyJob(self):
        q.newEmptyJob(DEFAULT_QUEUE)
        self.assertEqual(len(q.getJobsAndSets(DEFAULT_QUEUE)), 1)

    def testRemoveDoesNothing(self):
        self.assertEqual(
            q.remove(job_ids=[1, 2, 3], set_ids=[1, 2, 3]),
            dict(jobs_deleted=0, sets_deleted=0),
        )

    def testReplenishSilentOnFailedLookup(self):
        q.replenish([1, 2, 3], [4, 5, 6])


class TestSingleItemQueue(DBTest):
    def setUp(self):
        super().setUp()
        q.appendSet(
            DEFAULT_QUEUE, "j1", dict(path="a.gcode", sd=False, material="", count=1)
        )

    def testGetJobsAndSets(self):
        js = list(q.getJobsAndSets(DEFAULT_QUEUE))
        self.assertEqual(len(js), 1)
        self.assertEqual(js[0].as_dict()["name"], "j1")

    def testNextJobInQueue(self):
        self.assertEqual(q.getNextJobInQueue(DEFAULT_QUEUE).name, "j1")

    def testUpdateJob(self):
        q.updateJob(1, dict(name="jj", count=5))
        j = q.getJobsAndSets(DEFAULT_QUEUE)[0]
        self.assertEqual(j.name, "jj")
        self.assertEqual(j.count, 5)

    def testUpdateJobSet(self):
        q.updateJob(1, dict(sets=[dict(id=1, count=500)]))
        self.assertEqual(Set.get(id=1).count, 500)

    def testRemoveJob(self):
        q.remove(job_ids=[1])
        self.assertEqual(len(q.getJobsAndSets(DEFAULT_QUEUE)), 0)  # No jobs or sets

    def testJobIdsConsistent(self):
        q.remove(job_ids=[1])
        j = q.newEmptyJob(DEFAULT_QUEUE)
        self.assertNotEqual(
            j.id, 1
        )  # Original job ID is not reused even when it's deleted

    def testRemoveSet(self):
        q.remove(set_ids=[1])
        j = q.getJobsAndSets(DEFAULT_QUEUE)[0]
        # Job persists, but no set
        self.assertEqual(j.name, "j1")
        self.assertEqual(j.sets, [])

    def testRunBeginEnd(self):
        self.assertEqual(Run.select().count(), 0)
        j = Job.get(id=1)
        s = Set.get(id=1)
        r = q.beginRun(s)
        self.assertEqual(r.path, "a.gcode")
        self.assertEqual(r.job, s.job)
        self.assertEqual(q.getAcquired(), (j, s, r))

        q.endRun(s, r, "success")
        self.assertEqual(r.result, "success")

        # Since single job count with single set count, both should be 0 when set is completed
        self.assertEqual(s.remaining, 0)
        self.assertEqual(s.job.remaining, 0)
        self.assertEqual(q.getAcquired(), (None, None, None))

    def testRunEndFailureKeepsRemaining(self):
        s1 = Set.get(id=1)
        rem = s1.remaining
        r = q.beginRun(s1)
        q.endRun(s1, r, "failure")

        s2 = q.getNextJobInQueue(DEFAULT_QUEUE)
        self.assertEqual(s2.id, s1.id)
        self.assertEqual(s2.remaining, rem)

    def testGetNextJobInQueueParameterized(self):
        cases = [  # set/job remaining before and after retrieval, plus whether a result is retrieved
            [(1, 1), (1, 1), True],
            [(0, 1), (0, 0), False],
            [(0, 2), (1, 1), True],
            [(1, 0), (1, 0), True],
        ]
        j = Job.get(id=1)
        s = Set.get(id=1)
        for before, after, notNone in cases:
            with self.subTest(
                f"with set.remaining={before[0]}, job.remaining={before[1]} (expect result set={after[0]}, job={after[1]})"
            ):
                s.remaining = before[0]
                s.count = max(before[0], 1)
                s.save()
                j.remaining = before[1]
                j.count = max(before[1], 1)
                j.save()

                result = q.getNextJobInQueue(DEFAULT_QUEUE)
                if notNone:
                    self.assertNotEqual(result, None)
                    self.assertEqual(result.sets[0].remaining, after[0])
                    self.assertEqual(result.remaining, after[1])
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
        j = Job.get(id=1)
        s = Set.get(id=1)
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
        j = q.getNextJobInQueue(DEFAULT_QUEUE)
        s = j.sets[0]
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

                q.updateJob(j.id, dict(sets=[dict(id=s.id, count=after[0])]))
                s2 = Set.get(id=s.id)
                self.assertEqual(s2.count, after[0])
                self.assertEqual(s2.remaining, after[1])
                self.assertEqual(s2.job.remaining, after[2])


class TestMultiItemQueue(DBTest):
    def setUp(self):
        super().setUp()

        def testLex():
            t = time.time()
            i = 0
            while True:
                yield (t + 100 * i)
                i += 1

        rankGen = testLex()

        def rank():
            return next(rankGen)

        for jname, path in [
            ("j1", "a.gcode"),  # id=1
            ("j1", "b.gcode"),  # id=2
            ("j2", "c.gcode"),  # id=3
            ("j2", "d.gcode"),  # id=4
        ]:
            q.appendSet(
                DEFAULT_QUEUE,
                jname,
                dict(path=path, sd=False, material="", count=1),
                rank=rank,
            )

    def testMoveJob(self):
        for (moveArgs, want) in [((1, 2), [2, 1]), ((2, -1), [2, 1])]:
            with self.subTest(f"moveJob({moveArgs}) -> want {want}"):
                q.moveJob(*moveArgs)
                self.assertEqual([j.id for j in q.getJobsAndSets(DEFAULT_QUEUE)], want)

    def testMoveSet(self):
        for (desc, moveArgs, want) in [
            ("FirstToLast", (1, 2, 1), [2, 1, 3, 4]),
            ("LastToFirst", (2, -1, 1), [2, 1, 3, 4]),
            ("DiffJob", (1, 3, 2), [2, 3, 1, 4]),
            ("NewJob", (1, -1, -1), [2, 3, 4, 1]),
        ]:
            with self.subTest(f"{desc}: moveSet({moveArgs})"):
                q.moveSet(*moveArgs)
                set_order = [
                    (s["id"], s["rank"])
                    for j in q.getJobsAndSets(DEFAULT_QUEUE)
                    for s in j.as_dict()["sets"]
                ]
                self.assertEqual(set_order, [(w, ANY) for w in want])

    def testGetNextJobAfterSuccess(self):
        j = q.getNextJobInQueue(DEFAULT_QUEUE)
        s = j.sets[0]
        r = q.beginRun(s)
        q.endRun(s, r, "success")
        j2 = q.getNextJobInQueue(DEFAULT_QUEUE)
        self.assertEqual(j2.id, j.id)
        self.assertEqual(j2.sets[0].remaining, 0)

    def testGetHistoryNoRuns(self):
        self.assertEqual(q.getHistory(), [])

    def testGetHistory(self):
        s = Set.get(id=1)
        r = q.beginRun(s)
        q.endRun(s, r, "success")
        s = Set.get(id=2)
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
        q.beginRun(Set.get(id=1))
        self.assertNotEqual(Run.select().count(), 0)
        q.clearHistory()
        self.assertEqual(Run.select().count(), 0)
