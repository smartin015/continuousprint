import unittest
from unittest.mock import ANY
import logging
from .database import (
    migrateFromSettings,
    migrateScriptsFromSettings,
    init_db,
    init_queues,
    init_automation,
    Queue,
    migrateQueuesV2ToV3,
    Job,
    Set,
    SetView,
    Run,
    Script,
    EventHook,
    StorageDetails,
    DEFAULT_QUEUE,
    STLResolveError,
)
from ..data import CustomEvents
import tempfile

# logging.basicConfig(level=logging.DEBUG)


class QueuesDBTest(unittest.TestCase):
    def setUp(self):
        self.tmpQueues = tempfile.NamedTemporaryFile(delete=True)
        self.addCleanup(self.tmpQueues.close)
        init_queues(
            self.tmpQueues.name,
            logger=logging.getLogger(),
        )
        self.q = Queue.get(name=DEFAULT_QUEUE)


class AutomationDBTest(unittest.TestCase):
    def setUp(self):
        self.tmpAutomation = tempfile.NamedTemporaryFile(delete=True)
        self.addCleanup(self.tmpAutomation.close)
        init_automation(
            self.tmpAutomation.name,
            logger=logging.getLogger(),
        )


class DBTest(QueuesDBTest, AutomationDBTest):
    def setUp(self):
        AutomationDBTest.setUp(self)
        QueuesDBTest.setUp(self)


class TestScriptMigration(AutomationDBTest):
    def testMigration(self):
        migrateScriptsFromSettings("test_clearing", "test_finished", "test_cooldown")
        self.assertEqual(
            EventHook.get(name=CustomEvents.PRINT_SUCCESS.event).script.body,
            "test_clearing",
        )
        self.assertEqual(
            EventHook.get(name=CustomEvents.FINISH.event).script.body, "test_finished"
        )
        self.assertEqual(
            EventHook.get(name=CustomEvents.COOLDOWN.event).script.body, "test_cooldown"
        )

    def testMigrationEmpty(self):
        migrateScriptsFromSettings("test_clearing", "test_finished", "")
        self.assertEqual(
            EventHook.select()
            .where(EventHook.name == CustomEvents.COOLDOWN.event)
            .count(),
            0,
        )

    def testMigrationNone(self):
        migrateScriptsFromSettings("test_clearing", "test_finished", None)
        self.assertEqual(
            EventHook.select()
            .where(EventHook.name == CustomEvents.COOLDOWN.event)
            .count(),
            0,
        )


class TestMigration(QueuesDBTest):
    def testMigrationEmptyDict(self):
        migrateFromSettings({})
        self.assertEqual(Job.select().count(), 0)
        self.assertEqual(Set.select().count(), 0)
        self.assertEqual(Run.select().count(), 0)

    def testMigrationV1_6_0(self):
        migrateFromSettings(
            [
                {
                    "name": "sample-cube-026.gcode",
                    "path": "sample-cube-026.gcode",
                    "sd": "false",
                    "job": "",
                    "materials": [],
                    "run": 0,
                    "start_ts": 1652377632,
                    "end_ts": 1652381175,
                    "result": "success",
                    "retries": 2,
                }
            ]
        )
        j = Job.get(id=1)
        self.assertEqual(j.remaining, 0)
        self.assertEqual(j.count, 1)
        self.assertEqual(j.name, "")
        s = j.sets[0]
        self.assertEqual(s.path, "sample-cube-026.gcode")
        self.assertEqual(s.remaining, 0)
        self.assertEqual(s.materials(), [])
        self.assertEqual(s.sd, False)

    def testMigrationWithSD(self):
        migrateFromSettings([{"path": "a", "sd": "true"}])
        s = Set.get(id=1)
        self.assertEqual(s.sd, True)

    def testMigrationMidJob(self):
        migrateFromSettings(
            [
                dict(path="a", run=0, start_ts=1, end_ts=2),
                dict(path="a", run=1),
            ]
        )
        j = Job.get(id=1)
        self.assertEqual(j.count, 2)
        self.assertEqual(j.remaining, 1)
        s = Set.get(id=1)
        self.assertEqual(s.count, 1)
        self.assertEqual(s.remaining, 1)

    def testMigrationMidSet(self):
        migrateFromSettings(
            [
                dict(path="a", run=0, start_ts=1, end_ts=2),
                dict(path="a", run=0),
            ]
        )
        j = Job.get(id=1)
        self.assertEqual(j.count, 1)
        self.assertEqual(j.remaining, 1)
        s = Set.get(id=1)
        self.assertEqual(s.count, 2)
        self.assertEqual(s.remaining, 1)

    def testMigrationSchemav2tov3(self):
        details = StorageDetails.select().limit(1).execute()[0]
        details.schemaVersion = "0.0.2"
        details.save()
        q = Queue.get(name=DEFAULT_QUEUE)
        j = Job.create(name="j", queue_id=q.id, rank=0)
        s = Set.create(
            path="foo.gcode",
            remaining=3,
            count=5,
            completed=0,
            sd=False,
            job_id=j.id,
            rank=1,
        )

        migrateQueuesV2ToV3(details, logger=logging.getLogger())

        # Destination set both exists and has computed `completed` field.
        # We don't actually check whether the constraints were properly applied, just assume that
        # new table creation takes care of it.
        s2 = Set.get(s.id)
        self.assertEqual(s2.completed, s.count - s.remaining)


