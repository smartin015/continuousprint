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
from playhouse.migrate import SqliteMigrator, migrate

from collections import defaultdict
import datetime
from enum import IntEnum, auto
import sys
import inspect
import os
import yaml
import time


class PermView:
    def _allowed(self, user, groups, action_mask):
        action_mask = action_mask & 0x7
        return (
            (user == self.owner and (self.perms >> 6) & action_mask != 0)
            or (self.group in groups and (self.perms >> 3) & action_mask != 0)
            or (self.perms & action_mask != 0)
        )

    def permstr(self):
        r = "".join(
            reversed(
                ["xwr"[i % 3] if (self.perms & (1 << i)) else "-" for i in range(9)]
            )
        )
        return f"{r[0:3]} {r[3:6]} {r[6:]}"

    def can_read(self, user, groups):
        return self._allowed(user, groups, 0x4)

    def can_write(self, user, groups):
        return self._allowed(user, groups, 0x2)

    def can_exec(self, user, groups):
        return self._allowed(user, groups, 0x1)


class PermModel(Model):
    perms = IntegerField(default=0b111100100)
    owner = CharField(default="admin")
    group = CharField(null=True)


# Defer initialization
class DB:
    # Adding foreign_keys pragma is necessary for ON DELETE behavior
    queues = SqliteDatabase(None, pragmas={"foreign_keys": 1})


DEFAULT_QUEUE = "local"
LAN_QUEUE = "LAN"
ARCHIVE_QUEUE = "archive"


class StorageDetails(Model):
    schemaVersion = CharField(unique=True)

    class Meta:
        database = DB.queues


class Queue(PermView, PermModel):
    name = CharField(unique=True)
    created = DateTimeField(default=datetime.datetime.now)
    rank = FloatField()
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
        return q


class JobView(PermView):
    """The job view contains functions used to manipulate an underlying Job model.

    This is distinct from the Job class to facilitate other storage implementations (e.g. LAN queue data)"""

    def refresh_sets(self):
        raise NotImplementedError()

    def decrement(self):
        self.remaining = max(self.remaining - 1, 0)
        self.save()
        if self.remaining > 0:
            self.refresh_sets()

    def next_set(self, profile, custom_filter=None):
        if self.draft or self.queue.name == ARCHIVE_QUEUE or self.remaining == 0:
            return None

        nxt, any_printable = self._next_set(profile, custom_filter)
        # We may need to decrement to actually get the next set
        # but we don't touch the job if there aren't any compatible/printable sets to begin with
        if nxt is None and any_printable:
            self.decrement()
            return self._next_set(profile, custom_filter)[0]
        else:
            return nxt

    def _next_set(self, profile, custom_filter):
        # Return value: (set: SetView, any_printable: bool)
        # Second argument is whether there's any printable sets
        # for the given profile/filter. If this is False then
        # decrementing the set/job won't do anything WRT set availability
        any_printable = False
        for s in self.sets:
            if custom_filter is not None and not custom_filter(s):
                continue
            printable = s.is_printable(profile)
            any_printable = any_printable or printable
            if s.remaining > 0 and printable:
                return (s, True)
        return (None, any_printable)

    @classmethod
    def from_dict(self, data: dict):
        raise NotImplementedError

    def as_dict(self):
        sets = list(self.sets)
        sets.sort(key=lambda s: s.rank)
        sets = [s.as_dict() for s in sets]
        d = dict(
            name=self.name,
            count=self.count,
            draft=self.draft,
            sets=sets,
            created=self.created,
            id=self.id,
            remaining=self.remaining,
            acquired=self.acquired,
        )
        if type(d["created"]) != int:
            d["created"] = int(d["created"].timestamp())
        return d


class Job(PermModel, JobView):
    queue = ForeignKeyField(Queue, backref="jobs", on_delete="CASCADE")
    name = CharField()
    rank = FloatField()
    count = IntegerField(default=1, constraints=[Check("count >= 0")])
    remaining = IntegerField(
        default=1, constraints=[Check("remaining >= 0"), Check("remaining <= count")]
    )
    created = DateTimeField(default=datetime.datetime.now)

    # These members relate to status of the job in the UI / driver
    draft = BooleanField(default=True)
    acquired = BooleanField(default=False)

    class Meta:
        database = DB.queues

    @classmethod
    def from_dict(self, data: dict):
        j = Job(**data)
        j.sets = [Set.from_dict(s) for s in data["sets"]]
        return j

    def refresh_sets(self):
        Set.update(remaining=Set.count).where(Set.job == self).execute()


class SetView(PermView):
    """See JobView for rationale for this class."""

    def _csv2list(self, v):
        if v == "":
            return []
        return v.split(",")

    def materials(self):
        return self._csv2list(self.material_keys)

    def profiles(self):
        return self._csv2list(self.profile_keys)

    def is_printable(self, profile):
        profs = self.profiles()
        if len(profs) == 0 or profile["name"] in profs:
            return True
        return False

    def decrement(self, profile):
        self.remaining = max(0, self.remaining - 1)
        self.save()  # Save must occur before job is observed
        return self.job.next_set(profile)

    @classmethod
    def from_dict(self, s):
        raise NotImplementedError

    def as_dict(self):
        return dict(
            path=self.path,
            count=self.count,
            materials=self.materials(),
            profiles=self.profiles(),
            id=self.id,
            rank=self.rank,
            sd=self.sd,
            remaining=self.remaining,
        )


