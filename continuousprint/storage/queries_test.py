import unittest
from unittest.mock import ANY
from pathlib import Path
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

PROFILE = dict(name="profile")


class TestEmptyQueue(DBTest):
    def setUp(self):
        super().setUp()

    def testGettersReturnEmpty(self):
        self.assertEqual(list(q.getJobsAndSets(DEFAULT_QUEUE)), [])
        self.assertEqual(q.getNextJobInQueue(DEFAULT_QUEUE, PROFILE), None)
        self.assertEqual(q.getAcquiredJob(), None)

    def testClearOldState(self):
        Job.create(name="j1", count=1, acquired=True, queue=1, rank=0)
        Run.create(queueName="q", jobName="j1", path="a.gcode")
        q.clearOldState()
        self.assertEqual(Job.select().where(Job.acquired).count(), 0)
        self.assertEqual(Run.select().where(Run.end.is_null()).count(), 0)

    def testImportJob(self):
        q.importJob(
            DEFAULT_QUEUE,
            dict(name="j1", count=5, remaining=4, sets=[dict(count=1, path="a.gcode")]),
            Path("dirname"),
        )
        j = Job.get(id=1)
        self.assertEqual(j.name, "j1")
        self.assertEqual(j.remaining, 5)  # Overridden
        self.assertEqual(j.sets[0].path, "dirname/a.gcode")  # Prepended dirname

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

        # Append with that same job appends to that job
        self.assertEqual(
            q.appendSet(
                DEFAULT_QUEUE,
                "2",
                dict(path="a.gcode", sd=False, material="", count=1),
            ),
            dict(job_id=2, set_=ANY),
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
        q.resetJobs([1, 2, 3])


class TestSingleItemQueue(DBTest):
    def setUp(self):
        super().setUp()
        q.appendSet(
            DEFAULT_QUEUE, "", dict(path="a.gcode", sd=False, material="", count=1)
        )
        Job.update(name="j1", draft=False).where(Job.id == 1).execute()

    def testGetJobsAndSets(self):
        js = list(q.getJobsAndSets(DEFAULT_QUEUE))
        self.assertEqual(len(js), 1)
        self.assertEqual(js[0].as_dict()["name"], "j1")

    def testNextJobInQueue(self):
        self.assertEqual(q.getNextJobInQueue(DEFAULT_QUEUE, PROFILE).name, "j1")

    def testUpdateJob(self):
        q.updateJob(1, dict(name="jj", count=5))
        j = q.getJobsAndSets(DEFAULT_QUEUE)[0]
        self.assertEqual(j.name, "jj")
        self.assertEqual(j.count, 5)

    def testUpdateJobSet(self):
        q.updateJob(1, dict(sets=[dict(id=1, count=500)]))
        self.assertEqual(Set.get(id=1).count, 500)

    def testUpdateJobSetMaterials(self):
        q.updateJob(1, dict(sets=[dict(id=1, materials=["a", "b"])]))
        self.assertEqual(Set.get(id=1).materials(), ["a", "b"])

    def testUpdateJobSetProfiles(self):
        q.updateJob(1, dict(sets=[dict(id=1, profiles=["a", "b"])]))
        self.assertEqual(Set.get(id=1).profiles(), ["a", "b"])

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

    def testAcquire(self):
        self.assertEqual(q.acquireJob(Job.get(1)), True)
        self.assertEqual(Job.get(1).acquired, True)

    def testRunBeginEnd(self):
        self.assertEqual(Run.select().count(), 0)
        j = Job.get(id=1)
        s = Set.get(id=1)
        r = q.beginRun(DEFAULT_QUEUE, j.name, s.path)
        self.assertEqual(r.path, "a.gcode")
        self.assertEqual(r.jobName, s.job.name)
        self.assertEqual(q.getActiveRun(DEFAULT_QUEUE, j.name, s.path), r)
        q.endRun(r, "success")
        self.assertEqual(r.result, "success")

    def testGetNextJobInQueueParameterized(self):
        cases = [  # set/job remaining before and after retrieval, plus whether a result is retrieved
            [(1, 1), (1, 1), True],
            [(0, 1), (0, 0), False],
            [(0, 2), (1, 1), True],
            [(1, 0), (1, 0), False],  # job remaining=0 always returns false
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

                result = q.getNextJobInQueue(DEFAULT_QUEUE, PROFILE)
                if notNone:
                    self.assertNotEqual(result, None)
                    self.assertEqual(result.sets[0].remaining, after[0])
                    self.assertEqual(result.remaining, after[1])
                else:
                    self.assertEqual(result, None)

    def testDecrementParameterized(self):
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

                s.decrement(dict(name=PROFILE))

                s = Set.get(id=s.id)
                j = Job.get(id=j.id)
                self.assertEqual(s.remaining, after[0])
                self.assertEqual(j.remaining, after[1])

    def testResetJob(self):
        j = Job.get(id=1)
        s = j.sets[0]
        s.remaining = 0
        j.remaining = 0
        s.save()
        j.save()
        q.resetJobs([j.id])
        # Replenishing the job replenishes all sets
        self.assertEqual(Set.get(id=s.id).remaining, 1)
        self.assertEqual(Job.get(id=j.id).remaining, 1)

    def testUpdateJobCount(self):
        q.updateJob(1, dict(count=5, remaining=5))
        j = Job.get(id=1)
        self.assertEqual(j.count, 5)
        self.assertEqual(j.remaining, 5)

    def testUpdateJobCountZeros(self):
        q.updateJob(1, dict(count=0, remaining=0))
        j = Job.get(id=1)
        self.assertEqual(j.count, 0)
        self.assertEqual(j.remaining, 0)

    def testUpdateJobInvalid(self):
        # Can't have remaining > count for jobs (sets are fine though)
        with self.assertRaises(Exception):
            q.updateJob(1, dict(count=1, remaining=2))

        # Negative count not allowed
        with self.assertRaises(Exception):
            q.updateJob(1, dict(count=-5))

        # Negative remaining not allowed
        with self.assertRaises(Exception):
            q.updateJob(1, dict(remaining=-5))

    def testUpdateSetCountAndRemaining(self):
        # Note that remaining can exceed count
        q.updateJob(1, dict(sets=[dict(id=1, count=10, remaining=15)]))
        s2 = Set.get(id=1)
        self.assertEqual(s2.count, 10)
        self.assertEqual(s2.remaining, 15)


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

        js = [q.newEmptyJob(DEFAULT_QUEUE, f"j{i}") for i in (1, 2)]
        for j in js:
            j.draft = False
            j.save()

        for j, path in [
            (js[0], "a.gcode"),
            (js[0], "b.gcode"),
            (js[1], "c.gcode"),
            (js[1], "d.gcode"),
        ]:
            q.appendSet(
                DEFAULT_QUEUE,
                str(j.id),
                dict(path=path, sd=False, material="", count=1),
                rank=rank,
            )

    def testMoveJob(self):
        for (moveArgs, want) in [((1, 2), [2, 1]), ((2, -1), [2, 1])]:
            with self.subTest(f"moveJob({moveArgs}) -> want {want}"):
                q.moveJob(*moveArgs)
                self.assertEqual([j.id for j in q.getJobsAndSets(DEFAULT_QUEUE)], want)

    def testGetNextJobAfterDecrement(self):
        j = q.getNextJobInQueue(DEFAULT_QUEUE, PROFILE)
        s = j.sets[0]
        s.decrement(dict(name=PROFILE))
        j2 = q.getNextJobInQueue(DEFAULT_QUEUE, PROFILE)
        self.assertEqual(j2.id, j.id)
        self.assertEqual(j2.sets[0].remaining, 0)

    def testGetHistoryNoRuns(self):
        self.assertEqual(q.getHistory(), [])

    def testGetHistory(self):
        s = Set.get(id=1)
        r = q.beginRun(DEFAULT_QUEUE, s.job.name, s.path)
        q.endRun(r, "success")
        s = Set.get(id=2)
        r = q.beginRun(DEFAULT_QUEUE, s.job.name, s.path)
        self.assertEqual(
            q.getHistory(),
            [
                # Unfinished run references b.gcode, comes first in list (ascending timestamp sort order)
                {
                    "end": None,
                    "job_name": "j1",
                    "result": None,
                    "run_id": 2,
                    "set_path": "b.gcode",
                    "queue_name": DEFAULT_QUEUE,
                    "movie_path": None,
                    "thumb_path": None,
                    "start": ANY,
                },
                {
                    "end": ANY,
                    "job_name": "j1",
                    "result": "success",
                    "run_id": 1,
                    "set_path": "a.gcode",
                    "queue_name": DEFAULT_QUEUE,
                    "movie_path": None,
                    "thumb_path": None,
                    "start": ANY,
                },
            ],
        )

    def testResetHistory(self):
        s = Set.get(id=1)
        q.beginRun(DEFAULT_QUEUE, s.job.name, s.path)
        self.assertNotEqual(Run.select().count(), 0)
        q.resetHistory()
        self.assertEqual(Run.select().count(), 0)

    def testAnnotateLastRun(self):
        s = Set.get(id=1)
        r = q.beginRun(DEFAULT_QUEUE, s.job.name, s.path)
        q.endRun(r, "success")
        q.annotateLastRun(s.path, "movie_path.mp4", "thumb_path.png")
        r = Run.get(id=r.id)
        self.assertEqual(r.movie_path, "movie_path.mp4")
        self.assertEqual(r.thumb_path, "thumb_path.png")
