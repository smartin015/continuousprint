import time

class Supervisor:
  def __init__(self, queries, queueName):
    self.queue = queueName
    self.queries = queries
    self.assigned = None
    self.run = None

  def get_assignment(self):
    if self.assigned is not None:
      return self.assigned

    # Need to loop over jobs first to maintain job order
    for job in self.queries.getJobsAndSets(q=self.queue, lexOrder=True):
      for set_ in job.sets:
        if set_.remaining > 0:
          self.assigned = set_
          return self.assigned

  def begin_assignment(self):
    s = self.get_assignment()
    if a is not None:
      self.run = self.queries.beginRun(s)

  def end_assignment(self, result):
    if self.run is not None:
      self.queries.endRun(self.run, result)
      self.run = None

  def elapsed(self, now=None):
    if now is None:
      now = time.time()
    if self.run is not None:
      return now - self.run.start