class Set(PermModel, SetView):
    path = CharField()
    sd = BooleanField()
    job = ForeignKeyField(Job, backref="sets", on_delete="CASCADE")
    rank = FloatField()
    count = IntegerField(default=1, constraints=[Check("count >= 0")])
    remaining = IntegerField(
        default=1, constraints=[Check("remaining >= 0"), Check("remaining <= count")]
    )

    # This is a CSV of material key strings referencing SpoolManager entities
    # (makes it easier to manage material keys as a single field)
    # It's intentionally NOT a foreign key for this reason.
    material_keys = CharField(default="")

    # A CSV of printer profiles (names as defined in printer_profiles.yaml)
    profile_keys = CharField(default="")

    class Meta:
        database = DB.queues

    @classmethod
    def from_dict(self, s):
        for listform, csvform in [
            ("materials", "material_keys"),
            ("profiles", "profile_keys"),
        ]:
            if s.get(listform) is not None:
                s[csvform] = ",".join(s[listform])
                del s[listform]
        return Set(**s)


class Run(PermView, PermModel):
    # Runs are totally decoupled from queues, jobs, and sets - this ensures that
    # the run history persists even if the other items are deleted
    queueName = CharField()
    jobName = CharField()
    path = CharField()

    start = DateTimeField(default=datetime.datetime.now)
    end = DateTimeField(null=True)
    result = CharField(null=True)

    # Optional timelapse annotation for the run, set when
    # OctoPrint finishes rendering the timelapse of the prior run
    movie_path = CharField(null=True)
    thumb_path = CharField(null=True)

    class Meta:
        database = DB.queues

    def as_dict(self):
        d = dict(
            start=self.start,
            end=self.end,
            result=self.result,
            id=self.id,
            path=self.path,
            jobName=self.jobName,
            queueName=self.queueName,
        )
        d["start"] = int(d["start"].timestamp())
        if d["end"] is not None:
            d["end"] = int(d["end"].timestamp())
        return d


def file_exists(path: str) -> bool:
    try:
        return os.stat(path).st_size > 0
    except OSError:
        return False


MODELS = [Queue, Job, Set, Run, StorageDetails]


def populate():
    DB.queues.create_tables(MODELS)
    StorageDetails.create(schemaVersion="0.0.2")
    Queue.create(
        name=LAN_QUEUE, addr="auto", strategy="LINEAR", rank=1, mask=0b111111111
    )
    Queue.create(name=DEFAULT_QUEUE, strategy="LINEAR", rank=0, mask=0b111111111)
    Queue.create(name=ARCHIVE_QUEUE, strategy="LINEAR", rank=-1, mask=0b111111111)


def init(db_path="queues.sqlite3", logger=None):
    db = DB.queues
    needs_init = not file_exists(db_path)
    db.init(None)
    db.init(db_path)
    db.connect()

    if needs_init:
        if logger is not None:
            logger.debug("DB needs init")
        populate()
    else:
        try:
            details = StorageDetails.select().limit(1).execute()[0]
            migrator = SqliteMigrator(db)
            if details.schemaVersion == "0.0.1":
                if logger is not None:
                    logger.warning(f"Updating schema from {details.schemaVersion}")
                # Added fields to Run
                migrate(
                    migrator.add_column("run", "movie_path", Run.movie_path),
                    migrator.add_column("run", "thumb_path", Run.thumb_path),
                )
                details.schemaVersion = "0.0.2"
                details.save()

            if details.schemaVersion != "0.0.2":
                raise Exception("Unknown DB schema version: " + details.schemaVersion)

            if logger is not None:
                logger.debug("Storage schema version: " + details.schemaVersion)
        except Exception:
            raise Exception("Failed to fetch storage schema details!")


def migrateFromSettings(data: list):
    # Prior to v2.0.0, all state for the plugin was stored in a json-serialized list
    # in OctoPrint settings. This method converts the various forms of the json blob
    # to entries in the database.

    q = Queue.get(name=DEFAULT_QUEUE)
    jr = 0
    for i in data:
        jname = i.get("job", "")
        try:
            j = Job.get(name=jname)
        except Job.DoesNotExist:
            j = Job(queue=q, name=jname, draft=False, rank=jr, count=1, remaining=0)
            jr += 1
        run_num = i.get("run", 0)
        j.count = max(run_num + 1, j.count)
        if i.get("end_ts") is None:
            j.remaining = max(j.count - run_num, j.remaining)
        j.save()

        s = None
        spath = i.get("path", "")
        for js in j.sets:
            if js.path == spath:
                s = js
                break
        if s is None:
            sd = i.get("sd", False)
            if type(sd) == str:
                sd = sd.lower() == "true"
            if type(sd) != bool:
                sd = False
            mkeys = ""
            mats = i.get("materials")
            if mats is not None and len(mats) > 0:
                mkeys = ",".join(mats)
            s = Set(
                path=spath,
                sd=sd,
                job=j,
                rank=len(j.sets),
                count=1,
                remaining=0,
                material_keys=mkeys,
            )
        else:
            if i.get("run") == 0:  # Treat first run as true count
                s.count += 1
            if i.get("end_ts") is None:
                s.remaining += 1
        s.save()

        start_ts = i.get("start_ts")
        end_ts = i.get("end_ts")
        if start_ts is not None:
            start_ts = datetime.datetime.fromtimestamp(start_ts)
            end_ts = i.get("end_ts")
            if end_ts is not None:
                end_ts = datetime.datetime.fromtimestamp(end_ts)
            Run.create(
                queueName=DEFAULT_QUEUE,
                jobName=jname,
                job=j,
                path=spath,
                start=start_ts,
                end=end_ts,
                result=i.get("result"),
            )