class TestEmptyJob(QueuesDBTest):
    def setUp(self):
        super().setUp()
        self.j = Job.create(queue=self.q, name="a", rank=0, count=5, remaining=5)

    def testNextSetNoSets(self):
        self.assertEqual(self.j.next_set(dict(name="foo")), None)

    def testDecrementNoSet(self):
        self.j.decrement()
        self.assertEqual(self.j.remaining, 4)


class TestJobWithSet(QueuesDBTest):
    def setUp(self):
        super().setUp()
        self.j = Job.create(
            queue=self.q, name="a", rank=0, count=5, remaining=5, draft=False
        )
        self.s = Set.create(
            path="a",
            sd=False,
            job=self.j,
            rank=0,
            count=5,
            remaining=5,
            profile_keys="foo,baz",
        )

    def testNextSetDraft(self):
        self.j.draft = True
        self.assertEqual(self.j.next_set(dict(name="baz")), None)

    def testNextSetWithCustomFilterReject(self):
        self.assertEqual(self.j.next_set(dict(name="baz"), lambda s: False), None)

    def testNextSetWithCustomFilterAccept(self):
        self.assertEqual(self.j.next_set(dict(name="baz"), lambda s: True), self.s)

    def testNextSetWithDifferentProfile(self):
        self.assertEqual(self.j.next_set(dict(name="bar")), None)

    def testNextSetWithSameProfile(self):
        self.assertEqual(self.j.next_set(dict(name="baz")), self.s)

    def testNextSetWithZeroCount(self):
        self.s.count = 0
        self.s.remaining = 0
        self.s.save()
        self.assertEqual(self.j.next_set(dict(name="baz")), None)

    def testDecrementUnstartedSet(self):
        self.j.decrement()
        self.assertEqual(self.j.remaining, 4)
        self.assertEqual(self.j.sets[0].remaining, 5)

    def testDecrementCompletedSet(self):
        self.s.remaining = 0
        self.s.completed = 5
        self.s.save()
        self.j.decrement()
        self.assertEqual(self.j.remaining, 4)
        self.assertEqual(self.j.sets[0].remaining, 5)
        self.assertEqual(self.j.sets[0].completed, 0)

    def testDecrementPartialSet(self):
        self.s.remaining = 3
        self.s.save()
        self.j.decrement()
        self.assertEqual(self.j.remaining, 4)
        self.assertEqual(self.j.sets[0].remaining, 5)

    def testDecrementNoRemaining(self):
        self.j.remaining = 0
        self.j.decrement()
        self.assertEqual(self.j.remaining, 0)

    def testDecrementZeroCount(self):
        self.j.count = 0
        self.j.remaining = 0
        self.j.decrement()
        self.assertEqual(self.j.remaining, 0)

    def testFromDict(self):
        Set.create(
            path="a",
            sd=False,
            job=self.j,
            rank=0,
            count=5,
            remaining=3,
            material_keys="",
        )
        Set.create(
            path="b",
            sd=False,
            job=self.j,
            rank=0,
            count=3,
            remaining=1,
            material_keys="asdf",
        )
        j = Job.get(id=self.j.id)
        d = j.as_dict()
        j2 = Job.from_dict(d)
        self.assertEqual(j2.name, j.name)
        self.assertEqual(j2.count, j.count)
        self.assertEqual([s.path for s in j2.sets], [s.path for s in j.sets])


