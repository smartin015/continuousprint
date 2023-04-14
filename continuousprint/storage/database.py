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
    TextField,
    CompositeKey,
    JOIN,
    Check,
)
from playhouse.migrate import SqliteMigrator, migrate

from ..data import CustomEvents, PREPROCESSORS
from collections import defaultdict
import datetime
from enum import IntEnum, auto
import sys
import logging
import inspect
import os
import yaml
import time


def getint(d, k, default=0):
    v = d.get(k, default)
    if type(v) == str:
        v = int(v)
    return v


logging.getLogger("peewee").setLevel(logging.INFO)


class STLResolveError(Exception):
    pass


# Defer initialization
class DB:
    # Adding foreign_keys pragma is necessary for ON DELETE behavior
    queues = SqliteDatabase(None, pragmas={"foreign_keys": 1})
    automation = SqliteDatabase(None, pragmas={"foreign_keys": 1})


CURRENT_SCHEMA_VERSION = "0.0.4"
DEFAULT_QUEUE = "local"
LAN_QUEUE = "LAN"
ARCHIVE_QUEUE = "archive"
BED_CLEARING_SCRIPT = "Bed Clearing"
FINISHING_SCRIPT = "Finished"
COOLDOWN_SCRIPT = "Managed Cooldown"


class Script(Model):
    name = CharField(unique=True)
    created = DateTimeField(default=datetime.datetime.now)
    body = TextField()

    class Meta:
        database = DB.automation


class Preprocessor(Model):
    name = CharField(unique=True)
    created = DateTimeField(default=datetime.datetime.now)
    body = TextField()

    class Meta:
        database = DB.automation


class EventHook(Model):
    name = CharField()
    script = ForeignKeyField(Script, backref="events", on_delete="CASCADE")
    preprocessor = ForeignKeyField(
        Preprocessor, null=True, backref="events", on_delete="CASCADE"
    )
    rank = FloatField()

    class Meta:
        database = DB.automation


class StorageDetails(Model):
    schemaVersion = CharField(unique=True)

    class Meta:
        database = DB.queues


class Queue(Model):
    name = CharField(unique=True)
    created = DateTimeField(default=datetime.datetime.now)
    rank = FloatField()
    addr = CharField(null=True)  # null == local (offline) queue
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


