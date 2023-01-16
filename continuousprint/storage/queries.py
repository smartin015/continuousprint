from peewee import IntegrityError, JOIN, fn
from typing import Optional
from datetime import datetime
from io import StringIO
from asteval import Interpreter
import re
import time
import base64

from pathlib import Path
from .database import (
    Queue,
    Job,
    Set,
    Run,
    DB,
    DEFAULT_QUEUE,
    ARCHIVE_QUEUE,
    EventHook,
    Preprocessor,
    Script,
)
from ..data import CustomEvents


MAX_COUNT = 999999


def getint(d, k, default=0):
    v = d.get(k, default)
    if type(v) == str:
        v = int(v)
    return v


def clearOldState():
    # On init, scrub the local DB for any state that may have been left around
    # due to an improper shutdown
    Job.update(acquired=False).execute()
    Run.update(end=datetime.now(), result="aborted").where(Run.end.is_null()).execute()


def getQueues():
    return Queue.select().order_by(Queue.rank.asc())


def acquireJob(j) -> bool:
    Job.update(acquired=True).where(Job.id == j.id).execute()
    return True


def releaseJob(j) -> bool:
    Job.update(acquired=False).where(Job.id == j.id).execute()
    return True


def importJob(qname, manifest: dict, dirname: str, draft=False):
    q = Queue.get(name=qname)

    # Manifest may have "remaining" values set incorrectly for new job; ensure
    # these are set to the whole count for both job and sets.
    j = Job.from_dict(manifest)
    j.remaining = j.count
    j.id = None
    j.queue = q
    j.rank = _rankEnd()
    j.draft = draft
    j.save()
    for s in j.sets:
        # Prepend new folder as initial path is relative to root
        s.path = str(Path(dirname) / s.path)
        s.remaining = s.count
        s.sd = False
        s.id = None
        s.job = j.id
        s.rank = _rankEnd()
        s.save()
    return j


def getAcquiredJob():
    j = (
        Job.select()
        .where((Job.acquired) & (Job.queue.name != ARCHIVE_QUEUE))
        .limit(1)
        .execute()
    )
    if len(j) == 0:  # No jobs acquired
        return None
    return j[0]


def getActiveRun(qname, jname, spath):
    r = (
        Run.select()
        .where(
            (Run.end.is_null())
            & (Run.queueName == qname)
            & (Run.jobName == jname)
            & (Run.path == spath)
        )
        .limit(1)
        .execute()
    )
    if len(r) == 0:
        return None
    return r[0]


def assignQueues(queues):
    # Default/archive queues should never be removed
    names = set([qdata["name"] for qdata in queues] + [DEFAULT_QUEUE, ARCHIVE_QUEUE])
    with DB.queues.atomic():
        qq = getQueues()
        qq_names = set([q.name for q in qq])
        absent = [(q.id, q.name) for q in qq if q.name not in names]
        if len(absent) > 0:
            (absent_ids, absent_names) = zip(*absent)
            Queue.delete().where(Queue.id.in_(absent_ids)).execute()
        else:
            absent_names = []
        added = [q for q in queues if q["name"] not in qq_names]
        added_names = set([q["name"] for q in added])
        for rank, qdata in enumerate(queues):
            if qdata["name"] in added_names:
                Queue.create(
                    name=qdata["name"],
                    strategy=qdata["strategy"],
                    addr=qdata["addr"],
                    rank=rank,
                )
            else:
                Queue.update(
                    strategy=qdata["strategy"], addr=qdata["addr"], rank=rank
                ).where(Queue.name == qdata["name"]).execute()
    return (absent_names, added)


def getJobsAndSets(queue):
    if type(queue) == str:
        queue = Queue.get(name=queue)
    return (
        Job.select()
        .join(Set, JOIN.LEFT_OUTER)
        .where(Job.queue == queue)
        .group_by(Job.id)
        .order_by(Job.rank.asc())
    ).execute()


def getJob(jid):
    return Job.get(id=jid)


