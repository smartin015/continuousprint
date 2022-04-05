from peewee import Model, SqliteDatabase, CharField, DateTimeField, IntegerField, ForeignKeyField, BooleanField, FloatField, DateField, TimeField, CompositeKey, JOIN
import datetime
from enum import IntEnum, auto
import sys
import inspect
import os
import yaml
import time

# Defer initialization
class DB:
  # Adding foreign_keys pragma is necessary for ON DELETE behavior
  states = SqliteDatabase(None, pragmas={'foreign_keys': 1})
  queues = SqliteDatabase(None, pragmas={'foreign_keys': 1})
  files = SqliteDatabase(None, pragmas={'foreign_keys': 1})

class Schedule(Model):
  name = CharField(index=True)
  peer = CharField(index=True)
  class Meta:
    database = DB.states

  def as_dict(self):
    periods = []
    for p in self.periods:
      periods += p.resolve()
    periods.sort(key=lambda v: v[0])

    return dict(
      name=self.name,
      periods=periods,
    )

def utc_ts(dt=None) -> int:
  if dt is None:
    dt = datetime.datetime.now(tz=datetime.timezone.utc)
  utc_time = dt.replace(tzinfo=datetime.timezone.utc)
  return int(utc_time.timestamp())

def next_dt(daystr, dt=None):
  if dt is None:
    dt = datetime.datetime.now(tz=datetime.timezone.utc) 
  cur = dt.weekday()
  for day in range(cur+1,14): # 2 weeks, guaranteed to have a next day
    if daystr[day%7] != ' ':
      break
  return dt + datetime.timedelta(days=(day-cur))


class Period(Model):
  schedule = ForeignKeyField(Schedule, backref='periods',  on_delete='CASCADE') 
  # In the future, can potentially have a bool field in here to specifically select
  # holidays - https://pypi.org/project/holidays/
  
  # Leave null if not specific date event. Timestamp in seconds.
  timestamp_utc = IntegerField(null=True)

  # Leave null if timestamp_utc is set
  # Arbitrary characters with spaces for non-selected days (e.g. "MTWRFSU", "M W F  ")
  # TODO peewee validation
  daysofweek = CharField(max_length=7, null=True) 

  # See http://pytz.sourceforge.net/
  # https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
  # Must be populated if dayofweek is populated
  tz = CharField(null=True)

  # Must be populated if dayofweek is populated
  # Seconds after start of day where the period begins
  start = IntegerField(null=True)
 
  # Duration in seconds
  duration = IntegerField()

  # How many times are we allowed to interrupt the user?
  max_manual_events = IntegerField()


  class Meta:
    database = DB.states

  def resolve(self, now=None, unroll=60*60*24*3) -> list[tuple]:
    if self.timestamp_utc is not None:
      return [(self.timestamp_utc, self.duration, self.max_manual_events)]
    else:
      result = []
      now = utc_ts()
      dt = None
      ts = 0
      while ts < now+unroll:
        dt = next_dt(self.daysofweek, dt)
        ts = utc_ts(dt) + self.start
        result.append((ts, self.duration, self.max_manual_events))
      return result

class Material(Model):
  key = CharField(unique=True)
  color = CharField()
  composition = CharField()
  class Meta:
    database = DB.states
    indexes = (
      # Unique index on color/composition
      (('color', 'composition'), True),
    )

class PrinterProfile(Model):
  name = CharField(index=True)
  peer = CharField(index=True)
  model = CharField()
  width = FloatField()
  depth = FloatField()
  height = FloatField()
  formFactor = CharField()
  selfClearing = BooleanField()
  class Meta:
    database = DB.states

class PrinterState(Model):
  peer = CharField(unique=True)
  profile = ForeignKeyField(PrinterProfile)
  schedule = ForeignKeyField(Schedule)
  queue = CharField() # Specifically NOT a foreign key field (queues are in a different DB)
  status = CharField()
  secondsUntilIdle = IntegerField()
  class Meta:
    database = DB.states

  def as_dict(self):
    return dict(
      name=self.profile.name,
      peer=self.peer,
      queue=self.queue,
      model=self.profile.model,
      width=self.profile.width,
      depth=self.profile.depth,
      height=self.profile.height,
      formFactor=self.profile.formFactor,
      selfClearing=self.profile.selfClearing,
      schedule=self.schedule.as_dict(),
      status=self.status,
    )

class MaterialState(Model):
  material_key = CharField() # Not backref as material may not be known to some printers
  printer = ForeignKeyField(PrinterState, backref="materials")
  loaded = BooleanField(default=False)
  inStock = BooleanField(default=False)

  class Meta:
    database = DB.states

class NetworkType(IntEnum):
  NONE = auto()
  LAN = auto()

