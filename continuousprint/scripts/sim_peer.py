from peerprint.lan_queue import LANPrintQueue
import logging
import sys
import time
from random import random

logging.basicConfig(level=logging.DEBUG)


class IdlePeer:
    def __init__(self, ns, addr, port):
        self._logger = logging.getLogger(addr)
        self.q = LANPrintQueue(ns, addr, self.ready, self._logger)

    def ready(self, q):
        logging.info(f"Setting base peer state for {q.ns}")
        q.q.syncPeer(status="IDLE", run=None)

    def spinForWork(self):
        while True:
            time.sleep((1 + random.random()) * 5)


class SimPeer:
    def __init__(self, ns, addr, port):
        self._logger = logging.getLogger(addr)
        self.q = LANPrintQueue(ns, addr, self.ready, self._logger)

    def ready(self, q):
        logging.info(f"Setting base peer state for {q.ns}")
        q.q.syncPeer(status="IDLE", run=None)

    def spinForWork(self):
        while True:
            time.sleep((1 + random.random()) * 5)


if __name__ == "__main__":
    ns = sys.argv[1]
    port = int(sys.argv[3])

    print(f"Connecting to '{ns}', port {port_start}")

    qs = []
    for port in range(port_start, port_start + npeers):
        addr = f"localhost:{port}"
        print(f"Creating peer {addr}")
        qs.append(LANPrintQueue(ns, addr, peer_ready, logging.getLogger(addr)))

    input("Press any key to end")
