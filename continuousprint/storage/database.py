from peewee import Model, SqliteDatabase, CharField, DateTimeField, IntegerField, ForeignKeyField, BooleanField, FloatField, JOIN
import datetime
from enum import IntEnum, auto
import sys
import inspect
import os
import yaml
import time

# Defer initialization
class DB:
  states = SqliteDatabase(None)
  queues = SqliteDatabase(None)
  files = SqliteDatabase(None)

class Material(Model):
  key = CharField(unique=True)
  color = CharField()
  composition = CharField()
  loaded = BooleanField(default=False)
  inStock = BooleanField(default=False)
  class Meta:
    database = DB.states
    indexes = (
      # Unique index on color/composition
      (('color', 'composition'), True),
    )

class PrinterProfile(Model):
  name = CharField(unique=True)
  model = CharField()
  width = FloatField()
  depth = FloatField()
  height = FloatField()
  formFactor = str
  selfClearing = BooleanField()
  class Meta:
    database = DB.states

class PrinterState(Model):
  profile = ForeignKeyField(PrinterProfile)
  fileLoaded = CharField()
  octoprintState = CharField()
  class Meta:
    database = DB.states

class NetworkType(IntEnum):
  NONE = auto()
  LAN_DISCOVERY = auto()

class Queue(Model):
  name = CharField(unique=True)
  namespace = CharField()
  created = DateTimeField(default=datetime.datetime.now)
  network_type = IntegerField()
  class Meta:
    database = DB.queues

class Job(Model):
  name = CharField(unique=True)
  lexRank = CharField()
  queue = ForeignKeyField(Queue, backref='jobs')
  count = IntegerField(default=1)
  created = DateTimeField(default=datetime.datetime.now)
  class Meta:
    database = DB.queues
  
class Set(Model):
  path = CharField()
  material_key = CharField() # Specifically NOT a foreign key - materials are stored in a different db
  job = ForeignKeyField(Job, backref='sets')
  count = IntegerField(default=1)
  class Meta:
    database = DB.queues

class Attempt(Model):
  set_ = ForeignKeyField(Set, column_name='set', backref='attempts')
  start = DateTimeField(default=datetime.datetime.now)
  end = DateTimeField(null=True)
  result = CharField(null=True)
  class Meta:
    database = DB.queues

class FileHash(Model):
  path = CharField(unique=True)
  hash_ = CharField(index=True, column_name='hash')
  class Meta:
    database = DB.files
    

def file_exists(path: str) -> bool:
  try: 
    return os.stat(path).st_size > 0
  except OSError as error:
    return False

def init(base_dir: str, db_paths = dict(states='states.sqlite3', queues='queues.sqlite3', files='files.sqlite3'), initial_data_path="database_init.yaml"):
  print("Initializing storage in", base_dir)
  try:
    os.mkdir(base_dir)
  except OSError:
    pass
  needs_init = set()
  for name, path in db_paths.items():
    path = os.path.join(base_dir, path)
    db = getattr(DB, name)
    if not file_exists(path):
      needs_init.add(name)
    db.init(path)
    db.connect()

  print("Databases requiring initialization:", needs_init)
  if len(needs_init) > 0:
    with open(os.path.join(base_dir, initial_data_path), 'r') as f:
      data = yaml.safe_load(f)
  if "states" in needs_init:
    # In dependency order
    namecls = dict([('Material', Material), ('PrinterProfile', PrinterProfile), ('PrinterState', PrinterState)])
    DB.states.create_tables([Material, PrinterProfile, PrinterState])
    print("Initialized tables", namecls.keys())
    for name, cls in namecls.items():
      for ent in data.get(name, []):
        if name == 'PrinterState':
          ent['profile'] = PrinterProfile.get(PrinterProfile.name == ent['profile']['name'])
        print("Creating", name, ent)
        cls.create(**ent)
  if "queues" in needs_init:
    namecls = dict([('Queue', Queue), ('Job', Job), ('Set', Set), ('Attempt', Attempt)])
    DB.queues.create_tables(namecls.values())
    print("Initialized tables", namecls.keys())
    for name, cls in namecls.items():
      for ent in data.get(name, []):
        if name == 'Job':
          ent['queue'] = Queue.get(Queue.name == ent['queue']['name'])
        elif name == 'Set':
          ent['job'] = Job.get(Job.name == ent['job']['name'])
        elif name == 'Attempt':
          ent['set_'] = Set.get(path=ent['set_']['path'])
        print("Creating", name, ent)
        cls.create(**ent)
  if "files" in needs_init:
    DB.files.create_tables([FileHash])
    for ent in data.get('FileHash', []):
      FileHash.create(**ent)
      
def upsertJobFromString(v: str):
  (queue, name, count, sets) = v.split(":")
  j = Job.create(queue=Queue.get(namespace=queue), name=name.strip(), count=int(count.strip()), lexRank=str(time.time()))
  for s in sets.split(","):
    (path, mat, count) = s.split("|")
    ss = Set.create(path=path.strip(), material=mat.strip(), count=int(count.strip()), job=j)

if __name__ == "__main__":
  init("data/")
  q = Queue.select().join(Job, JOIN.LEFT_OUTER).join(Set, JOIN.LEFT_OUTER).join(Attempt, JOIN.LEFT_OUTER)
  print(len(q), "results")
  for result in q:
    print("Queue", result.name)
    for j in result.jobs:
      print(f"\tJob {j.name}")
      for s in j.sets:
        print(f"\t\tSet {s.path}")
        for a in s.attempts:
          print(f"\t\t\tAttempt {a.start}")