class Queue(Model):
  name = CharField(unique=True)
  created = DateTimeField(default=datetime.datetime.now)
  network_type = IntegerField()
  class Meta:
    database = DB.queues

class Job(Model):
  queue = ForeignKeyField(Queue, backref='jobs', on_delete='CASCADE')
  # By convention, namespaced by queue name. We avoid CompositeKey here as PeeWee does not support
  # foreign-keys to models with CompositeKey primary keys - which is the case with Sets
  name = CharField(unique=True) 
  lexRank = CharField()
  count = IntegerField(default=1)
  created = DateTimeField(default=datetime.datetime.now)

  # Job state variables
  peerAssigned = CharField(null=True)
  peerLease = DateTimeField(null=True)
  result = CharField(null=True)
  ageRank = IntegerField(default=0)

  class Meta:
    database = DB.queues

  def as_dict(self):
    sets = [s.as_dict() for s in self.sets]
    return dict(name=self.name, count=self.count, sets=sets, created=self.created)

  def age_sec(self, now=None):
    if now == None:
      now = datetime.datetime.now()
    
    return (now - self.created).total_seconds()

  def materialChanges(self, start_material):
    c = 0
    cm = start_material
    for s in self.sets:
      if s.material_key != cm:
        c += 1
        cm = s.material_key
    age_rank = 0 # TODO set rank based on number of times passed over for scheduling
    return c

class Set(Model):
  path = CharField()
  hash_ = CharField()
  # TODO multi-material
  material_key = CharField() # Specifically NOT a foreign key - materials are stored in a different db
  job = ForeignKeyField(Job, backref='sets', on_delete='CASCADE')
  count = IntegerField(default=1)
  class Meta:
    database = DB.queues

  def as_dict(self):
    return dict(path=self.path, count=self.count, hash_=self.hash_, material=self.material_key)

class Attempt(Model):
  set_ = ForeignKeyField(Set, column_name='set', backref='attempts',  on_delete='CASCADE')
  start = DateTimeField(default=datetime.datetime.now)
  end = DateTimeField(null=True)
  result = CharField(null=True)
  class Meta:
    database = DB.queues

class FileHash(Model):
  hash_ = CharField(index=True, column_name='hash')
  path = CharField()
  peer = CharField()
  created = DateTimeField(default=datetime.datetime.now)
  class Meta:
    database = DB.files
    

def file_exists(path: str) -> bool:
  try: 
    return os.stat(path).st_size > 0
  except OSError as error:
    return False

def init(base_dir: str, db_paths = dict(states='states.sqlite3', queues='queues.sqlite3', files='files.sqlite3'), initial_data_path="database_init.yaml"):
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
    db.init(None)
    db.init(path)
    db.connect()

  if len(needs_init) > 0:
    if initial_data_path is not None:    
      with open(os.path.join(base_dir, initial_data_path), 'r') as f:
        data = yaml.safe_load(f)
    else:
      data = {}
  if "states" in needs_init:
    # In dependency order
    namecls = dict([
      ('Schedule', Schedule), 
      ('Period', Period), 
      ('Material', Material), 
      ('PrinterProfile', PrinterProfile), 
      ('PrinterState', PrinterState),
      ('MaterialState', MaterialState),
    ])
    DB.states.create_tables(namecls.values())
    for name, cls in namecls.items():
      for ent in data.get(name, []):
        if name == 'PrinterState':
          ent['profile'] = PrinterProfile.get(PrinterProfile.name == ent['profile']['name'])
          ent['schedule'] = Schedule.get(Schedule.name == ent['schedule']['name'])
        elif name == 'Period':
          ent['schedule'] = Schedule.get(Schedule.name == ent['schedule']['name'])
        elif name == 'MaterialState':
          ent['printer'] = PrinterState.get(PrinterState.peer == ent['printer']['peer'])
        cls.create(**ent)
  if "queues" in needs_init:
    namecls = dict([('Queue', Queue), ('Job', Job), ('Set', Set), ('Attempt', Attempt)])
    DB.queues.create_tables(namecls.values())
    for name, cls in namecls.items():
      for ent in data.get(name, []):
        if name == 'Job':
          ent['name'] = f"{ent['queue']['name']}/{ent['name']}" 
          ent['queue'] = Queue.get(Queue.name == ent['queue']['name'])
        elif name == 'Set':
          ent['job'] = Job.get(Job.name == ent['job']['name'])
        elif name == 'Attempt':
          ent['set_'] = Set.get(path=ent['set_']['path'])
        cls.create(**ent)
  if "files" in needs_init:
    DB.files.create_tables([FileHash])
    for ent in data.get('FileHash', []):
      FileHash.create(**ent)
      
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
