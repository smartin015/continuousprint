class DummyQueue:
    name = "foo"


def testJob(inst, cls):
    j = cls()
    j.load_dict(
        dict(
            job=j,
            id=inst,
            acquired=False,
            name=f"job{inst}",
            count=2,
            remaining=2,
            draft=False,
            rank=0,
            peer_="foo",
            created=5,
            sets=[
                dict(
                    id=f"set{inst}",
                    path=f"set{inst}.gcode",
                    count=2,
                    remaining=2,
                    rank=0,
                    sd=False,
                    material_keys="",
                    metadata=None,
                    profiles=["profile"],
                    completed=0,
                )
            ],
        ),
        DummyQueue(),
    )
    return j


class JobEqualityTests:
    def _strip(self, d, ks):
        for k in ks:
            if k in d:
                del d[k]

    def assertJobsEqual(self, v1, v2, ignore=[]):
        d1 = v1.as_dict()
        d2 = v2.as_dict()
        for d in (d1, d2):
            self._strip(d, [*ignore, "id", "queue", "hash"])
        for s in d1["sets"]:
            self._strip(s, ("id", "rank"))
        for s in d2["sets"]:
            self._strip(s, ("id", "rank"))
        self.assertEqual(d1, d2)

    def assertSetsEqual(self, s1, s2):
        self.assertTrue(s1 is not None)
        self.assertTrue(s2 is not None)
        for k in (
            "path",
            "count",
            "metadata",
            "material_keys",
            "profile_keys",
            "sd",
            "remaining",
            "completed",
        ):
            self.assertEqual(getattr(s1, k), getattr(s2, k))


class AbstractQueueTests(JobEqualityTests):
    maxDiff = None

    def setUp(self):
        raise NotImplementedError(
            "Must create queue as self.q with testJob() inserted, also assign self.j"
        )

    def test_acquire_get_release(self):
        self.assertEqual(self.q.acquire(), True)
        self.assertEqual(self.q.get_job().acquired, True)
        self.assertJobsEqual(self.q.get_job(), self.j, ignore=["acquired", "sd"])
        self.assertSetsEqual(self.q.get_set(), self.j.sets[0])
        self.q.release()
        self.assertEqual(self.q.get_job(), None)
        self.assertEqual(self.q.get_set(), None)

    def test_decrement_and_reset(self):
        self.assertEqual(self.q.acquire(), True)
        self.assertEqual(self.q.decrement(), True)  # Work remains
        got = self.q.get_set()
        self.assertEqual(got.remaining, 1)
        self.assertEqual(got.completed, 1)
        self.q.reset_jobs([self.jid])
        got = self.q.as_dict()["jobs"][0]["sets"][0]
        self.assertEqual(got["remaining"], 2)
        self.assertEqual(got["completed"], 0)

    def test_remove_jobs(self):
        self.assertEqual(self.q.remove_jobs([self.jid])["jobs_deleted"], 1)
        self.assertEqual(len(self.q.as_dict()["jobs"]), 0)

    def test_as_dict(self):
        d = self.q.as_dict()
        self.assertNotEqual(d.get("name"), None)
        self.assertNotEqual(d.get("jobs"), None)
        self.assertNotEqual(d.get("strategy"), None)


class EditableQueueTests(JobEqualityTests):
    NUM_TEST_JOBS = 4

    def setUp(self):
        raise NotImplementedError(
            "Must create queue as self.q with testJob() inserted (inst=0..3)"
        )

    def test_mv_job_exchange(self):
        self.q.mv_job(self.jids[1], self.jids[2])
        jids = [j["id"] for j in self.q.as_dict()["jobs"]]
        self.assertEqual(jids, [self.jids[i] for i in (0, 2, 1, 3)])

    def test_mv_to_front(self):
        self.q.mv_job(self.jids[2], None)
        jids = [j["id"] for j in self.q.as_dict()["jobs"]]
        self.assertEqual(jids, [self.jids[i] for i in (2, 0, 1, 3)])

    def test_mv_to_back(self):
        self.q.mv_job(self.jids[2], self.jids[3])
        jids = [j["id"] for j in self.q.as_dict()["jobs"]]
        self.assertEqual(jids, [self.jids[i] for i in (0, 1, 3, 2)])

    def test_edit_job(self):
        result = self.q.edit_job(self.jids[0], dict(draft=True))
        self.assertEqual(result, self.q.as_dict()["jobs"][0])
        self.assertEqual(self.q.as_dict()["jobs"][0]["draft"], True)

    def test_edit_job_then_decrement_persists_changes(self):
        self.assertEqual(self.q.acquire(), True)
        self.assertEqual(self.q.as_dict()["jobs"][0]["acquired"], True)
        self.assertEqual(len(self.q.as_dict()["jobs"][0]["sets"]), 1)

        # Edit the acquired job, adding a new set
        newsets = [testJob(0).sets[0].as_dict()]  # Same as existing
        newsets.append(testJob(100).sets[0].as_dict())  # New set
        self.q.edit_job(self.jids[0], dict(sets=newsets))

        # Value after decrement should be consistent, i.e. not regress to prior acquired-job value
        self.q.decrement()
        self.assertEqual(len(self.q.as_dict()["jobs"][0]["sets"]), 2)

    def test_get_job_view(self):
        self.assertJobsEqual(self.q.get_job_view(self.jids[0]), testJob(0))

    def test_import_job_from_view(self):
        j = testJob(10)
        jid = self.q.import_job_from_view(j)
        self.assertJobsEqual(self.q.get_job_view(jid), j)

    def test_import_job_from_view_persists_completion_and_remaining(self):
        j = testJob(10)
        j.sets[0].completed = 3
        j.sets[0].remaining = 5
        jid = self.q.import_job_from_view(j)
        got = self.q.get_job_view(jid).sets[0]
        self.assertEqual(got.completed, j.sets[0].completed)
        self.assertEqual(got.remaining, j.sets[0].remaining)


class AbstractFactoryQueueTests(JobEqualityTests):
    pass  # TODO
