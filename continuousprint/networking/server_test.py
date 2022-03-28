import unittest
from networking.server import Server, Shell
import logging
from storage.database import Job, init as init_db

logging.basicConfig(level=logging.DEBUG)

class TestServerLocalOnlyInstance(unittest.TestCase):
  srv = None

  def setUp(self):
    if self.srv is None:
      self.srv = Server('networking/testdata/unittest_solo/', 6700, logging.getLogger("server"), clear_data=True)
      self.cli = Shell()
      self.cli.attach(self.srv)
    # Remove any existing jobs - faster and less noisy than creating srv from scratch every time
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
    self.assertEqual(self.cli.stdout.dump(), "Removed job1 from default\n")

  def testCreateAlreadyExists(self):
    self.cli.do_create("job1 5 a.gcode,a,3 b.gcode,b,1")
    self.cli.stdout.dump()
    self.cli.do_create("job1 1 a.gcode,a,3")
    self.assertEqual(self.cli.stdout.dump(), "Wat\n")
 
  def testCreateWithNoSets(self):
    pass # should fail

  def testCreateWithInvalidCount(self):
    pass # test job and set count invalid

  def testCreateWithInvalidMaterial(self):
    pass

  def testMoveLocalToLan(self):
    pass

  def testMoveLanToLocal(self):
    pass

  def testMoveAcquired(self):
    pass # should fail

  def testMoveOldAcquired(self):
    pass # past acquired date should succeed

  def testAssignSingle(self):
    pass

  def testAssignMultiple(self):
    pass

  def testAcquireNoneAssigned(self):
    pass

  def testAcquire(self):
    pass

  def testAcquireMultipleAssigned(self):
    pass # Second assignment should be ignored

  def testAcquireAleadyAcquired(self):
    pass

  def testReleaseNotAcquired(self):
    pass
  
  def testRelease(self):
    pass

  def testReleaseMultipleAcquired(self):
    pass


class TestQueryCommands(unittest.TestCase):

  def setUp(self):
    self.tmpdir = tempfile.TemporaryDirectory()
    init_db(self.tmpdir.name, initial_data_path = None)

  def testFilesNone(self):
    pass

  def testFilesNoSuchPeer(self):
    pass

  def testFiles(self):
    pass
  
  def testQueuesNoQueues(self):
    pass

  def testQueues(self):
    pass

  def testPrintersNoPeers(self):
    pass

  def testJobs(self):
    pass

  def testJobsNoJobs(self):
    pass

if __name__ == "__main__":
  unittest.main()
