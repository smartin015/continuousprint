# TODO https://github.com/bakwc/PySyncObj
# TODO https://github.com/cr0hn/PyDiscover
from networking.lan_queue import LANPrintQueue
from networking.local_queue import LocalPrintQueue
from networking.filesharing import FileShare
from print_queue import PrintQueueInterface, QueueJob
from storage.database import init as db_init, NetworkType
from storage import queries
import logging
import os
import cmd
import yaml

class LocalFileManager:
  # This class matches methods of
  # https://docs.octoprint.org/en/master/modules/filemanager.html#module-octoprint.filemanager.storage

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
      self._pqs = {}
      self.next_port = start_port
      for q in queries.getQueues():
          if q.network_type == 1:
            # Local queue
            self._logger.info(f"Initializing local queue {q.name}")
            self._pqs[q.name] = LocalPrintQueue(q.name, logging.getLogger(q.name))
          if q.network_type == 2:
            # LAN queue
            self.join(q.name)
    
    # =========== Network administrative methods ===========

    def _queue_ready(self, queue: str):
      s = queries.getPrinterStates()
      if s is not None:
        self._logger.info("Sending printer state")
        self._pqs[queue].q.setPrinterState(s[0].as_dict())

    def join(self, queue: str):
      self._logger.info(f"Initializing network queue '{queue}'")
      queries.addQueue(queue, NetworkType.LAN)
      self._pqs[queue] = LANPrintQueue(
          queue, f"localhost:{self.next_port}", self._queue_ready, self._fs, logging.getLogger(queue))
      self.next_port += 1

    def leave(self, queue: str):
      self._logger.info(f"Leaving network queue '{queue}'")
      queries.removeQueue(queue)
      self._pqs[queue].destroy()
      del self._pqs[queue]

    def getQueue(self, queue:str) -> PrintQueueInterface:
      return self._pqs.get(queue)

    # ========= Job related methods ===========

    def _resolveFile(self, queue: str, path: str, hash_: str) -> str:
      local = self._fs.resolveHash(hash_)
      if local is not None:
        return local
      
      for url in self._pqs[queue].q.lookupFileURLByHash(hash_):
        if self._fs.downloadFile(url):
          break
      return self._fs.resolveHash(hash_)

    def acquireJob(self, cb):
      # This method looks through the available work, then claims the job of best fit.
      # All relevant files are downloaded once the job has been claimed and before cb() is invoked.
      raise Exception("Unimplemented")

    
    def releaseJob(self, result):
      # This method release the previously acquired job
      raise Exception("Unimplemented")



class Shell(cmd.Cmd):
    intro = 'Type help to list commands. Ctrl+C to exit\n'
    prompt = '>> '

    def log(self, s):
      self.stdout.write(s + "\n")

    def validQueue(self, queue):
      if self.server.getQueue(queue) is None:
        self.log(f"No such queue '{queue}'")
        return False
      return True

    # ====== Network commands =====
 
    def do_join(self, arg):
      'Join a LAN queue: queue'
      self.server.join(arg)
      self.log(f"joined {arg}")

    def do_leave(self, arg):
      'Leave a LAN queue: queue'
      if self.validQueue(arg):
        self.server.leave(arg)
        self.log(f"left {arg}")

    # ====== Job commands ======

    def do_create(self, arg):
      'Create a job on the local (default) queue: jobname count file1,mat1,count1 file2,mat2,count2'
      cmd = arg.split()
      sets = [tuple(c.split(',') for c in cmd[2:])]
      self.server.getQueue('default').addJob(name=cmd[0], count=cmd[1], sets=sets)
      self.log(f"Added job {name}")

    def do_move(self, arg):
      'Move a job from one queue to another: jobname from_queue to_queue. Use to_queue="delete" to delete'
      job, queue = arg.split(' ', 1)
      if self.validQueue(queue):
        self.server.submitJob(job, queue)

    def do_claim(self, arg):
      'Claim the next best job out of all queues'
      job = self.server.startNextJob()
      self.log(f"Started job '{job.name}'")

    def do_finish(self, arg):
      'Complete the next job: result (one of [success, failure, cancelled])'
      if arg not in ("success", "failure", "cancelled"):
        self.log(f"Invalid result status: {arg}. Must be one of [success, failure, cancelled]")
      else:
        job = self.server.completeCurrentJob(arg)
        self.log(f"Completed job '{job.name}' with status '{arg}'")
 
    # ===== Database and inmemory (network queue) getters =====

    def do_files(self, arg):
      'Print list of files and hashes in queue: queue'
      if arg == "default":
        files = queries.getFiles()
      else:
        sq = self.server.getQueue(arg)
        files = sq.q.getFiles()
      self.log(f"=== Files in queue '{arg}' ===")
      for p, val in files.items():
        self.log(f"{p}\n\t{val}\n")

    def do_schedule(self, arg):
      'Run job scheduling on queue: queue'
      if self.validQueue(arg):
        self.log("UNIMPLEMENTED")
 
    def do_queues(self, arg):
      'Print current queue details'
      self.log("=== Queues: ===")
      for q in queries.getQueues():
        self.log(f"name={q.name}, network_type={q.network_type}")

    def do_printers(self, arg):
      'Print printers managing queue: queue'
      if self.validQueue(arg):
        printers = queries.getPrinterStates(arg)
        self.log(f"=== {len(printers)} printers: ===")
        for p in printers:
          self.log(str(p.as_dict()))

    def do_jobs(self, arg):
      'List jobs in a queue: queue'
      self.log(f"=== Jobs for queue '{arg}' ===")
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
    parser.add_argument('--debug', action='store_true', help='Enable debug socket (address given by server.yaml)')
    
    args = parser.parse_args()

    with open(os.path.join(args.base_dir, "server.yaml"), 'r') as f:
      data = yaml.safe_load(f.read())

    logging.debug(f"start port: {data['start_port']}")
    server = Server(args.base_dir, int(data['start_port']), logging.getLogger("server"))

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
