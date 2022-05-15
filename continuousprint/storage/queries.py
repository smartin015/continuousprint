from peewee import IntegrityError, JOIN, fn
from typing import Optional
from datetime import datetime
import time
import base64

from .database import Queue, Job, Set, Run, DB, DEFAULT_QUEUE, ARCHIVE_QUEUE


def getQueues():
    return Queue.select().order_by(Queue.rank.asc())


def getAcquired():
    r = Run.select().where(Run.end.is_null()).limit(1).execute()
    if len(r) > 0:
        r = r[0]
        j = r.job
        for s in j.sets:
            if s.remaining > 0 and s.path == r.path:
                return (j, s, r)
    return (None, None, None)


def assignQueues(queues):
    # Default/archive queues should never be removed
    names = set([qdata["name"] for qdata in queues] + [DEFAULT_QUEUE, ARCHIVE_QUEUE])
    with DB.queues.atomic():
        qq = getQueues()
        qq_names = set([q.name for q in qq])
        absent = [(q.id, q.name) for q in qq if q.name not in names]
        if len(absent) > 0:
            (absent_ids, absent_names) = zip(*absent)
            print("Delete", absent_ids)
            Queue.delete().where(Queue.id.in_(absent_ids))
        else:
            absent_names = []
        added = [q for q in queues if q["name"] not in qq_names]
        added_names = set([q["name"] for q in added])
        for rank, qdata in enumerate(queues):
            if qdata["name"] in added_names:
                print("Create", qdata)
                Queue.create(
                    name=qdata["name"],
                    strategy=qdata["strategy"],
                    addr=qdata["addr"],
                    rank=rank,
                )
            else:
                print("Update", qdata)
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


def getNextJobInQueue(q=None):
    # Need to loop over jobs first to maintain job order
    for job in getJobsAndSets(q):
        has_work = job.normalize()
        if has_work:
            return job


def _updateSet(set_id, data, job):
    # Called internally from updateJob
    s = Set.get(id=set_id)
    for k, v in data.items():
        if k in ("id", "count", "remaining"):  # ignored or handled below
            continue
        setattr(s, k, v)
    s.job = job

    if data.get("count") is not None:
        newCount = int(data["count"])
        inc = newCount - s.count
        s.count = newCount
        s.remaining = min(newCount, s.remaining + max(inc, 0))
        # Boost job remaining if we would cause it to be incomplete
        job_remaining = s.job.remaining
        if inc > 0 and job_remaining == 0:
            job_remaining = 1
            s.job.remaining = 1
            s.job.save()
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
                "count",
                "remaining",
                "sets",
            ):  # ignored or handled separately
                continue
            setattr(j, k, v)

        if data.get("count") is not None:
            newCount = int(data["count"])
            inc = newCount - j.count
            j.remaining = min(newCount, j.remaining + max(inc, 0))
            j.count = newCount

        j.save()

        if data.get("sets") is not None:
            for s in data["sets"]:
                _updateSet(s["id"], s, j)
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


def _moveImpl(cls, src, dest_id: int, retried=False):
    if dest_id == -1:
        destRank = 0
    else:
        destRank = cls.get(id=dest_id).rank

    # Get the next object having a rank beyond the destination rank,
    # so we can then split the difference
    # Note the unary '&' operator and the expressions wrapped in parens (a limitation of peewee)
    postRank = (
        cls.select(cls.rank)
        .where((cls.rank > destRank) & (cls.id != src.id))
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
            _rankBalance(cls)
            _moveImpl(cls, src, dest_id, retried=True)
        else:
            raise Exception("Could not rebalance job rank to move job")
    else:
        src.rank = candidate
        src.save()


def moveJob(src_id: int, dest_id: int):
    j = Job.get(id=src_id)
    return _moveImpl(Job, j, dest_id)


def moveSet(src_id: int, dest_id: int, dest_job: int):
    s = Set.get(id=src_id)
    if dest_job == -1:
        j = newEmptyJob(s.job.queue)
    else:
        j = Job.get(id=dest_job)
    s.job = j
    s.save()
    _moveImpl(Set, s, dest_id)


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


def appendSet(queue: str, job, data: dict, rank=_rankEnd):
    q = Queue.get(name=queue)
    if job == "":
        j = newEmptyJob(q)
    else:
        try:
            j = Job.get(queue=q, name=job)
        except Job.DoesNotExist:
            j = newEmptyJob(q, name=job)

    count = int(data["count"])
    s = Set.create(
        path=data["path"],
        sd=data["sd"] == "true",
        rank=rank(),
        material_keys=",".join(data["material"]),
        count=count,
        remaining=count,
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


def replenish(job_ids: list, set_ids: list):
    with DB.queues.atomic():
        # Update the "remaining" counters to reflect the lack of runs
        updated = 0
        if len(job_ids) > 0:
            updated += (
                Job.update(remaining=Job.count).where(Job.id.in_(job_ids)).execute()
            )
        if len(set_ids) > 0:
            updated += (
                Set.update(remaining=Set.count).where(Set.id.in_(set_ids)).execute()
            )
        return dict(num_updated=updated)


def beginRun(s):
    # Abort any unfinished runs before beginning a new run in the set
    Run.update({Run.end: datetime.now(), Run.result: "aborted"}).where(
        (Run.job == s.job) & (Run.end.is_null())
    ).execute()
    j = s.job
    return Run.create(
        queueName=j.queue.name, jobName=j.name, job=s.job, path=s.path
    )  # start defaults to now()


def endRun(s, r, result: str, txn=None):
    with DB.queues.atomic():
        r.end = datetime.now()
        r.result = result
        r.save()

        if result == "success":
            # Decrement set remainder
            s.remaining = max(s.remaining - 1, 0)
            s.save()

            # If we've tapped out the set remaining amounts for the job, decrement job remaining (and refresh sets)
            if s.remaining <= 0:
                j = s.job
                totalRemaining = (
                    Set.select(fn.SUM(Set.remaining).alias("count"))
                    .where(Set.job == j)
                    .execute()[0]
                    .count
                )
                if totalRemaining == 0:
                    j.decrement(save=True)


def getHistory():
    cur = (
        Run.select(Run.start, Run.end, Run.result, Run.path, Job.name, Job.id, Run.id)
        .join_from(Run, Job)
        .order_by(Run.start.desc())
        .limit(1000)
    ).execute()

    result = [
        dict(
            start=int(c.start.timestamp()),
            end=int(c.end.timestamp()) if c.end is not None else None,
            result=c.result,
            set_path=c.path,
            job_name=c.job.name,
            job_id=c.job.id,
            run_id=c.id,
        )
        for c in cur
    ]
    return result


def clearHistory():
    Run.delete().execute()
