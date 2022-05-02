from peewee import IntegrityError, JOIN, fn
from typing import Optional
from datetime import datetime
import time
import base64

from .database import Queue, Job, Set, Run, DB


def getJobsAndSets(q=None, lexOrder=False):
    if type(q) == str:
        q = Queue.get(name=q)
    if q is None:
        return []
    cursor = Job.select().join(Set, JOIN.LEFT_OUTER).where(Job.queue == q)
    cursor = cursor.group_by(Job.id)
    if lexOrder:
        cursor = cursor.order_by(Job.lexRank.asc())
    return cursor.execute()


def decrementJobRemaining(j):
    j.remaining = max(j.remaining - 1, 0)
    j.save()
    if j.remaining > 0:
        # Refresh sets within the job if this isn't the last go-around
        Set.update(remaining=Set.count).where(Set.job == j).execute()
        print("Refreshed sets belonging to job", j.id)
        return True
    return False


def getNextSetInQueue(q=None):
    # Need to loop over jobs first to maintain job order
    for job in getJobsAndSets(q=q, lexOrder=True):
        for set_ in job.sets:
            if set_.remaining > 0:
                return set_

        # If we've looped through all sets in the job and all are complete,
        # decrement the job. Pick its first set if there's still more work to be done.
        if job.remaining > 0 and decrementJobRemaining(job):
            return job.sets[0]
    print("No set in queue available for next")


def updateJob(job_id, data, json_safe=False, queue="default"):
    try:
        j = Job.get(id=job_id)
    except Job.DoesNotExist:
        q = Queue.get(name=queue)
        j = newEmptyJob(q)
    for k, v in data.items():
        if k in ("id", "count", "remaining"):  # ignored or handled separately
            continue
        setattr(j, k, v)

    if data.get("count") is not None:
        newCount = int(data["count"])
        inc = newCount - j.count
        j.remaining = min(newCount, j.remaining + max(inc, 0))
        j.count = newCount
        print(
            "Job now count",
            j.count,
            "remaining",
            j.remaining,
            "rtype",
            type(j.remaining),
        )

    j.save()
    return j.as_dict(json_safe)


MAX_LEX = 1000000.0  # Arbitrary


def genLex(n):
    maxval = MAX_LEX
    stride = int(maxval / (n + 1))  # n+1 to allow for space at beginning
    for i in range(stride, int(maxval + 1), stride):
        yield i


def lexBalance(cls):
    with DB.queues.atomic():
        # TODO discriminate by queue - may case weirdness with archived jobs
        lexer = genLex(cls.select().count())
        for (l, c) in zip(lexer, cls.select().order_by(cls.lexRank)):
            c.lexRank = l
            c.save()


def lexEnd():
    return time.time()


def moveSet(src_id: int, dest_id: int, job_id: int, upsert_queue="default"):
    s = Set.get(id=src_id)
    if s.job.id != job_id:
        if job_id == -1:
            j = newEmptyJob(upsert_queue).id
        else:
            j = Job.get(id=job_id)
        s.job = j
        s.save()
    return moveCls(Set, src_id, dest_id)


def moveJob(src_id, dest_id):
    return moveCls(Job, src_id, dest_id)


def moveCls(cls, src_id: int, dest_id: int, retried=False):
    if dest_id == -1:
        destRank = 0
    else:
        destRank = cls.get(id=dest_id).lexRank
    # Get the next object/set having a lexRank beyond the destination rank,
    # so we can then split the difference
    # Note the unary '&' operator and the expressions wrapped in parens (a limitation of peewee)
    postRank = (
        cls.select(cls.lexRank)
        .where((cls.lexRank > destRank) & (cls.id != src_id))
        .limit(1)
        .execute()
    )
    if len(postRank) > 0:
        postRank = postRank[0].lexRank
    else:
        postRank = MAX_LEX
    # Pick the target value as the midpoint between the two lexRanks
    candidate = abs(postRank - destRank) / 2 + min(postRank, destRank)

    # We may end up with an invalid candidate if we hit a singularity - in this case, rebalance all the
    # rows and try again
    if candidate <= destRank or candidate >= postRank:
        if not retried:
            lexBalance(cls)
            moveCls(cls, src_id, dest_id, retried=True)
        else:
            raise Exception("Could not rebalance job lexRank to move job")
    else:
        c = cls.get(id=src_id)
        c.lexRank = candidate
        c.save()


def newEmptyJob(q, lex=lexEnd):
    if type(q) == str:
        q = Queue.get(name=q)
    return Job.create(
        queue=q,
        lexRank=lex(),
        name="",
        count=1,
    )


def appendSet(queue: str, job: str, data: dict, lex=lexEnd):
    q = Queue.get(name=queue)
    try:
        j = Job.get(queue=q, name=job)
    except Job.DoesNotExist:
        j = newEmptyJob(q)
        j.name = job
        j.save()

    count = int(data["count"])
    try:
        s = Set.get(path=data["path"], job=j)
        s.count += count
        s.remaining += count
        s.save()
    except Set.DoesNotExist:
        s = Set.create(
            path=data["path"],
            sd=data["sd"] == "true",
            lexRank=lex(),
            material_keys=",".join(data["material"]),
            count=count,
            remaining=count,
            job=j,
        )
    return dict(job_id=j.id, set_=s.as_dict(json_safe=True))


def updateSet(set_id, data, json_safe=False):
    s = Set.get(id=set_id)
    for k, v in data.items():
        if k in ("id", "count", "remaining"):  # ignored or handled below
            continue
        setattr(s, k, v)

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
    result = s.as_dict(json_safe=json_safe)
    result["job_remaining"] = job_remaining
    return result


def removeJobsAndSets(job_ids: list, set_ids: list):
    q = Queue.get(name="archive")
    with DB.queues.atomic():
        j = Job.update(queue=q).where(Job.id.in_(job_ids)).execute()
        # Only delete sets if we haven't already archived their job
        s = (
            Set.delete()
            .where((Set.id.in_(set_ids)) & (Set.job.not_in(job_ids)))
            .execute()
        )
    return {"jobs_deleted": j, "sets_deleted": s}


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
    return Run.create(job=s.job, path=s.path)  # start defaults to now()


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
                    decrementJobRemaining(j)


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
