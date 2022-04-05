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
    return queries.runSimpleAssignment(self.name, self.peer, self._logger)
