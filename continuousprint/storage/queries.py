from storage.database import FileHash, Queue, Job, Set, Material, PrinterState, PrinterProfile, Schedule, Period, NetworkType, DB
from typing import Optional
from print_queue import QueueJob

def getPathWithhash(hash_: str) -> Optional[str]:
  result = FileHash.get(hash_=hash_)
  if result is None:
    return None
  return result.path

def getFiles() -> dict:
  result = {}
  for fh in FileHash.select():
    result[fh.hash_] = fh.path
  return result

def getQueues():
  return Queue.select()

def addQueue(name, network_type: NetworkType):
  Queue.replace(name=name, network_type=network_type).execute()

def removeQueue(name):
  q = Queue.get(name=name)
  q.delete_instance()

def getJobs(queue) -> QueueJob:
  cursor = (Job.select()
          .join(Queue).where(Queue.name == queue)
          .join(Set, on=(Set.job == Job.id))
  )
  return (QueueJob(c) for c in cursor)

def upsertJob(queue, data: dict):
  q = Queue.get(name=queue)
  Job.replace(queue=q, **data).execute()

def removeJob(queue, name):
  job = Job.select().join(Queue).where(Queue.name == queue and Job.name == name).get()
  job.delete_instance()
  return job

def getPrinterStates(queue='default'):
  return PrinterState.select().where(PrinterState.queue==queue).prefetch(PrinterProfile, Schedule, Period)

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
  pass

if __name__ == "__main__":
  import sys
  from storage.database import init as db_init
  db_init(sys.argv[1])
  s = getPrinterState()
  print("Printer state:")
  print(s.as_dict())
