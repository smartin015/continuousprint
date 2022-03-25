# TODO https://github.com/bakwc/PySyncObj
# TODO https://github.com/cr0hn/PyDiscover
from pysyncobj import SyncObj, SyncObjConf, replicated, FAIL_REASON
from print_queue import AbstractPrintQueue, QueueItem
from networking.scheduler import assign_jobs_to_printers
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
# Queue items are distributed by an elected leader.
# Files are also fetched from other members as needed
class LANPrintQueue(SyncObj, AbstractPrintQueue):
  def __init__(self, name, addr, peers, ready_cb, logger):
    self._logger = logger
    self.name = name
    self.addr = addr
    self.peer_addrs = peers
    self.ready_cb = ready_cb

    conf = SyncObjConf(onReady=self._onReady, dynamicMembershipChange=True)
    super(LANPrintQueue, self).__init__(addr, peers, conf)
    self.__files = defaultdict(dict) # {[md5]: {addr: path}}
    self.__queue = []
    self.__peers = {}

  def _onReady(self):
    self.ready_cb(self.name)

  @replicated
  def _syncPeer(self, addr, state):
    self.__peers[addr] = state
  
  @replicated  
  def _syncQueue(self, queue):
    self.__queue = queue
 
  @replicated
  def _syncFiles(self, addr, files):
    for checksum, mapping in self.__files.items():
      if files.get(checksum) is None:
        # Delete missing
        if mapping.get(addr) is not None:
          del mapping[addr]
      else:
        # Upsert present
        mapping[addr] = files[checksum]

  def setPeerState(self, addr, state):
    self.__peers[addr] = state
    self._syncPeer(addr, state)
    self._set_assignment(self.assign_jobs_to_printers(jobs, printers))

  def registerFiles(self, files):
    self._syncFiles(self.addr, files)

  def _set_assignment(self, assignment):
    for peer, job in assignment.items():
      self.__peers[peer]['job'] = job
    self._syncPeer(self, self.addr, self.__peers[peer])

  def pushJob(self, item):
    self.__queue.append(item)
    self._syncQueue(self.__queue)
    print("queue:", self.__queue)

  def queueMemberChangeCallback(self, result, error):
    if error != FAIL_REASON.SUCCESS:
      print("membership change error:", result, error)

  def addPeer(self, addr):
    self.addNodeToCluster(addr, callback=self.queueMemberChangeCallback)

  def removePeer(self, addr):
    self.removeNodeFromCluster(addr, callback=self.queueMemberChangeCallback)

  def getAssignedJob(self):
    # TODO better than linear
    assigned = self.__peers[self.name].assigned_job
    for (i, job) in enumerate(self.__queue):
      if job.id == assigned:
        return job, i

  def startActiveItem(self, **kwargs):
    job, idx = self.getAssignedJob()
    self.__queue[idx].started = time.time()
    self.__peers[self.name].active_job = job.id

  def getActiveItem(self) -> Optional[QueueItem]:
    job = self.getAssignedJob()
    for (i, item) in enumerate(job.items):
      if item.end_ts is None:
        return item, i

  def completeActiveItem(self, result, end_ts = int(time.time())):
    item, idx = self.getCurrentItem()
    item.end_ts = int(time.time())
    item.result = result
    self.__queue[idx] = item

  def getNext(self) -> Optional[QueueItem]:
    raise Exception("Unimplemented")

  def setAssignedJobCompleted(result):
    job, idx = self.getAssignedJob()
    job.completed = time.time()
    job.result = result
    self.__queue[idx] = job
    self.__peers[self.name].active_job = None

class AutoDiscoveryLANPrintQueue(AbstractPrintQueue, P2PDiscovery):
  def __init__(self, namespace, addr, ready_cb, logger):
    super().__init__(namespace, addr)
    self._logger = logger
    self.ready_cb = ready_cb
    self.q = None
    self._logger.info(f"Starting discovery")
    self.t = threading.Thread(target=self.spin, daemon=True)
    self.t.start()

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
    self.q = LANPrintQueue(self.namespace, self.addr, results.keys(), self.ready_cb, self._logger)

  def pushJob(self, item):
    self.q.pushJob(item)

  def startActiveItem(self, **kwargs):
    return self.q.startActiveItem(kwargs)

  def getActiveItem(self) -> Optional[QueueItem]:
    return self.q.getActiveItem()

  def completeActiveItem(self, result, end_ts = int(time.time())):
    return self.q.completeActiveItem(result, end_ts)

  def getNext(self) -> Optional[QueueItem]:
    return self.q.getNext()

  def registerFiles(self, files):
    self.q.registerFiles(files)



def main():
    logging.basicConfig(level=logging.DEBUG)
    import sys
    if len(sys.argv) != 3:
        print('Usage: lan_queue.py [namespace] [selfHost:port]')
        sys.exit(-1)

    def ready_cb():
      logging.info("Queue ready")

    state = {"state": "OPERATIONAL", "file": "test.gcode", "time_left": 3000}
    lpq = AutoDiscoveryLANPrintQueue(sys.argv[1], sys.argv[2], ready_cb, logging.getLogger("lpq"))
    while True:
      cmd = input(">> ").split()
      lpq.pushJob({"name": cmd[0], "queuesets": [{"name": 'herp.gcode', 'count': 2}], "count": 2})

if __name__ == "__main__":
  main()
