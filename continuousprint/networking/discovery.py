import socket
import random
import select
import time

class P2PDiscovery:
  def __init__(self, namespace, advertise_addr, min_broadcast_pd=5, ttl=20):
    self.namespace = namespace
    self.ttl = ttl
    self.min_broadcast_pd = min_broadcast_pd
    self.addr = advertise_addr
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #, socket.IPPROTO_UDP)

    # Enable port reusage so we will be able to run multiple clients and servers on single (host, port). 
    # Do not use socket.SO_REUSEADDR except you using linux(kernel<3.9): goto https://stackoverflow.com/questions/14388706/how-do-so-reuseaddr-and-so-reuseport-differ for more information.
    # For linux hosts all sockets that want to share the same address and port combination must belong to processes that share the same effective user ID!
    # So, on linux(kernel>=3.9) you have to run multiple servers and clients under one user to share the same (host, port).
    # Thanks to @stevenreddie
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    self.sock.bind(("", 37020))
    self.sock.settimeout(0.2)

    self.host_timestamps = {}
  
  def _handlePing(self, host, ts):
    if host == self.addr:
      return # Don't count our own host in the list of peers
    # Filter all hosts that haven't contacted us in the TTL
    if self.host_timestamps.get(host) is None:
      self._on_host_added(host)
      self.next_broadcast = 0 # Get the new host up to speed quickly
    self.host_timestamps[host] = ts
  
  def _prune(self, ts):
    removed = []
    for (k,v) in self.host_timestamps.items():
      if ts > v+self.ttl:
        removed.append(k)
    for k in removed:
      del self.host_timestamps[k]
      self._on_host_removed(k)

  def _on_host_added(self, host):
    pass

  def _on_host_removed(self, host):
    pass

  def _on_startup_complete(self, results):
    pass

  def destroy(self):
    self.running = False

  def spin(self):
    startup = time.time()
    self.running = True
    while self.running:
      ts = time.time()

      # We should have received all hosts actively broadcasting on the network basically 
      # instantaneously with rebroadcasts, but wait a bit just in case
      if startup is not None and ts > startup+self.min_broadcast_pd/2:
        self._on_startup_complete(self.host_timestamps)
        startup = None

      self.sock.sendto(f"{self.namespace}|{self.addr}".encode(), ('<broadcast>', 37020))
      self.next_broadcast = ts + self.min_broadcast_pd * (1 + random.random())
      self._prune(ts)
      while ts < self.next_broadcast:
        ts = time.time()
        read_sockets, write_sockets, error_sockets = select.select([self.sock], [], [], 0.2)
        if len(read_sockets) > 0:
          #incoming message from remote server
          data = read_sockets[0].recv(4096)
          if data.startswith(self.namespace.encode()):
            data = data.decode("utf8").split("|")[1]
            self._handlePing(data, ts)

if __name__ == "__main__":
  import sys
  
  class BasicDiscovery(P2PDiscovery):
    def _on_host_added(self, host):
      print("ADD:", host)

    def _on_host_removed(self, host):
      print("RM:", host)

    def _on_startup_complete(self, results):
      print("START:", results)

  if len(sys.argv) != 3:
    sys.stderr.write("Usage: python3 discover.py [namespace] [address:port]\n")
    sys.exit(1)

  b = BasicDiscovery(sys.argv[1], sys.argv[2])
  print("Starting discovery")
  b.spin()
  