class TestMultiSet(QueuesDBTest):
    def setUp(self):
        super().setUp()
        self.j = Job.create(
            queue=self.q, name="a", rank=0, count=5, remaining=5, draft=False
        )
        self.s = []
        for name in ("a", "b"):
            self.s.append(
                Set.create(
                    path="a",
                    sd=False,
                    job=self.j,
                    rank=0,
                    count=2,
                    remaining=2,
                    material_keys="m1,m2",
                    profile_keys="p1,p2",
                )
            )

    def testSetsAreSequential(self):
        p = dict(name="p1")
        self.assertEqual(self.j.next_set(p), self.s[0])
        Set.get(1).decrement(p)
        self.assertEqual(self.j.next_set(p), self.s[0])
        Set.get(1).decrement(p)
        self.assertEqual(self.j.next_set(p), self.s[1])
        Set.get(2).decrement(p)
        self.assertEqual(self.j.next_set(p), self.s[1])


class TestSet(QueuesDBTest):
    def setUp(self):
        super().setUp()
        self.j = Job.create(
            queue=self.q, name="a", rank=0, count=5, remaining=5, draft=False
        )
        self.s = Set.create(
            path="a",
            sd=False,
            job=self.j,
            rank=0,
            count=5,
            remaining=5,
            material_keys="m1,m2",
            profile_keys="p1,p2",
        )

    def testDecrementWithRemaining(self):
        self.s.decrement(dict(name="p1"))
        self.assertEqual(self.s.remaining, 4)
        self.assertEqual(self.j.remaining, 5)

    def testDecrementToZeroDecrementsJob(self):
        self.s.remaining = 0
        self.s.decrement(dict(name="p1"))
        self.s = Set.get(id=self.s.id)
        self.j = Job.get(id=self.j.id)
        self.assertEqual(self.s.remaining, 5)
        self.assertEqual(self.j.remaining, 4)

    def testDecrementEndNotDoubleCounted(self):
        # When there's one "remaining" job run but all the sets are complete,
        # consider the job done.
        self.s.remaining = 0
        self.s.save()
        self.j.remaining = 1
        self.j.save()
        self.s.decrement(dict(name="p1"))
        self.s = Set.get(id=self.s.id)
        self.j = Job.get(id=self.j.id)
        self.assertEqual(self.j.remaining, 0)
        self.assertEqual(self.s.remaining, 0)

    def testResolveUnimplemented(self):
        sv = SetView()
        with self.assertRaises(NotImplementedError):
            sv.resolve()

    def testResolveGcode(self):
        self.assertEqual(self.s.resolve(), self.s.path)

    def testResolveSTL(self):
        self.s.path = "testpath.stl"
        with self.assertRaises(STLResolveError):
            self.s.resolve()

    def testResolveAlreadySet(self):
        self.s._resolved = "testval"
        self.assertEqual(self.s.resolve(), "testval")

    def testFromDict(self):
        d = self.s.as_dict()
        s = Set.from_dict(d)
        self.assertEqual(s.path, self.s.path)
        self.assertEqual(s.count, self.s.count)
        self.assertEqual(s.materials(), self.s.materials())
        self.assertEqual(s.profiles(), self.s.profiles())

    def test_materials_none(self):
        self.s.material_keys = ""
        self.assertEqual(self.s.materials(), [])

    def test_materials_one(self):
        self.s.material_keys = "asdf"
        self.assertEqual(self.s.materials(), ["asdf"])

    def test_materials_many(self):
        self.s.material_keys = "asdf,ghjk,zxcv"
        self.assertEqual(self.s.materials(), ["asdf", "ghjk", "zxcv"])
