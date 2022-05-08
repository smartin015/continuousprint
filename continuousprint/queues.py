import time
from enum import Enum, auto
from peerprint.lan_queue import LANPrintQueue
from pathlib import Path
import os
import json


class Strategy(Enum):
    IN_ORDER = auto()
    LEAST_MANUAL = auto()


class AbstractQueue:
    def __init__(self):
        self.assigned = None
        self.run = None

    def peek_job(self):
        raise NotImplementedError

    def acquire_job(self):
        raise NotImplementedError

    def begin_run(self):
        raise NotImplementedError

    def end_run(self):
        raise NotImplementedError

    def as_dict(self):
        raise NotImplementedError

    def get_assignment(self):
        if self.assigned is None:
            peek = self.peek_job()
            if peek is not None:
                self.assigned = self.acquire_job(peek)
                return self.get_assignment()
        else:
            for set_ in self.assigned.sets:
                if set_.remaining > 0:
                    return set_

    def elapsed(self, now=None):
        if now is None:
            now = time.time()
        if self.run is not None:
            return now - self.run.start


class LocalQueue(AbstractQueue):
    def __init__(self, queries, queueName, strategy: Strategy):
        super().__init__()
        self.queries = queries
        self.strategy = strategy
        self.queue = queueName

    def peek_job(self):
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        return self.queries.getNextJobInQueue(self.queue)

    def acquire_job(self, job):
        return job

    def begin_run(self):
        s = self.get_assignment()
        if s is not None:
            self.run = self.queries.beginRun(s)
            return self.run

    def end_run(self, result):
        if self.run is not None:
            self.queries.endRun(self.get_assignment(), self.run, result)
            self.run = None
            if self.peek_job() != self.assigned:
                self.assigned = None

    def as_dict(self):
        active_set = None
        if self.run is not None:
            assigned = self.get_assignment()
            if assigned is not None:
                active_set = assigned.id

        return dict(
            name=self.queue,
            strategy=self.strategy.name,
            jobs=[j.as_dict() for j in self.queries.getJobsAndSets(self.queue)],
            active_set=active_set,
        )


class LANQueue(AbstractQueue):
    def __init__(self, ns, addr, basedir, logger, strategy: Strategy):
        super().__init__()
        self.strategy = strategy
        path = Path(basedir) / ns
        os.makedirs(path, exist_ok=True)
        self.lan = LANPrintQueue(ns, addr, path, logger)

    def peek_job(self):
        for k, j in self.lan.q.jobs.items():
            j = Job.from_dict(j)
            for s in j.sets:
                if s.remaining > 0:
                    return j
            if j.remaining > 0 and j.decrement():
                self.lan.q.jobs[k] = j.as_dict()
                return j

    def acquire_job(self, job):
        if self.lan.q.acquireJob(job["hash"]):
            return

    def begin_run(self):
        raise NotImplementedError

    def end_run(self):
        raise NotImplementedError

    def as_dict(self):
        active_set = None
        assigned = self.get_assignment()
        if assigned is not None:
            active_set = assigned.id
        jobs = []
        if self.lan.q is not None:
            for (hash_, v) in self.lan.q.jobs.items():
                (peer, manifest) = v
                manifest["peer"] = peer
                manifest["hash"] = hash_
                jobs.append(manifest)

        return dict(
            name=self.lan.ns,
            strategy=self.strategy.name,
            jobs=jobs,
            active_set=active_set,
        )

    def destroy(self):
        self.lan.destroy()


# This class treats one or more queues as a unified queue of sorts.
class MultiQueue(AbstractQueue):
    def __init__(self, strategy):
        super().__init__()
        self.strategy = strategy
        self.queues = {}
        self.run = None

    def add(self, name: str, q: AbstractQueue):
        self.queues[name] = q

    def remove(self, name: str):
        if hasattr(self.queues[name], "destroy"):
            self.queues[name].destroy()
        del self.queues[name]

    def get_assignment(self):
        if self.assigned is not None:
            return self.assigned
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        candidates = []
        for k, q in self.queues.items():
            s = q.get_assignment()
            if s is not None:  # Favor ongoing assignments instead of starting new ones
                self.cur = q
                return s
        return None

    def begin_run(self):
        if self.cur is not None:
            return self.cur.begin_run()

    def end_run(self, result):
        if self.cur is not None:
            return self.cur.end_run(result)

    def elapsed(self, now=None):
        if self.cur is not None:
            return self.cur.elapsed()
