from print_queue import PrintQueueInterface, QueueJob
from storage import queries

class LocalPrintQueue(PrintQueueInterface):
  def __init__(self, name, logger):
    self.name = name
    self._logger = logger

  def addJob(self, job: QueueJob):
    queries.addJob(self.name, job)
  
  def removeJob(self, name: str) -> QueueJob:
    return queries.removeJob(self.name, name).as_dict()

  def peekJob(self) -> QueueJob:
    raise Exception("Unimplemneted")

  def acquireJob(self) -> QueueJob:
    raise Exception("Unimplemneted")

  def releaseJob(self, result: str):
    raise Exception("Unimplemented")

