from storage.database import FileHash, Queue, Job, Set, Material
from typing import Optional

def addFileWithHash(path: str, hash_: str):
  FileHash.replace(path=path, hash_=hash_).execute()

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

def getJobs(namespace):
  return (Job.select()
          .join(Queue).where(Queue.namespace == namespace)
          .join(Set, on=(Set.job == Job.id))
  )
