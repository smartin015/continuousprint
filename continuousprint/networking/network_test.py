import unittest
from parameterized import parameterized

Intrinsics = namedtuple("printer_intrinsics", [
  "p_printer_failure", 
  "p_filament_failure", 
  "p_spaghetti",
])

class MockNetworkPrinter:
  def __init__(self, name, sched, constraints, cur, elapsed, intrinsics):
    self.name = name
    self.sched = sched
    self.constraints = constraints
    self.cur = cur
    self.elapsed = elapsed

  def predict_start_time(self, p):
    t = 0
    if self.cur is not None:
      return 
    return self.started + self.cur.duration_sec

# Note: job counts are reflected in the print group section
BOX_JOB = Job([Print('box_body', 1, 50), Print('box_lid', 1, 30)])
TABLE_JOB = Job([Print('tabletop', 1, 60), Print('tabeleg', 4, 60)])

PRINT_GROUP_A = [BOX_JOB]*2 + [TABLE_JOB]*3

# TODO different starting printers
@parameterized_class(('printers'), [
  (
    MockNetworkPrinter("A", BASIC_SCHEDULE, None, None, None), 
    MockNetworkPrinter("B", BASIC_SCHEDULE, None, None, None)
  ),
])
class TestSingleNetwork:
  def setUp(self):
    self.d = Distributor(self.printers)
    self.sched = Scheduler()

  @parameterized.expand([
    ("simple", PRINT_GROUP_A),
  ])
  def testDistributePrints(self, queue):
    self.d.distribute(queue)

    # Printers should receive jobs if they can
    if len(self.d.remainder) > 0:
      for p in self.printers:
        self.assertGreater(p.queue, 0, f"Printer {p.name} queue empty, but there are leftovers: {self.d.remainder}")
    
    # TODO play through all events on the network