def getNextJobInQueue(q, profile, custom_filter=None):
    for job in getJobsAndSets(q):
        ns = job.next_set(
            profile, custom_filter
        )  # Only return a job which has a compatible next set
        if ns is not None:
            return job


def _upsertSet(set_id, data, job):
    # Called internally from updateJob
    try:
        s = Set.get(id=set_id)
    except Set.DoesNotExist:
        # This can happen when dragging a set between two draft jobs, and saving
        # the source job (which deletes the source job's set).
        # In that case the ID doesn't matter as much as the existence of the set.
        # We use placeholder values here as all will be set later in the upsert.
        s = Set.create(path="", sd=False, job=job, rank=0)
    for k, v in data.items():
        if k in (
            "id",
            "materials",
            "profiles",
        ):  # ignored or handled below
            continue

        # parse and limit integer values
        if k in (
            "count",
            "remaining",
        ):
            v = min(int(v), MAX_COUNT)
        setattr(s, k, v)
    s.job = job

    s.material_keys = ",".join(
        ["" if m is None else m for m in data.get("materials", [])]
    )
    s.profile_keys = ",".join(
        ["" if p is None else p for p in data.get("profiles", [])]
    )
    s.save()


def updateJob(job_id, data, queue=DEFAULT_QUEUE):
    with DB.queues.atomic():
        try:
            j = Job.get(id=job_id)
        except Job.DoesNotExist:
            q = Queue.get(name=queue)
            j = newEmptyJob(q)

        for k, v in data.items():
            if k in (
                "id",
                "sets",
                "queue",
            ):  # ignored or handled separately
                continue

            # Parse and bound integer values
            if k in ("count", "remaining"):
                v = min(int(v), MAX_COUNT)
            setattr(j, k, v)

        if data.get("sets") is not None:
            # Remove any missing sets
            set_ids = set([s["id"] for s in data["sets"]])
            for s in j.sets:
                if s.id not in set_ids:
                    s.delete_instance()
            # Update new sets and ensure proper order
            for i, s in enumerate(data["sets"]):
                s["rank"] = float(i)
                _upsertSet(s["id"], s, j)

        j.save()
        return Job.get(id=job_id).as_dict()


MAX_RANK = 1000000.0  # Arbitrary


def _genRank(n):
    maxval = MAX_RANK
    stride = int(maxval / (n + 1))  # n+1 to allow for space at beginning
    for i in range(stride, int(maxval + 1), stride):
        yield i


def _rankBalance(cls):
    with DB.queues.atomic():
        # TODO discriminate by queue - may case weirdness with archived jobs
        ranker = _genRank(cls.select().count())
        for (l, c) in zip(ranker, cls.select().order_by(cls.rank)):
            c.rank = l
            c.save()


def _rankEnd():
    return time.time()


def _moveImpl(src, dest_id, retried=False):
    if dest_id is None:
        destRank = 0
    else:
        dest_id = int(dest_id)
        destRank = Job.get(id=dest_id).rank

    # Get the next object having a rank beyond the destination rank,
    # so we can then split the difference
    # Note the unary '&' operator and the expressions wrapped in parens (a limitation of peewee)
    postRank = (
        Job.select(Job.rank)
        .where(
            (Job.rank > destRank)
            & (Job.id != src.id)
            & (Job.queue.name != ARCHIVE_QUEUE)
        )
        .order_by(Job.rank)
        .limit(1)
        .execute()
    )
    if len(postRank) > 0:
        postRank = postRank[0].rank
    else:
        postRank = MAX_RANK
    # Pick the target value as the midpoint between the two ranks
    candidate = abs(postRank - destRank) / 2 + min(postRank, destRank)

    # We may end up with an invalid candidate if we hit a singularity - in this case, rebalance all the
    # rows and try again
    if candidate <= destRank or candidate >= postRank:
        if not retried:
            _rankBalance(Job)
            _moveImpl(src, dest_id, retried=True)
        else:
            raise Exception("Could not rebalance job rank to move job")
    else:
        src.rank = candidate
        src.save()


