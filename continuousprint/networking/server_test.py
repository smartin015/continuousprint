import unittest
from networking.server import Server, Shell
import logging
import datetime
import tempfile
import os
from storage.database import Job, init as init_db, FileHash, Queue, NetworkType
from storage import queries

logging.basicConfig(level=logging.INFO)

class TestServerLocalOnlyInstance(unittest.TestCase):
  srv = None
  DATA_DIR = 'networking/testdata/unittest_solo/'

  def setUp(self):
    # Remove any stale state
    if self.srv is None:
      self.srv = Server(self.DATA_DIR, 6700, logging.getLogger("server"))
      self.cli = Shell()
      self.cli.attach(self.srv)

  def tearDown(self):
    #del self.cli
    #del self.srv
    # Remove any new data - faster and less noisy than reinitializing the datastores every time
    Queue.delete().where(Queue.name != "default").execute()
    Job.delete().execute()

  def testJoinNewQueue(self):
    pass

  def testJoinExistingQueue(self):
    pass

  def testLeaveQueue(self):
    pass  
    
  def testLeaveInvalidQueue(self):
    pass

  def testCreateDelete(self):
    self.cli.do_create("job1 5 a.gcode,a,3 b.gcode,b,1")
    self.assertEqual(self.cli.stdout.dump(), "Added job job1\n")
    self.cli.do_mv("job1 default null")
    self.assertEqual(self.cli.stdout.dump(), "Removed default/job1 from default\n")

  def testDeleteNonExistant(self):
    self.cli.do_mv("job1 default null")
    self.assertRegex(self.cli.stdout.dump(), "No such job")

  def testDeleteAcquired(self):
    self.cli.do_create("job1 1 a.gcode,a,1")
    j = queries.acquireJob(queries.getJob("default", "job1"))
    self.cli.stdout.dump()
    self.cli.do_mv("job1 default null")
    self.assertRegex(self.cli.stdout.dump(), "cannot transfer")

  def testCreateWithInvalidName(self):
    self.cli.do_create("job/withaslash 5 a.gcode,a,3")
    self.assertRegex(self.cli.stdout.dump(), "requires no forward slashes")

  def testCreateAlreadyExists(self):
    self.cli.do_create("job1 5 a.gcode,a,3 b.gcode,b,1")
    self.cli.stdout.dump()
    self.cli.do_create("job1 1 a.gcode,a,3")
    self.assertRegex(self.cli.stdout.dump(), "already exists")
 
  def testCreateWithNoSets(self):
    self.cli.do_create("job1 5")
    self.assertRegex(self.cli.stdout.dump(), "at least one set")

  def testCreateWithInvalidCount(self):
    self.cli.do_create("job1 -1 a.gcode,a,3)")
    self.assertRegex(self.cli.stdout.dump(), "Job count must be")
    
    self.cli.do_create("job1 1 a.gcode,a,0")
    self.assertRegex(self.cli.stdout.dump(), "Set.*count must be at least 1")

  def testMove(self):
    self.cli.do_join("local q2")
    self.cli.do_create("job1 1 a.gcode,a,1")
    self.cli.stdout.dump()
    self.cli.do_mv("job1 default q2")
    self.assertRegex(self.cli.stdout.dump(), "Moved")
    with self.assertRaises(LookupError):
      queries.getJob("default", "job1")
    self.assertNotEqual(queries.getJob("q2", "job1"), None)

  def testMoveNonExistant(self):
    self.cli.do_mv("job1 default default")
    self.assertRegex(self.cli.stdout.dump(), "No such job")

  def testMoveAcquired(self):
    self.cli.do_join("local q2")
    self.cli.do_create("job1 1 a.gcode,a,1")
    j = queries.acquireJob(queries.getJob("default", "job1"))
    self.cli.stdout.dump()
    self.cli.do_mv("job1 default q2")
    self.assertRegex(self.cli.stdout.dump(), "cannot transfer")

  def testMoveOldAcquired(self):
    self.cli.do_join("local q2")
    self.cli.do_create("job1 1 a.gcode,a,1")
    j = queries.acquireJob(queries.getJob("default", "job1"))
    j.peerLease = datetime.datetime.now() - datetime.timedelta(days=3)
    j.save()
    self.cli.stdout.dump()
    self.cli.do_mv("job1 default q2")
    self.assertRegex(self.cli.stdout.dump(), "Moved")

  def testAssignSingle(self):
    # Note: multiple assignment is handled in a different testclass as it's much more complicated   
    self.cli.do_create("job1 1 a.gcode,a,1")
    self.cli.stdout.dump()
    self.cli.do_assign("default")
    self.assertRegex(self.cli.stdout.dump(), "Assigned")
    self.assertEqual(queries.getJob("default", "job1").peerAssigned, "local")

  def testAcquireNoneAssigned(self):
    self.cli.do_acquire("")
    self.assertRegex(self.cli.stdout.dump(), "No jobs available")

  def testAcquireSingleAssigned(self):
    # Note: multiple acquire is handled in a different testclass as it's much more complicated
    self.cli.do_create("job1 1 a.gcode,a,1")
    j = queries.assignJob(queries.getJob("default", "job1"), "local")
    self.cli.stdout.dump()
    self.cli.do_acquire("")
    self.assertRegex(self.cli.stdout.dump(), "Acquired job 'default/job1'")

  def testAcquireAlreadyAcquired(self):
    self.cli.do_create("job1 1 a.gcode,a,1")
    j = queries.acquireJob(queries.getJob("default", "job1"))
    self.cli.stdout.dump()
    self.cli.do_acquire("")
    self.assertRegex(self.cli.stdout.dump(), "Acquired job 'default/job1'")

  def testReleaseNotAcquired(self):
    self.cli.do_release("")
    self.assertRegex(self.cli.stdout.dump(), "No job")
  
  def testRelease(self):
    self.cli.do_create("job1 1 a.gcode,a,1")
    j = queries.acquireJob(queries.getJob("default", "job1"))
    self.cli.stdout.dump()
    self.cli.do_release("")
    self.assertRegex(self.cli.stdout.dump(), "Released job")
    self.assertEqual(queries.getJob("default", "job1").peerLease, None)

  def testReleaseMultipleAcquired(self):
    self.cli.do_create("job1 1 a.gcode,a,1")
    self.cli.do_create("job2 1 a.gcode,a,1")
    j = queries.acquireJob(queries.getJob("default", "job1"))
    j = queries.acquireJob(queries.getJob("default", "job2"))
    self.cli.stdout.dump()
    self.cli.do_release("")
    self.assertRegex(self.cli.stdout.dump(), "Released job 'default/job1'")


