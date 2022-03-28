# TODO https://github.com/bakwc/PySyncObj
# TODO https://github.com/cr0hn/PyDiscover
from networking.lan_queue import LANPrintQueue
from networking.local_queue import LocalPrintQueue
from networking.filesharing import FileShare
from print_queue import PrintQueueInterface, QueueJob
from storage.database import init as db_init, NetworkType
from storage import queries
from peewee import IntegrityError
from networking.scheduler import JobSchedulerDP, Job as SJob, Period as SPeriod
from functools import cache
import logging
import os
import time
import cmd
import yaml
import traceback
import datetime

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

  def has_analysis(self, path):
    return True

  def get_additional_metadata(self, path):
    # TODO actual analysis
    return {'estimatedPrintTime': 10}

class Server:
    def __init__(self, data_dir, start_port, logger):
      self._logger = logger
      db_init(data_dir)
      self._lfm = LocalFileManager(os.path.join(data_dir, "gcode_files"))
      self._fs = FileShare(self._lfm, queries, logging.getLogger("filemanager"))
      self._fs.analyzeAllNew()
      self._pqs = {}
      self.next_port = start_port
      for q in queries.getQueues():
          self.join(q.network_type, q.name)
    
    # =========== Network administrative methods ===========

    def _queue_ready(self, queue: str):
      s = queries.getPrinterStates()
      if s is not None:
        self._logger.info("Sending printer state")
        self._pqs[queue].q.setPrinterState(s[0].as_dict())

    def join(self, net: NetworkType, queue: str):
      if net == NetworkType.NONE:
        self._logger.debug(f"Initializing local queue {queue}")  
        queries.addQueue(queue, NetworkType.NONE)
        self._pqs[queue] = LocalPrintQueue(queue, logging.getLogger(queue))
      elif net == NetworkType.LAN:
        self._logger.debug(f"Initializing LAN queue '{queue}'")
        queries.addQueue(queue, NetworkType.LAN)
        self._pqs[queue] = LANPrintQueue(
            queue, f"localhost:{self.next_port}", self._queue_ready, self._fs, logging.getLogger(queue))
        self.next_port += 1
      else:
        raise ValueError(f"Unsupported network type {net}")

    def leave(self, queue: str):
      self._logger.info(f"Leaving network queue '{queue}'")
      queries.removeQueue(queue)
      self._pqs[queue].destroy()
      del self._pqs[queue]

    def getQueue(self, queue:str) -> PrintQueueInterface:
      q = self._pqs.get(queue)
      if q is not None and isinstance(q, LANPrintQueue):
        q = q.q # Unwrap the queue discovery/filesystem stuff
      return q

    # ========= Job related methods ===========

    def _resolveFile(self, queue: str, path: str, hash_: str) -> str:
      local = self._fs.resolveHash(hash_)
      if local is not None:
        return local
      
      for url in self._pqs[queue].q.lookupFileURLByHash(hash_):
        if self._fs.downloadFile(url):
          break
      return self._fs.resolveHash(hash_)

    @cache
    def _estimateDuration(self, path):
      # TODO lookup file analysis 
      return 10 

    def acquireJob(self):
      # This method looks through the available work, then claims the job of best fit.
      # All relevant files are downloaded once the job has been claimed and before cb() is invoked.
      acquired = queries.getAcquired()
      if acquired is not None:
        self._logger.debug("Job already assigned - returning that one")
        acquired = queries.acquireJob(acquired) # re-acquire to refresh the lease
        return acquired

      # TODO update JobSchedulerDP to accept multi-material printer
      materials = [m.key for m in queries.getLoadedMaterials()]
      start_material = materials[0]

      assigned = queries.getAssigned('local')
      if len(assigned) == 0:
        raise LookupError("No jobs available to schedule; assign jobs first")
      elif len(assigned) == 1:
        self._logger.debug("Shortcutting scheduler - only one job to assign")
        acquired = queries.acquireJob(assigned[0])
        return acquired

      sjobs = []
      for j in assigned:
        duration = sum([self._fs.estimateDuration(s.path)*s.count for s in j.sets])
        sjobs.append(SJob(j.sets[0].material, j.materialChanges(start_material), c, d, j.ageRank))

      # There's only one local peer state
      state = queries.getPrinterStates(peer='local')[0]

      periods = [p.resolve() for p in state.schedule.periods]
      # flatten
      periods = [i for ii in periods for i in ii]
      start_ts = periods[0][0]
      spds = [SPeriod(ts - start_ts, ts - start_ts + duration, max_events) for ts,duration,max_events in periods]
      
      s = JobSchedulerDP(spds, sjobs, start_material, logging.getLogger("server:sched"))
      result = s.run()
      self._logger.debug(f"Result: {result}")
      if result is not None:
        s.debug(result[1])
        acquired = queries.acquireJob(assigned[result[1]])
        return acquired
      else:
        raise Exception("Failed to resolve schedule")

    
    def releaseJob(self, result):
      # This method release the previously acquired job
      acquired = queries.getAcquired()
      if acquired is None:
        raise LookupError("No job currently acquired")
      return queries.releaseJob(acquired, result)



