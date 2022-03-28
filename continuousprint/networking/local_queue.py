from print_queue import PrintQueueInterface, QueueJob
from storage import queries

class LocalPrintQueue(PrintQueueInterface):
  def __init__(self, name, logger):
    self.name = name
    self._logger = logger

  def upsertJob(self, job):
    queries.upsertJob(self.name, job)
  
  def removeJob(self, name: str):
    return queries.removeJob(self.name, name)

  def peekJob(self) -> QueueJob:
    raise NotImplementedError

  def acquireJob(self) -> QueueJob:
    raise NotImplementedError

  def releaseJob(self, result: str):
    raise NotImplementedError

  def runAssignment(self):
    # Note: this shouldn't require running in a transaction, as the queue is local (no peers know about it)
    # This follows a sequential queue strategy - TODO allow for DP-based ordering strategy
    jobs = queries.getJobs(self.name, lexOrder=True)

    candidate = None
    for j in jobs:
      # Don't mess with assignment if one has been leased
      if j.peerLease is not None:
        return j
    
      # Find the first uncompleted job.
      if not candidate and j.result not in ('success', 'failure'): 
        candidate = j
        # Don't break out here so we can continue to check for pre-assignment

    if candidate is not None:
      queries.assignJob(candidate, 'local')
    return candidate