def moveJob(src_id: int, dest_id: int):
    j = Job.get(id=src_id)
    return _moveImpl(j, dest_id)


def newEmptyJob(q, name="", rank=_rankEnd):
    if type(q) == str:
        q = Queue.get(name=q)
    j = Job.create(
        queue=q,
        rank=rank(),
        name=name,
        count=1,
    )
    return j


def appendSet(queue: str, jid, data: dict, rank=_rankEnd):
    q = Queue.get(name=queue)
    try:
        if jid != "":
            j = Job.get(id=int(jid))
        else:
            j = newEmptyJob(q)
    except Job.DoesNotExist:
        j = newEmptyJob(q)

    if data.get("jobName") is not None:
        j.name = data["jobName"]
    if data.get("jobDraft") is not None:
        draft = data["jobDraft"]
        j.draft = draft is True or (type(draft) == str and draft.lower() == "true")
    if j.is_dirty():
        j.save()

    count = getint(data, "count")
    sd = data.get("sd", "false")
    s = Set.create(
        path=data["path"],
        sd=(sd is True or (type(sd) == str and sd.lower() == "true")),
        rank=rank(),
        material_keys=",".join(data.get("materials", "")),
        profile_keys=",".join(data.get("profiles", "")),
        count=count,
        metadata=data.get("metadata", None),
        remaining=getint(data, "remaining", count),
        completed=getint(data, "completed"),
        job=j,
    )

    return dict(job_id=j.id, set_=s.as_dict())


def remove(queue_ids: list = [], job_ids: list = [], set_ids: list = []):
    result = {}
    with DB.queues.atomic():
        if len(queue_ids) > 0:
            result["queues_deleted"] = (
                Queue.delete().where(Queue.id.in_(queue_ids)).execute()
            )

        # Jobs aren't actually deleted- they go to an archive instead
        q = Queue.get(name="archive")
        if len(job_ids) > 0:
            result["jobs_deleted"] = (
                Job.update(queue=q).where(Job.id.in_(job_ids)).execute()
            )

        # Only delete sets if we haven't already archived their job
        if len(set_ids) > 0:
            result["sets_deleted"] = (
                Set.delete()
                .where((Set.id.in_(set_ids)) & (Set.job.not_in(job_ids)))
                .execute()
            )
    return result


def resetJobs(job_ids: list):
    with DB.queues.atomic():
        # Update the "remaining" counters to reflect the lack of runs
        updated = 0
        if len(job_ids) > 0:
            updated += (
                Job.update(remaining=Job.count).where(Job.id.in_(job_ids)).execute()
            )
        updated += (
            Set.update(remaining=Set.count, completed=0)
            .where(Set.job.in_(job_ids))
            .execute()
        )
        return dict(num_updated=updated)


def beginRun(qname, jname, spath):
    # Abort any unfinished runs before beginning a new run in the job
    Run.update({Run.end: datetime.now(), Run.result: "aborted"}).where(
        (Run.jobName == jname) & (Run.end.is_null())
    ).execute()
    return Run.create(
        queueName=qname, jobName=jname, path=spath
    )  # start defaults to now()


def endRun(r, result: str, txn=None):
    r.end = datetime.now()
    r.result = result
    r.save()


def annotateLastRun(gcode, movie_path, thumb_path):
    # Note: this query assumes that timelapse movie processing completes before
    # the next print completes - this is almost always the case, but annotation may fail if the timelapse
    # is extremely long and the next print extremely short. In this case, the run won't
    # be annotated (but the timelapse will still exist, OctoPrint willing)
    cur = Run.select().order_by(Run.start.desc()).limit(1).execute()
    if len(cur) == 0:
        return False
    run = cur[0]
    if (
        run.movie_path is not None
        or run.thumb_path is not None
        or run.path.split("/")[-1] != gcode
    ):
        return False
    run.movie_path = movie_path
    run.thumb_path = thumb_path
    return run.save() > 0