class TestComplexAcquireAssign(unittest.TestCase):
  def setUp(self):
    pass

  def testAcquireMultiJob(self):
    pass

  def testAssignMultiJob(self):
    pass

class TestQueryCommands(unittest.TestCase):

  class FakeSrv:
    def getQueue(self, queue):
      return True

  def setUp(self):
    self.tmpdir = tempfile.TemporaryDirectory()
    init_db(self.tmpdir.name, initial_data_path = None)
    self.cli = Shell()
    self.cli.attach(self.FakeSrv())

  def tearDown(self):
    # Trigger teardown of temp directory
    with self.tmpdir as t:
      pass

  def testFilesNone(self):
    self.cli.do_files('local')
    self.assertRegex(self.cli.stdout.dump(), "0 File")

  def testFilesNoSuchPeer(self):
    self.cli.do_files("definitelynotapeer")
    self.assertRegex(self.cli.stdout.dump(), "0 File")

  def testQueuesNoQueues(self):
    self.cli.do_queues("")
    self.assertRegex(self.cli.stdout.dump(), "0 Queue")

  def testPrintersNoPeers(self):
    self.cli.do_printers("default")
    self.assertRegex(self.cli.stdout.dump(), "0 Printer")
    pass

  def testJobsNoJobs(self):
    queries.addQueue("testqueue", NetworkType.NONE)
    self.cli.do_jobs("testqueue")
    self.assertRegex(self.cli.stdout.dump(), "0 Job")

  def testFiles(self):
    queries.syncFiles("somebody", "anybody", {"hash1":"path1", "hash2":"path2"})
    self.cli.do_files("anybody")
    self.assertRegex(self.cli.stdout.dump(), "hash1")

  def testQueues(self):
    queries.addQueue("testqueue", NetworkType.NONE)
    self.cli.do_queues("")
    self.assertRegex(self.cli.stdout.dump(), "testqueue")

  def testJobs(self):
    queries.addQueue("testqueue", NetworkType.NONE)
    queries.createJob("testqueue", {"name": "job1", "count": 1, "sets": [{"path": "a.gcode", "hash_": "hash", "material": "a", "count": 1}]})
    self.cli.do_jobs("testqueue")
    self.assertRegex(self.cli.stdout.dump(), "job1")

if __name__ == "__main__":
  unittest.main()
