import time
from typing import Optional
from enum import Enum, auto
from peerprint.lan_queue import LANPrintQueue
import dataclasses
from .storage.database import Job, Set, Run
from pathlib import Path
from abc import ABC, abstractmethod
import os
import json


class Strategy(Enum):
    IN_ORDER = auto()  # Jobs and sets printed in lexRank order
    LEAST_MANUAL = auto()  # Choose the job which produces the least manual changes


@dataclasses.dataclass
class QueueData:
    name: str
    strategy: str
    jobs: list
    active_set: int
    addr: Optional[str] = None
    peers: list = dataclasses.field(default_factory=list)


class AbstractQueue(ABC):
    """Base class for all queue types.

    Queues are composed of Jobs, which themselves are composed of Sets, as
    defined in storage/database.py.

    Additionally, a queue has "runs" which are individual attempts at printing
    a gcode file.
    """

    def __init__(self):
        self.job = None
        self.set = None

    def get_job(self) -> Optional[Job]:
        return self.job

    def get_set(self) -> Optional[Set]:
        return self.set

    @abstractmethod
    def acquire(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def release(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def decrement(
        self,
    ) -> bool:  # Returns true if the job has more work, false if job complete+released
        raise NotImplementedError

    @abstractmethod
    def as_dict(self) -> dict:
        raise NotImplementedError


class LocalQueue(AbstractQueue):
    def __init__(self, queries, queueName, strategy: Strategy):
        super().__init__()
        self.ns = queueName
        j = queries.getAcquiredJob()
        self.job = j
        self.set = j.next_set() if j is not None else None
        self.strategy = strategy
        self.queries = queries

    def acquire(self) -> bool:
        if self.job is not None:
            return True
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        p = self.queries.getNextJobInQueue(self.ns)
        if p is not None and self.queries.acquireJob(p):
            self.job = p
            self.set = p.next_set()
            return True
        return False

    def release(self) -> None:
        if self.job is not None:
            self.queries.releaseJob(self.job)
        self.job = None
        self.set = None

    def decrement(self) -> bool:
        if self.set is None or self.job is None:
            self.release()
            return False

        has_work = self.set.decrement(save=True)
        if has_work:
            self.set = self.job.next_set()
            return True
        else:
            self.release()
            return False

    def as_dict(self) -> dict:
        active_set = self.get_set()
        if active_set is not None:
            active_set = active_set.id
        return dataclasses.asdict(
            QueueData(
                name=self.ns,
                strategy=self.strategy.name,
                jobs=[j.as_dict() for j in self.queries.getJobsAndSets(self.ns)],
                active_set=active_set,
            )
        )


class LANQueue(AbstractQueue):
    def __init__(self, ns, addr, basedir, logger, strategy: Strategy, update_cb):
        super().__init__()
        self._logger = logger
        self.strategy = strategy
        self.ns = ns
        self.basedir = basedir
        self.addr = addr
        self.lan = None
        self.update_cb = update_cb

    # ---------- LAN queue methods ---------

    def connect(self):
        path = Path(self.basedir) / self.ns
        os.makedirs(path, exist_ok=True)
        self.lan = LANPrintQueue(
            self.ns, self.addr, path, self._on_update, self._logger
        )

    def _on_update(self):
        self._logger.info(f"Queue {self.ns} update")
        self.update_cb(self)

    def destroy(self):
        self.lan.destroy()

    def update_peer_state(self, status, run):
        if self.lan is not None and self.lan.q is not None:
            self.lan.q.syncPeer(status, run)

    # --------- AbstractQueue implementation --------

    def _peekSet(self, job) -> Optional[Set]:
        for s in job.sets:
            if s.remaining > 0:
                return s
        if job.remaining > 0 and job.decrement():
            print(f"TODO set jobs[{k}] = {j.as_dict()}")
            # self.lan.q.jobs[k] = j.as_dict()
            return self._peekJobSet(job)

    def _peek(self):
        if self.lan is None or self.lan.q is None:
            return (None, None)
        for k, addr_man in self.lan.q.jobs.items():
            job = Job.from_dict(addr_man[1])  # j = (address, manifest)
            job.hash = k
            s = self._peekSet(job)
            if s is not None:
                return (job, s)
        return (None, None)

    def acquire(self) -> bool:
        if self.lan is None or self.lan.q is None:
            return False
        (job, s) = self._peek()
        if job is not None and s is not None and self.lan.q.acquireJob(job.hash):
            self.job = job
            self.set = s
            return True
        return False

    def release(self) -> None:
        if self.job is not None:
            self.lan.q.releaseJob(self.job.hash)
            self.job = None
            self.set = None

    def get_job(self):
        if self.job is not None:
            return Job.from_dict(self.job)

    def get_set(self):
        raise NotImplementedError

    def decrement(self) -> None:
        if self.job is not None:
            j = Job.from_dict(self.job)
            j.decrement()
            self.lan.q.jobs[self.job.hash] = j.as_dict()
            raise Exception("TODO return true/false based on release of job")

    def as_dict(self) -> dict:
        active_set = None
        assigned = self.get_set()
        if assigned is not None:
            active_set = assigned.id
        jobs = []
        peers = {}
        if self.lan.q is not None:
            jobs = self.lan.q.getJobs()
            peers = self.lan.q.getPeers()

        return dataclasses.asdict(
            QueueData(
                name=self.lan.ns,
                addr=self.addr,
                strategy=self.strategy.name,
                jobs=jobs,
                peers=peers,
                active_set=active_set,
            )
        )


# This class treats one or more queues as a unified queue of sorts.
# Note that runs are implemented at this level and not lower queue levels,
# so that history can be appropriately preserved for all queue types
class MultiQueue(AbstractQueue):
    def __init__(self, queries, strategy, update_cb):
        super().__init__()
        self.queries = queries
        self.strategy = strategy
        self.queues = {}
        self.run = None
        self.active_queue = None
        self.update_cb = update_cb

    def update_peer_state(self, status, run):
        for q in self.queues.values():
            if hasattr(q, "update_peer_state"):
                q.update_peer_state(status, run)

    def add(self, name: str, q: AbstractQueue):
        if hasattr(q, "connect"):
            q.connect()
        self.queues[name] = q

    def remove(self, name: str):
        q = self.queues.get(name)
        if q is None:
            return
        if hasattr(q, "destroy"):
            q.destroy()
        del self.queues[name]

    def get_job(self):
        if self.active_queue is not None:
            return self.active_queue.get_job()

    def get_set(self):
        if self.active_queue is not None:
            return self.active_queue.get_set()

    def get_set_or_acquire(self) -> Optional[Set]:
        s = self.get_set()
        if s is not None:
            return s
        if self.acquire():
            r = self.get_set()
            return r
        return None

    def begin_run(self) -> Optional[Run]:
        if self.active_queue is not None:
            self.run = self.queries.beginRun(
                self.active_queue.ns,
                self.get_job().name,
                self.get_set().path,
            )
            self.update_cb()

    def get_run(self) -> Optional[Run]:
        return self.run

    def end_run(self, result) -> None:
        if self.run is not None:
            self.queries.endRun(self.run, result)
            self.decrement()
            self.update_cb()

    # ---------- AbstractQueue Implementation -----------

    def acquire(self) -> bool:
        if self.strategy != Strategy.IN_ORDER:
            raise Exception("Unimplemented strategy " + self.strategy.name)
        if self.active_queue is not None:
            print(
                "Already acquired - TODO need to somehow repopulate set when queue already acquired but last set of a job is completed"
            )
            return True
        for k, q in self.queues.items():
            if q.acquire():
                self.active_queue = q
                self.run = self.queries.getActiveRun(
                    self.active_queue.ns, self.get_job().name, self.get_set().path
                )
                return True
        return False

    def release(self) -> None:
        if self.active_queue is not None:
            self.active_queue.release()
            self.active_queue = None

    def decrement(self) -> bool:
        if self.active_queue is not None:
            continue_job = self.active_queue.decrement()
            if not continue_job:
                self.active_queue = None
            return continue_job

    def as_dict(self) -> dict:
        return dataclasses.asdict(
            QueueData(
                name=self.name,
                strategy=self.strategy.name,
                jobs=[],
                active_set=None,  # TODO?
            )
        )
