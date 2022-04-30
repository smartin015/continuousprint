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
  queues = SqliteDatabase(None, pragmas={'foreign_keys': 1})

class Queue(Model):
  name = CharField(unique=True)
  created = DateTimeField(default=datetime.datetime.now)
  class Meta:
    database = DB.queues


class Job(Model):
  queue = ForeignKeyField(Queue, backref='jobs', on_delete='CASCADE')
  name = CharField()
  lexRank = FloatField()
  count = IntegerField(default=1)
  created = DateTimeField(default=datetime.datetime.now)

  class Meta:
    database = DB.queues

  def as_dict(self, json_safe=False):
    sets = list(self.sets)
    sets.sort(key=lambda s: s.lexRank)
    sets = [s.as_dict(json_safe) for s in sets]
    d = dict(name=self.name, count=self.count, sets=sets, created=self.created, id=self.id)
    if json_safe:
      d['created'] = int(d['created'].timestamp())
    return d


class Set(Model):
  path = CharField()
  sd = BooleanField()
  job = ForeignKeyField(Job, backref='sets', on_delete='CASCADE')
  lexRank = FloatField()
  count = IntegerField(default=1)
  remaining = IntegerField(default=1)

  # This is a CSV of material key strings referencing SpoolManager entities
  # (makes it easier to manage material keys as a single field)
  # It's intentionally NOT a foreign key for this reason.
  material_keys = CharField()
  def materials(self):
    if self.material_keys == "":
      return []
    return self.material_keys.split(",")

  class Meta:
    database = DB.queues

  def as_dict(self, json_safe=False):
    runs = [r.as_dict(json_safe) for r in self.runs]
    return dict(path=self.path, count=self.count, materials=self.material_keys.split(","), runs=runs, id=self.id, lr=self.lexRank, sd=self.sd)



class Run(Model):
  set_ = ForeignKeyField(Set, column_name='set', backref='runs',  on_delete='CASCADE')
  start = DateTimeField(default=datetime.datetime.now)
  end = DateTimeField(null=True)
  result = CharField(null=True)

  class Meta:
    database = DB.queues

  def as_dict(self, json_safe=True):
    d = dict(start=self.start, end=self.end, result=self.result, id=self.id)
    if json_safe:
      d['start'] = int(d['start'].timestamp())
      if d['end'] is not None:
        d['end'] = int(d['end'].timestamp())
    return d



def file_exists(path: str) -> bool:
  try:
    return os.stat(path).st_size > 0
  except OSError as error:
    return False

def init(db_path='queues.sqlite3', initial_data_path="init.yaml"):
  db = DB.queues
  needs_init = not file_exists(db_path)
  db.init(None)
  db.init(db_path)
  db.connect()

  if needs_init:
    if initial_data_path is not None:
      with open(initial_data_path, 'r') as f:
        data = yaml.safe_load(f)
    else:
      data = {}

    namecls = dict([('Queue', Queue), ('Job', Job), ('Set', Set), ('Run', Run)])
    DB.queues.create_tables(namecls.values())
    for name, cls in namecls.items():
      for ent in data.get(name, []):
        if name == 'Job':
          ent['queue'] = Queue.get(Queue.name == ent['queue']['name'])
        elif name == 'Set':
          ent['job'] = Job.get(Job.name == ent['job']['name'])
        elif name == 'Run':
          ent['set_'] = Set.get(path=ent['set_']['path'])
        cls.create(**ent)