class JobView:
    """The job view contains functions used to manipulate an underlying Job model.

    This is distinct from the Job class to facilitate other storage implementations (e.g. LAN queue data)"""

    def refresh_sets(self):
        raise NotImplementedError()

    def save(self):
        raise NotImplementedError()

    def _load_set(self, data, idx):
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
        for s in sorted(self.sets, key=lambda s: s.rank):
            if custom_filter is not None and not custom_filter(s):
                continue
            printable = s.is_printable(profile)
            any_printable = any_printable or printable
            if s.remaining > 0 and printable:
                return (s, True)
        return (None, any_printable)

    def load_dict(self, data: dict, queue):
        self.queue = queue
        self.name = data.get("name", "")
        self.created = getint(data, "created")
        self.count = getint(data, "count")
        self.remaining = getint(data, "remaining", default=self.count)
        self.id = data.get("id", None)
        self.draft = data.get("draft", False)
        self.acquired = data.get("acquired", False)
        self.sets = [self._load_set(s, i) for i, s in enumerate(data["sets"])]

    def as_dict(self):
        sets = list(self.sets)
        sets.sort(key=lambda s: s.rank)
        sets = [s.as_dict() for s in sets]
        d = dict(
            queue=self.queue.name,
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


class Job(Model, JobView):
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

    def _load_set(self, data, idx):
        s = Set()
        s.load_dict(data, self, idx)
        return s

    def refresh_sets(self):
        Set.update(remaining=Set.count, completed=0).where(Set.job == self).execute()


class SetView:
    """See JobView for rationale for this class."""

    def save(self):
        raise NotImplementedError()

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
        self.completed += 1
        self.save()  # Save must occur before job is observed
        return self.job.next_set(profile)

    def load_dict(self, data, job, rank=None):
        self.job = job
        for listform, csvform in [
            ("materials", "material_keys"),
            ("profiles", "profile_keys"),
        ]:
            if data.get(listform) is not None:
                data[csvform] = ",".join(data[listform])
                del data[listform]
            else:
                data[csvform] = data.get(csvform, "")

        for numeric in ("count", "remaining", "completed"):
            data[numeric] = getint(data, numeric, 0)

        if rank is not None:
            data["rank"] = rank
        elif data.get("rank") is not None:
            data["rank"] = float(data["rank"])

        for filler in ("id", "sd"):
            if filler not in data:
                data[filler] = None

        for (k, v) in data.items():
            setattr(self, k, v)

    def resolve(self, override=None):
        if override is not None:
            self._resolved = override

        # TODO use registered slicer object types per octoprint hook
        if not hasattr(self, "_resolved") or self._resolved is None:
            raise NotImplementedError(
                "Implementer of SetView must implement .resolve()"
            )
        elif self._resolved.endswith(".stl"):
            raise STLResolveError(f"Set path {self._resolved} requires slicing")
        else:
            return self._resolved

    @classmethod
    def from_dict(self, s):
        raise NotImplementedError

    def as_dict(self):
        return dict(
            path=self.path,
            count=self.count,
            metadata=self.metadata,
            materials=self.materials(),
            profiles=self.profiles(),
            id=self.id,
            rank=self.rank,
            sd=self.sd,
            remaining=self.remaining,
            completed=self.completed,
        )


class Set(Model, SetView):
    path = CharField()
    sd = BooleanField()
    job = ForeignKeyField(Job, backref="sets", on_delete="CASCADE")
    rank = FloatField()
    count = IntegerField(default=1, constraints=[Check("count >= 0")])

    # Contains JSON of metadata such as print time estimates, filament length
    # etc. These are assigned on creation and are
    # only as accurate as the provider's ability to analyze the gcode.
    metadata = TextField(null=True)

    remaining = IntegerField(
        # Unlike Job, Sets can have remaining > count if the user wants to print
        # additional sets as a one-off correction (e.g. a print fails)
        default=1,
        constraints=[Check("remaining >= 0")],
    )
    completed = IntegerField(
        # Due to one-off corrections to "remaining", it's important to track
        # completions separately as completed + remaining != count
        # This is different from jobs, where this equation holds.
        default=0,
        constraints=[Check("completed >= 0")],
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

    def resolve(self, override=None):
        if getattr(self, "_resolved", None) is None:
            self._resolved = self.path
        return super().resolve(override)


class Run(Model):
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
AUTOMATION = [Script, EventHook, Preprocessor]


def populate_queues():
    DB.queues.create_tables(MODELS)
    StorageDetails.create(schemaVersion=CURRENT_SCHEMA_VERSION)
    Queue.create(name=LAN_QUEUE, addr="auto", strategy="LINEAR", rank=1)
    Queue.create(name=DEFAULT_QUEUE, strategy="LINEAR", rank=0)
    Queue.create(name=ARCHIVE_QUEUE, strategy="LINEAR", rank=-1)


def populate_automation():
    DB.automation.create_tables(AUTOMATION)
    bc = Script.create(name=BED_CLEARING_SCRIPT, body="@pause")
    fin = Script.create(name=FINISHING_SCRIPT, body="@pause")
    EventHook.create(name=CustomEvents.PRINT_SUCCESS.event, script=bc, rank=0)
    EventHook.create(name=CustomEvents.FINISH.event, script=fin, rank=0)
    for pp in PREPROCESSORS.values():
        Preprocessor.create(name=pp["name"], body=pp["body"])


def init_db(automation_db, queues_db, logger=None):
    init_automation(automation_db, logger)
    init_queues(queues_db, logger)


def init_automation(db_path, logger=None):
    db = DB.automation
    needs_init = not file_exists(db_path)
    db.init(None)
    db.init(db_path)
    db.connect()
    if needs_init:
        if logger is not None:
            logger.debug("Initializing automation DB")
        populate_automation()


def migrateQueuesV2ToV3(details, logger):
    # Constraint removal isn't allowed in sqlite, so we have
    # to recreate the table and move the entries over.
    # We also added a new `completed` field, so some calculation is needed.
    class TempSet(Set):
        pass

    if logger is not None:
        logger.warning(
            f"Beginning migration to v0.0.3 for decoupled completions - {Set.select().count()} sets to migrate"
        )
    db = DB.queues
    with db.atomic():
        TempSet.create_table(safe=True)
        for s in Set.select(
            Set.path,
            Set.sd,
            Set.job,
            Set.rank,
            Set.count,
            Set.remaining,
            Set.material_keys,
            Set.profile_keys,
        ).execute():
            attrs = {}
            for f in Set._meta.sorted_field_names:
                attrs[f] = getattr(s, f)
            attrs["completed"] = max(0, attrs["count"] - attrs["remaining"])
            TempSet.create(**attrs)
            if logger is not None:
                logger.warning(f"Migrating set {s.path} to schema v0.0.3")

    Set.drop_table(safe=True)
    db.execute_sql('ALTER TABLE "tempset" RENAME TO "set";')
    details.schemaVersion = "0.0.3"
    details.save()


def init_queues(db_path, logger=None):
    db = DB.queues
    needs_init = not file_exists(db_path)
    db.init(None)
    db.init(db_path)
    db.connect()

    if needs_init:
        if logger is not None:
            logger.debug("Initializing queues DB")
        populate_queues()
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

            if details.schemaVersion == "0.0.2":
                migrateSchemaV2ToV3(details, logger)

            if details.schemaVersion == "0.0.3":
                if logger is not None:
                    logger.warning(
                        f"Updating schema from {details.schemaVersion} to 0.0.4"
                    )
                migrate(
                    migrator.add_column("set", "metadata", Set.metadata),
                )
                details.schemaVersion = "0.0.4"
                details.save()

            if details.schemaVersion != CURRENT_SCHEMA_VERSION:
                raise Exception(
                    "DB schema version is not current: " + details.schemaVersion
                )

            if logger is not None:
                logger.debug("Storage schema version: " + details.schemaVersion)
        except Exception:
            raise Exception("Failed to fetch storage schema details!")

    return db


def migrateScriptsFromSettings(clearing_script, finished_script, cooldown_script):
    # In v2.2.0 and earlier, a fixed list of scripts were stored in OctoPrint settings.
    # This converts them to DB format for use in events.
    with DB.automation.atomic():
        for (evt, name, body) in [
            (CustomEvents.PRINT_SUCCESS, BED_CLEARING_SCRIPT, clearing_script),
            (CustomEvents.FINISH, FINISHING_SCRIPT, finished_script),
            (CustomEvents.COOLDOWN, COOLDOWN_SCRIPT, cooldown_script),
        ]:
            if body is None or body.strip() == "":
                continue  # Don't add empty scripts
            Script.delete().where(Script.name == name).execute()
            s = Script.create(name=name, body=body)
            EventHook.delete().where(EventHook.name == evt.event).execute()
            EventHook.create(name=evt.event, script=s, rank=0)


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
                completed=0,
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
