from storage.database import FileHash, Queue, Job, Set, Material, PrinterState, PrinterProfile, Schedule, Period, NetworkType, DB
from typing import Optional
from print_queue import QueueJob
import datetime

def getPathWithhash(hash_: str) -> Optional[str]:
  result = FileHash.get(hash_=hash_)
  if result is None:
    return None
  return result.path

def getHashes(peer: str) -> dict:
  result = {}
  for fh in FileHash.select().where(FileHash.peer == peer):
    result[fh.path] = fh.hash_
  return result

def getFiles(peer: str) -> dict:
  result = {}
  for fh in FileHash.select().where(FileHash.peer == peer):
    result[fh.hash_] = fh.path
  return result

def getQueues():
  return Queue.select()

def addQueue(name, network_type: NetworkType):
  Queue.replace(name=name, network_type=network_type).execute()

def removeQueue(name):
  q = Queue.get(name=name)
  q.delete_instance()

def getJobs(queue, lexOrder=False):
  q = Queue.get(name=queue)
  if q is None:
    return []
  cursor = Job.select().where(Job.queue == q)
  if lexOrder:
    cursor.order_by(Job.lexRank.asc())
  return cursor.prefetch(Set)

def createJob(queue, data: dict):
  lut = getHashes('local')

  if '/' in data['name']:
    raise ValueError("createJob requires no forward slashes ('/') in job names")
  elif len(data['sets']) <= 0:
    raise ValueError("job must contain at least one set")
  elif int(data['count']) <= 0:
    raise ValueError(f"Job count must be at least 1")

  with DB.queues.atomic() as txn:
    q = Queue.get(name=queue)
    j = Job.create(
      queue=q,
      lexRank="0",
      name=f"{queue}/{data['name']}",
      count=int(data['count']),
      )

    for s in data['sets']:
      if not s.get('hash_'):
        s['hash_'] = lut[s['path']]
      if int(s['count']) <= 0:
        raise ValueError(f"Set {s['path']} count must be at least 1")
      Set.create(path=s['path'], hash_=s['hash_'], material_key=s['material'], count=int(s['count']), job=j)

def getJob(queue, name):
  q = Queue.get(name=queue)
  j = Job.select().where(Job.queue==q and Job.name==f"{queue}/{name}").prefetch(Set)
  if len(j) > 0:
    return j[0]
  raise LookupError(f"No such job {name} in queue {queue}")

def removeJob(queue, name):
  job = getJob(queue, name)
  if job.peerLease is not None and job.peerLease > datetime.datetime.now():
    raise ValueError(f"Job {name} is under lease; cannot transfer")
  job.delete_instance(recursive=True)
  return job

def transferJob(queue, name, dest):
  q = Queue.get(name=dest)
  job = getJob(queue, name)
  if job.peerLease is not None and job.peerLease > datetime.datetime.now():
    raise ValueError(f"Job {name} is under lease; cannot transfer")

  # Reset all state variables
  job.peerAssigned = None
  job.peerLease = None
  job.ageRank = 0
  job.result = None
  
  # Job name must also change to remain unique
  job.name = f"{dest}/{name}"

  job.queue = q
  job.save()

def releaseJob(queue, name, result):
  job = _getJob(queue, name)
  job.result = result
  job.peerAssigned = None
  job.peerLease = None
  job.save()

def getLoadedMaterials():
  return Material.select().where(Material.loaded == True)

def getPrinterStates(queue='default', peer=None):
  cursor = PrinterState.select()
  if peer is None:
    cursor = cursor.where(PrinterState.queue==queue)
  else:
    cursor = cursor.where(PrinterState.queue==queue and PrinterState.peer == peer)
  return cursor.prefetch(PrinterProfile, Schedule, Period)
  

def syncPrinter(addr: str, peer: str, state: dict):
  # TODO handle schedule / profile foreign key resolution
  # localhost:6750 localhost:6750 {'name': 'Creality CR30', 'model': 'CR30', 'width': 200.0, 'depth': 1000.0, 'height': 200.0, 'formFactor': 'rectangular', 'selfClearing': True, 'schedule': {'name': 'default', 'periods': [(1648339744, 28800, 2), (1648426144, 28800, 2), (1648454944, 28800, 4), (1648512544, 28800, 2), (1648627744, 28800, 4)]}, 'status': 'UNKNOWN'}
  with DB.states.atomic() as txn:
    pp_kwargs = dict([(k,v) for (k,v) in state.items() if hasattr(PrinterProfile, k) and k != 'peer'])
    pp = PrinterProfile.replace(peer=peer, **pp_kwargs).execute()
    
    # Blows away old schedule and periods
    sname = state['schedule']['name']
    Schedule.delete().where(Schedule.peer == peer and Schedule.name == sname)

    s = Schedule.create(peer=peer, name=sname)
    for (ts, d, v) in state['schedule']['periods']:
      Period.create(schedule=s, timestamp_utc=ts, duration=d, max_manual_events=v)

    ps_kwargs = dict([(k,v) for (k,v) in state.items() if hasattr(PrinterState, k) and k != 'peer'])
    PrinterState.replace(peer=peer, queue=state['queue'], profile=pp, schedule=s, status=state['status']).execute()

def syncFiles(addr: str, peer: str, files: dict, remove=True):
  if peer == addr: # We already know our own files
    return

  with DB.files.atomic() as txn:
    # Remove any missing files from list
    for fh in FileHash.select().where(FileHash.peer == peer):
      if files.get(fh.hash_) is None:
        if remove:
          fh.delete_instance()
      else:
        # No need to add; already exists
        del files[fh.hash_]

    # Upsert new files
    for (hash_, path) in files.items():
      FileHash.create(peer=peer, hash_=hash_, path=path)

def syncAssigned(queue:str, assignment):
  with DB.queues.atomic() as txn:
    q = Queue.get(name=queue)
    now = datetime.datetime.now()
    Job.update(peerAssigned=None).where(Job.queue == q and Job.peerLease < now)
    for (peer, name) in assignment.items():
      j = Job.get(queue=q, name=name)
      j.peerAssigned = peer
      j.save()
  
def getAssigned(peer):
  return Job.select().where(Job.peerAssigned == peer).prefetch(Queue, Set)

def getSchedule(peer):
  return Schedule.select().where(Schedule.peer == peer).limit(1).prefetch(Period)

def assignJob(job, peer):
  job.peerAssigned = peer
  job.result = None
  job.save()

def acquireJob(job, duration=60*60):
  job.peerLease = datetime.datetime.now() + datetime.timedelta(seconds=duration)
  job.result = None
  job.save()
  return job

def getAcquired():
  cursor = Job.select().where(Job.peerLease > datetime.datetime.now()).limit(1).prefetch(Queue, Set)
  if len(cursor) > 0:
    return cursor[0]

def releaseJob(job, result):
  job.result = result
  job.peerLease = None
  job.save()
  return job

if __name__ == "__main__":
  import sys
  from storage.database import init as db_init
  db_init(sys.argv[1])
  s = getPrinterState()
  print("Printer state:")
  print(s.as_dict())