def getHistory():
    cur = (Run.select().order_by(Run.start.desc()).limit(100)).execute()

    result = [
        dict(
            start=int(c.start.timestamp()),
            end=int(c.end.timestamp()) if c.end is not None else None,
            result=c.result,
            queue_name=c.queueName,
            job_name=c.jobName,
            set_path=c.path,
            run_id=c.id,
            movie_path=c.movie_path,
            thumb_path=c.thumb_path,
        )
        for c in cur
    ]
    return result


def resetHistory():
    Run.delete().execute()


def assignAutomation(scripts, preprocessors, events):
    with DB.automation.atomic():
        EventHook.delete().execute()
        Preprocessor.delete().execute()
        Script.delete().execute()
        s = dict()
        for k, v in scripts.items():
            s[k] = Script.create(name=k, body=v)
        p = dict()
        for k, v in preprocessors.items():
            p[k] = Preprocessor.create(name=k, body=v)

        validEvents = set([e.event for e in CustomEvents])
        for k, e in events.items():
            if k not in validEvents:
                raise KeyError(f"No such CPQ event {k}, options: {validEvents}")
            for i, a in enumerate(e):
                pre = None
                if a.get("preprocessor") not in ("", None):
                    pre = p[a["preprocessor"]]
                EventHook.create(
                    name=k, script=s[a["script"]], preprocessor=pre, rank=i
                )


def getAutomation():
    scripts = dict()
    preprocessors = dict()
    events = dict([(e.event, []) for e in CustomEvents])
    for s in Script.select():
        scripts[s.name] = s.body
    for p in Preprocessor.select():
        preprocessors[p.name] = p.body
    for e in (
        EventHook.select()
        .join_from(EventHook, Script, JOIN.LEFT_OUTER)
        .join_from(EventHook, Preprocessor, JOIN.LEFT_OUTER)
    ):
        events[e.name].append(
            dict(
                script=e.script.name,
                preprocessor=e.preprocessor.name
                if e.preprocessor is not None
                else None,
            )
        )

    return dict(scripts=scripts, events=events, preprocessors=preprocessors)


def getInterpreter(symbols):
    # TODO move to separate file
    out = StringIO()
    err = StringIO()
    interp = Interpreter(writer=out, err_writer=err)
    # Merge in so default symbols (e.g. exceptions) are retained
    for (k, v) in symbols.items():
        interp.symtable[k] = v
    return interp, out, err


def getAutomationForEvent(evt: CustomEvents) -> list:
    return [
        (e.script.body, e.preprocessor.body)
        for e in (
            EventHook.select()
            .join_from(EventHook, Script, JOIN.LEFT_OUTER)
            .join_from(EventHook, Preprocessor, JOIN.LEFT_OUTER)
            .where(EventHook.name == evt.event)
            .order_by(EventHook.rank)
        )
    ]


def genEventScript(automation: list, interp=None, logger=None) -> str:
    # TODO move to separate file
    result = []
    for script, preprocessor in automation:
        procval = True
        if preprocessor is not None and preprocessor.strip() != "":
            procval = interp(preprocessor)
            if logger:
                logger.info(
                    f"EventHook preprocessor: {preprocessor}\nSymbols: {interp.symtable}\nResult: {procval}"
                )

        if procval is None or procval is False:
            continue
        elif procval is True:
            formatted = script
        elif type(procval) is dict:
            if logger:
                logger.info(f"Appending script using formatting data {procval}")
            formatted = script.format(**procval)
        else:
            raise Exception(
                f"Invalid return type {type(procval)} for peprocessor {preprocessor}"
            )

        leftovers = re.findall(r"\{.*?\}", formatted)
        if len(leftovers) > 0:
            ppname = " (preprocessed)" if e.preprocessor is not None else ""
            raise Exception(f"Unformatted placeholders in script{ppname}: {leftovers}")
        result.append(formatted)
    return "\n".join(result)