class Shell(cmd.Cmd):
    intro = 'Type help to list commands. Ctrl+C to exit\n'
    prompt = '>> '

    RESULT_TYPES = ("success", "failure", "cancelled")

    class OutputCapture:
      def __init__(self):
        self.out = ""
      def write(self, s):
        self.out += s
      def dump(self):
        s = self.out
        self.out = ""
        return s

    def attach(self, server):
      self.server = server
      self.stdout = Shell.OutputCapture()
      self.use_rawinput = False

    def log(self, s):
      self.stdout.write(s + "\n")

    def validQueue(self, queue):
      if self.server.getQueue(queue) is None:
        self.log(f"No such queue '{queue}'")
        return False
      return True

    # ====== Network commands =====
 
    def do_join(self, arg):
      'Join a queue: [local|lan] name'
      typ, name = arg.split(" ")
      typ = {"local": NetworkType.NONE, "lan": NetworkType.LAN}.get(typ.lower())
      if typ is None:
        self.log(f"Invalid network type (options: local, lan)")
      else:
        self.server.join(typ, name)
        self.log(f"joined {arg}")

    def do_leave(self, arg):
      'Leave a LAN queue: name'
      if self.validQueue(arg):
        self.server.leave(arg)
        self.log(f"left {arg}")

    # ====== Job commands ======

    def do_create(self, arg):
      'Create a job on the local (default) queue: jobname count file1,mat1,count1 file2,mat2,count2'
      cmd = arg.split()
      sets = [dict(zip(('path','material','count'),c.split(','))) for c in cmd[2:]]
      try:
        self.server.getQueue('default').createJob(dict(name=cmd[0], count=cmd[1], sets=sets))
        self.log(f"Added job {cmd[0]}")
      except IntegrityError:
        self.log(f"Job with name {cmd[0]} already exists in default queue")
      except ValueError as e:
        self.log(f"ValueError: {e}")

    def do_mv(self, arg):
      'Move a job from one queue to another: jobname from_queue to_queue. Use to_queue="null" to delete'
      name, src, dest = arg.split(' ', 2)
      try:
        if dest == 'null':
          job = self.server.getQueue(src).removeJob(name)
          self.log(f"Removed {job.name} from {src}")
        elif self.validQueue(src) and self.validQueue(dest):
            queries.transferJob(src, name, dest)
            self.log(f"Moved {name} from {src} to {dest}")
      except ValueError as e:
        self.log(f"ValueError: {e}")
      except LookupError as e:
        self.log(f"LookupError: {e}")
      

    def do_assign(self, arg):
      'Compute job assignments for queue: queue'
      if self.validQueue(arg):
        j = self.server.getQueue(arg).runAssignment()
        self.log(f"Assigned job {j.name} in queue {arg}")
 
    def do_acquire(self, arg):
      'Claim the next best job out of all queues'
      try:
        job = self.server.acquireJob()
        self.log(f"Acquired job '{job.name}' from queue '{job.queue.name}'")
      except Exception:
        self.log(traceback.format_exc())

    def do_release(self, arg):
      f'Complete the next job: result (one of RESULT_TYPES or empty)'
      if arg != '' and arg not in self.RESULT_TYPES:
        self.log(f"Invalid result status: {arg}. Must be one of {self.RESULT_TYPES}")
      else:
        try:
          job = self.server.releaseJob(arg)
          self.log(f"Released job '{job.name}' with status '{arg}'")
        except LookupError as e:
          self.log(f"LookupError: {e}")
 
    # ===== Database and inmemory (network queue) getters =====

    def do_files(self, arg):
      'Print list of known files and hashes of peer: peer ("local" for local files)'
      files = queries.getFiles(arg)
      self.log(f"=== {len(files)} File(s) from peer '{arg}' ===")
      for p, val in files.items():
        self.log(f"{p}\n\t{val}\n")

    def do_queues(self, arg):
      'Print current queue details'
      qs = queries.getQueues()
      self.log(f"=== {len(qs)} Queue(s): ===")
      for q in queries.getQueues():
        self.log(f"name={q.name}, network_type={q.network_type}")

    def do_printers(self, arg):
      'Print printers managing queue: queue'
      if self.validQueue(arg):
        printers = queries.getPrinterStates(arg)
        self.log(f"=== {len(printers)} Printer(s): ===")
        for p in printers:
          self.log('\n')
          for k,v in p.as_dict().items():
            if k == 'schedule':
              self.log(f"Schedule {v['name']}:")
              for p in v['periods']:
                self.log(f"\tt={p[0]}\td={p[1]}\tn={p[2]}")
            else:
              self.log(f"{k}: {v}")

    def do_jobs(self, arg):
      'List jobs in a queue: queue'
      now = datetime.datetime.now()
      if self.validQueue(arg):
        js = queries.getJobs(arg)
        self.log(f"=== {len(js)} Job(s) for queue '{arg}' ===")
        for j in js:
          js = f"{j.name} (count={j.count})"
          if j.peerAssigned:
            js += f" assigned to {j.peerAssigned}"
            if j.peerLease is not None and j.peerLease > now:
              dt = (j.peerLease - now).total_seconds() / 60
              js += f" - leased for {dt:.1f} min"
          self.log(js)
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
      sh = Shell()
      sh.attach(server)
      context = zmq.Context()
      socket = context.socket(zmq.REP)
      logging.info(f"Starting debug REP socket at {data['debug_socket']}")
      socket.bind(data['debug_socket'])
      while True:
        msg = socket.recv_string()
        logging.debug(f"USER: {msg}")
        sh.onecmd(msg)
        socket.send_string(sh.stdout.dump())

if __name__ == "__main__":
  main()
