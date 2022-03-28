# TODO https://github.com/bakwc/PySyncObj
# TODO https://github.com/cr0hn/PyDiscover
from pysyncobj import SyncObj, SyncObjConf, replicated, FAIL_REASON
from print_queue import PrintQueueInterface, QueueJob
from storage import queries
from networking.discovery import P2PDiscovery
from typing import Optional
from collections import defaultdict
from dataclasses import dataclass
import threading
import logging
import random
import time
import json

# This queue is shared with other printers on the local network which are configured with the same namespace.
# Actual scheduling and printing is done by the object owner.
#
# Queue state is synchronized back to the storage system, to allow for multi-queue queries
class LANPrintQueueBase(SyncObj):
  def __init__(self, name, addr, peers, ready_cb, logger):
    self._logger = logger
    self.name = name
    self.addr = addr
    self.ready_cb = ready_cb
    conf = SyncObjConf(onReady=self.ready_cb, dynamicMembershipChange=True)
    super(LANPrintQueueBase, self).__init__(addr, peers, conf)

  # ==== Network methods ====

  def addPeer(self, addr):
    self.addNodeToCluster(addr, callback=self.queueMemberChangeCallback)

  def removePeer(self, addr):
    self.removeNodeFromCluster(addr, callback=self.queueMemberChangeCallback)
    # TODO Clean up peer state

  def queueMemberChangeCallback(self, result, error):
    if error != FAIL_REASON.SUCCESS:
      self._logger.error(f"membership change error: {result}, {error}")

  # ==== Hooks to save to storage ====

  @replicated
  def _syncPrinter(self, peer, state):
    self._logger.debug(f"@replicated _syncPrinter({peer}, _)")
    queries.syncPrinter(self.addr, peer, state)
  
  @replicated  
  def _upsertJob(self, job):
    self._logger.debug(f"@replicated _upsertJob {job}")
    queries.upsertJob(self.name, job)

  @replicated
  def _removeJob(self, peer, name: str):
    if peer == self.name:
      return # Local removal is handled by caller
    self._logger.debug("@replicated _removeJob")
    queries.removeJob(self.name, name)
 
  @replicated
  def _syncFiles(self, peer, files):
    self._logger.debug(f"@replicated _syncFiles({peer}, len({len(files)}))")
    queries.syncFiles(self.addr, peer, files)

  @replicated
  def _syncAssigned(self, assignment):
    self._logger.debug(f"@replicated _syncAssigned()")
    queries.syncAssigned(self.addr, self.name, assignment)

  # ==== Mutation methods ====

  def setPrinterState(self, state):
    self._syncPrinter(self.addr, state)

  def registerFiles(self, files: dict):
    self._logger.debug(f"registering files: {files}")
    self._syncFiles(self.addr, files)

  def runAssignment(self):
    # TODO validate - also return job

    assignment = None
    raise NotImplementedError
    self._syncAssigned(self, assignment)

  def upsertJob(self, job):
    self._upsertJob(job)

  def removeJob(self, name: str):
    # TODO fix desync issue if consensus fails
    self._removeJob(self.name, name)
    return queries.removeJob(self.name, name)

# Wrap LANPrintQueueBase in a discovery class, allowing for dynamic membership based 
# on a namespace instead of using a list of specific peers.
# 
# This class also handles syncing of files from a FileShare object.
class LANPrintQueue(PrintQueueInterface, P2PDiscovery):
  def __init__(self, namespace, addr, ready_cb, fileshare, logger):
    super().__init__(namespace, addr)
    self._logger = logger
    self._fs = fileshare
    self.ready_cb = ready_cb
    self.q = None
    self._logger.info(f"Starting discovery")
    self.t = threading.Thread(target=self.spin, daemon=True)
    self.t.start()

  def destroy(self):
    self._logger.info(f"Destroying discovery and SyncObj")
    super(LANPrintQueue, self).destroy()
    self.q.destroy()

  def _on_queue_ready(self):
    files = queries.getFiles("local")
    self._logger.info(f"Registering {len(files)} files")
    self.q.registerFiles(files)
    self.ready_cb(self.namespace)

  def _on_host_added(self, host):
    if self.q is not None:
      self._logger.info(f"Adding peer {host}")
      self.q.addPeer(host)

  def _on_host_removed(self, host):
    if self.q is not None:
      self._logger.info(f"Removing peer {host}")
      self.q.removePeer(host)

  def _on_startup_complete(self, results):
    self._logger.info(f"Discover end: {results}; initializing queue")
    self.q = LANPrintQueueBase(self.namespace, self.addr, results.keys(), self._on_queue_ready, self._logger)

  def addJob(self, job: QueueJob):
    pass

  def removeJob(self, name: str) -> QueueJob:
    pass
  
  def peekJob(self) -> QueueJob:
    pass

  def acquireJob(self) -> QueueJob:
    pass

  def releaseJob(self, result: str):
    pass


def main():
    logging.basicConfig(level=logging.DEBUG)
    import sys
    from storage.database import init as init_db
    if len(sys.argv) != 4:
        print('Usage: lan_queue.py [base_dir] [namespace] [selfHost:port]')
        sys.exit(-1)

    def ready_cb(namespace):
      logging.info(f"Queue ready: {namespace}")

    init_db(sys.argv[1])

    state = {"state": "OPERATIONAL", "file": "test.gcode", "time_left": 3000}
    lpq = LANPrintQueue(sys.argv[2], sys.argv[3], ready_cb, logging.getLogger("lpq"))
    while True:
      cmd = input(">> ").split()
      lpq.pushJob({"name": cmd[0], "queuesets": [{"name": 'herp.gcode', 'count': 2}], "count": 2})

if __name__ == "__main__":
  main()
