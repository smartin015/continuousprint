from peewee import (
    Model,
    SqliteDatabase,
    CharField,
    DateTimeField,
    IntegerField,
    ForeignKeyField,
    BooleanField,
    FloatField,
    DateField,
    TimeField,
    CompositeKey,
    JOIN,
    Check,
)
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
    queues = SqliteDatabase(None, pragmas={"foreign_keys": 1})


class Queue(Model):
    name = CharField(unique=True)
    created = DateTimeField(default=datetime.datetime.now)
    addr = CharField(null=True)  # null == local queue
    strategy = CharField()

    class Meta:
        database = DB.queues

    def as_dict(self):
        q = dict(
            name=self.name,
            addr=self.addr,
            strategy=self.strategy,
        )
        # if json_safe:
        #    q["created"] = int(q["created"].timestamp())
        return q


class Job(Model):
    queue = ForeignKeyField(Queue, backref="jobs", on_delete="CASCADE")
    name = CharField()
    lexRank = FloatField()
    count = IntegerField(default=1, constraints=[Check("count > 0")])
    remaining = IntegerField(
        default=1, constraints=[Check("remaining >= 0"), Check("remaining <= count")]
    )
    created = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = DB.queues

    def as_dict(self, json_safe=False):
        sets = list(self.sets)
        sets.sort(key=lambda s: s.lexRank)
        sets = [s.as_dict(json_safe) for s in sets]
        d = dict(
            name=self.name,
            count=self.count,
            sets=sets,
            created=self.created,
            id=self.id,
            remaining=self.remaining,
        )
        if json_safe:
            d["created"] = int(d["created"].timestamp())
        return d


class Set(Model):
    path = CharField()
    sd = BooleanField()
    job = ForeignKeyField(Job, backref="sets", on_delete="CASCADE")
    lexRank = FloatField()
    count = IntegerField(default=1, constraints=[Check("count > 0")])
    remaining = IntegerField(
        default=1, constraints=[Check("remaining >= 0"), Check("remaining <= count")]
    )

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
        return dict(
            path=self.path,
            count=self.count,
            materials=self.material_keys.split(","),
            id=self.id,
            lr=self.lexRank,
            sd=self.sd,
            remaining=self.remaining,
        )


class Run(Model):
    job = ForeignKeyField(Job, backref="runs", on_delete="CASCADE")
    path = CharField()
    start = DateTimeField(default=datetime.datetime.now)
    end = DateTimeField(null=True)
    result = CharField(null=True)

    class Meta:
        database = DB.queues

    def as_dict(self, json_safe=True):
        d = dict(start=self.start, end=self.end, result=self.result, id=self.id)
        if json_safe:
            d["start"] = int(d["start"].timestamp())
            if d["end"] is not None:
                d["end"] = int(d["end"].timestamp())
        return d


def file_exists(path: str) -> bool:
    try:
        return os.stat(path).st_size > 0
    except OSError:
        return False


def init(db_path="queues.sqlite3", initial_data_path="init.yaml"):
    db = DB.queues
    needs_init = not file_exists(db_path)
    db.init(None)
    db.init(db_path)
    db.connect()

    if needs_init:
        DB.queues.create_tables([Queue, Job, Set, Run])
        Queue.create(name="default", strategy="LINEAR")
        Queue.create(name="archive", strategy="LINEAR")
