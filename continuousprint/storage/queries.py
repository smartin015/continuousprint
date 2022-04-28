from peewee import IntegrityError, JOIN
from typing import Optional
from .database import Queue, Job, Set, DB
import time
import base64

def getQueues():
  return Queue.select()

def addQueue(name):
  try:
    Queue.create(name=name)
  except IntegrityError:
    return

def removeQueue(name):
  q = Queue.get(name=name)
  q.delete_instance()

def getJobsAndSets(q=None, lexOrder=False):
  if type(q) == str:
    q = Queue.get(name=q)
  if q is None:
    return []
  cursor = Job.select().join(Set, JOIN.LEFT_OUTER).where(Job.queue == q).group_by(Job.id)
  if lexOrder:
    cursor = cursor.order_by(Job.lexRank.asc())
  return cursor.execute()

def createJob(queue, data: dict):
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
      if int(s['count']) <= 0:
        raise ValueError(f"Set {s['path']} count must be at least 1")
      Set.create(path=s['path'], material_keys=s['material'], count=int(s['count']), job=j)

def getJob(queue, name):
  q = Queue.get(name=queue)
  j = Job.select().where(Job.queue==q and Job.name==name).prefetch(Set, Run)
  if len(j) > 0:
    return j[0]
  raise LookupError(f"No such job {name} in queue {queue}")

def updateJob(job_id, data, json_safe=False, queue="default"):
  try:
    j = Job.get(id=job_id)
  except Job.DoesNotExist:
    q = Queue.get(name=queue)
    j = newEmptyJob(q)
  for k,v in data.items():
    if k == "id":
      continue
    setattr(j, k, v)
  j.save()
  return j.as_dict(json_safe)

def removeJobs(jids):
  with DB.queues.atomic() as txn:
    for jid in jids:
      Job.get(id=jid).delete_instance(recursive=True)

MAX_LEX = 1000000.0 # Arbitrary
def genLex(n):
  maxval = MAX_LEX
  stride = int(maxval/(n+1)) # n+1 to allow for space at beginning
  for i in range(stride, int(maxval+1), stride):
    yield i

def lexBalance(cls):
  with DB.queues.atomic() as txn:
    lexer = genLex(cls.select().count())
    for (l, c) in zip(lexer, cls.select().order_by(cls.lexRank)):
      c.lexRank = l
      c.save()

def lexEnd():
  return time.time()

def moveSet(src_id: int, dest_id: int, job_id: int, upsert_queue='default'):
  s = Set.get(id=src_id)
  if s.job.id != job_id:
    print("set job ID", s.job.id, "not matching target job id", job_id)
    if job_id == -1:
      q = Queue.get(name=upsert_queue)
      j = newEmptyJob(queue).id
    else:
      j = Job.get(id=job_id)
    s.job = j
    s.save()
  return moveCls(Set, src_id, dest_id)

def moveJob(src_id, dest_id):
  return moveCls(Job, src_id, dest_id)

def moveCls(cls, src_id: int, dest_id: int, retried=False):
  print("moveCls src", src_id, "dest", dest_id)
  if dest_id == -1:
    destRank = 0
  else:
    print("cls.get id=", dest_id)
    destRank = cls.get(id=dest_id).lexRank
  print("destRank", destRank)
  # Get the next object/set having a lexRank beyond the destination rank,
  # so we can then split the difference
  # Note the unary '&' operator and the expressions wrapped in parens (a limitation of peewee)
  postRank = cls.select(cls.lexRank).where((cls.lexRank > destRank) & (cls.id != src_id)).limit(1).execute()
  if len(postRank) > 0:
    postRank = postRank[0].lexRank
  else:
    postRank = MAX_LEX
  print("postRank", postRank)
  # Pick the target value as the midpoint between the two lexRanks
  candidate = abs(postRank-destRank) / 2 + min(postRank, destRank)
  print("candidate", candidate)

  # We may end up with an invalid candidate if we hit a singularity - in this case, rebalance all the
  # rows and try again
  if candidate <= destRank or candidate >= postRank:
    if not retried:
      print("rebalancing")
      lexBalance(cls)
      moveCls(cls, src_id, dest_id, retried=True)
    else:
      raise Exception("Could not rebalance job lexRank to move job")
  else:
    c = cls.get(id=src_id)
    c.lexRank = candidate
    c.save()
    print("saved candidate lexrank")

def transferJob(queue, name, dest):
  q = Queue.get(name=dest)
  job = getJob(queue, name)
  job.queue = q
  job.save()

def newEmptyJob(q):
  print(type(q))
  if type(q) == str:
    q = Queue.get(name=q)
    print("Looked up q")
  return Job.create(
      queue=q,
      lexRank=lexEnd(),
      name="",
      count=1,
    )

def appendSet(queue: str, job: str, data: dict):
  q = Queue.get(name=queue)
  try:
    j = Job.get(queue=q, name=job)
  except Job.DoesNotExist:
    j = newEmptyJob(q)
    j.name = job
    j.save()

  count = int(data['count'])
  try:
    s = Set.get(path=data['path'], job=j)
    s.count += count
    s.remaining += count
    s.save()
  except Set.DoesNotExist:
    s = Set.create(
        path=data['path'],
        lexRank=lexEnd(),
        material_keys=",".join(data['material']),
        count=count,
        remaining=count,
        job=j
    )
  return dict(job_id=j.id, set_=s.as_dict(json_safe=True))

def updateSet(set_id, data, json_safe=False):
  s = Set.get(id=set_id)
  for k,v in data.items():
    if k == "id":
      continue
    setattr(s, k, v)
  s.save()
  return s.as_dict(json_safe=json_safe)

def removeSets(set_ids: list):
  with DB.queues.atomic() as txn:
    for sid in set_ids:
      Set.get(id=sid).delete_instance(recursive=True)

def beginRun(s):
  Run.create(set_=s, start=datetime.now())

def endRun(r, result: str):
  with DB.queues.atomic() as txn:
    r.end = datetime.now()
    r.result = result
    r.set_.remaining = max(r.set_.remaining - 1, 0)
    r.save()
    s.save()

def normalizeLexRanks():
  raise NotImplemented
