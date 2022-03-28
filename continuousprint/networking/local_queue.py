from print_queue import PrintQueueInterface, QueueJob
from storage import queries

class LocalPrintQueue(PrintQueueInterface):
  def __init__(self, name, logger, peer="local"):
    self.name = name
    self.peer = peer
    self._logger = logger

  def createJob(self, job):
    queries.createJob(self.name, job)
  
  def removeJob(self, name: str):
    return queries.removeJob(self.name, name)

  def setPrinterState(self, state):
    # This method is only needed during testing to spoof peer traffic
    if self.peer == "local":
      return
    self._logger.debug("LOCAL setPrinterState({self.peer})")
    queries.syncPrinter("local", self.peer, state)

  def registerFiles(files: dict):
    # This method is only needed during testing to spoof peer traffic
    if self.peer == "local":
      return
    self._logger.debug("LOCAL registerFiles({peer}, len({len(files)})")
    queries.syncFiles("local", self.peer, files) 

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
