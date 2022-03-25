# TODO https://github.com/bakwc/PySyncObj
# TODO https://github.com/cr0hn/PyDiscover
from networking.lan_queue import AutoDiscoveryLANPrintQueue
from networking.filesharing import FileShare
from storage.database import init as db_init, upsertJobFromString
from storage import queries
import logging
import os
import cmd
import yaml

class LocalFileManager:
  def __init__(self, data_dir):
    self._datadir = data_dir

  def path_on_disk(self, path):
    return os.path.join(self._datadir, path)

  def list_files(self, ddir=None):
    if ddir is None:
      ddir = self._datadir
    result = {}
    for f in os.listdir(ddir):
      if os.path.isfile(os.path.join(ddir, f)):
        result[f] = True
      else: # Directory
        result[f] = self.list_files(os.path.join(ddir, f))
    return result

class Server:
    def __init__(self, data_dir, start_port, logger):
      self._logger = logger
      db_init(data_dir)
      self._lfm = LocalFileManager(os.path.join(data_dir, "gcode_files"))
      print(self._lfm.list_files())
      self._fs = FileShare(self._lfm, queries, logging.getLogger("filemanager"))
      self._fs.analyzeAllNew()
      self._lpqs = {}
      self.next_port = start_port
      for q in queries.getQueues():
          if q.network_type != 2:
            continue
          self.join(q.name, q.namespace)
    
    def join(self, name, namespace):
      self._logger.info(f"Initializing queue {name} (namespace '{namespace}')")
      self._lpqs[namespace] = AutoDiscoveryLANPrintQueue(
          namespace, f"localhost:{self.next_port}", self.queue_ready, logging.getLogger(f"lpq:{namespace}"))
      self.next_port += 1

    def leave(self, namespace):
      self._logger.error("UNIMPLEMENTED")

    def getNext(self):
      # Get the next best print to start, given constraints and whatnot
      self._logger.error("UNIMPLEMENTED")

    def queue_ready(self, namespace):
      print(f"TODO handle queue {namespace}")
      # Get annotated files from _fs and post them to the queue

class Shell(cmd.Cmd):
    intro = 'Type help to list commands. Ctrl+C to exit\n'
    prompt = '>> '

    def log(self, s):
      self.stdout.write(s + "\n")

    def do_create_job(self, arg):
      'Create a job on the local (default) queue: jobname count file1,mat1,count1 file2,mat2,count2'
      # lpq[0].pushJob({"name": cmd[0], "queuesets": [{"name": 'herp.gcode', 'count': 2}], "count": 2})
      self.log("UNIMPLEMENTED")

    def do_delete_job(self, arg):
      'Delete a job from the local (default) queue: jobname'
      self.log("UNIMPLEMENTED")

    def do_submit_job(self, arg):
      'Submit a job to a queue: namespace jobname. Job will be removed from the local queue'
      self.log("UNIMPLEMENTED")

    def do_claim_job(self, arg):
      'Claim a job on a lan queue: namespace jobname'
      self.log("UNIMPLEMENTED")

    def do_complete_job(self, arg):
      'Complete a job in a queue: namespace jobname result. Result can be one of [success, failure, cancelled]'
      self.log("UNIMPLEMENTED")
 
    def do_join_lan(self, arg):
      'Join a LAN queue: namespace name'
      arg = arg.split(" ", 1) 
      self.server.join(*arg)
      self.log(f"joined {arg[0]}")

    def do_leave_lan(self, arg):
      'Leave a LAN queue: namespace'
      self.server.leave(arg)
      self.log(f"left {arg}")
 
    def do_schedule(self, arg):
      'Run job scheduling on queue: namespace'
      self.log("UNIMPLEMENTED")
 
    def do_queues(self, arg):
      'Print current queues'
      self.log("=== Queues: ===")
      for q in queries.getQueues():
        self.log(f"{q.name} (ns={q.namespace}, network_type={q.network_type})")

    def do_jobs(self, arg):
      'List jobs in a queue: namespace. Leave blank for local (default) queue'
      self.log(f"=== Jobs for queue with namespace '{arg}' ===")
      for j in queries.getJobs(arg):
        self.log(f"{j.name} (count={j.count})")
        for s in j.sets:
          self.log(f"\t- {s.path} (count={s.count}, material={s.material_key})")

def main():
    logging.basicConfig(level=logging.DEBUG)
    import sys  
    import yaml
    import argparse
    import zmq

    parser = argparse.ArgumentParser(description='Start a network queue server')
    parser.add_argument('base_dir', type=str, help='path to base directory for data')
    parser.add_argument('--start_port', type=int, default=6700, help='Start of port range for queue networking')
    parser.add_argument('--debug', action='store_true', help='Enable debug socket (address given by server.yaml)')
    
    args = parser.parse_args()

    with open(os.path.join(args.base_dir, "server.yaml"), 'r') as f:
      data = yaml.safe_load(f.read())

    server = Server(args.base_dir, args.start_port, logging.getLogger("server"))

    if args.debug:
      class OutputCapture:
        def __init__(self):
          self.out = ""
        def write(self, s):
          self.out += s
        def dump(self):
          s = self.out
          self.out = ""
          return s

      oc = OutputCapture()
      sh = Shell(stdout=oc)
      sh.server = server
      sh.use_rawinput = False
      context = zmq.Context()
      socket = context.socket(zmq.REP)
      logging.info(f"Starting debug REP socket at {data['debug_socket']}")
      socket.bind(data['debug_socket'])
      while True:
        msg = socket.recv_string()
        logging.debug(f"USER: {msg}")
        sh.onecmd(msg)
        socket.send_string(oc.dump())

if __name__ == "__main__":
  main()
