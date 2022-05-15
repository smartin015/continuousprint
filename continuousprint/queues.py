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
    def decrement(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def as_dict(self) -> dict:
        raise NotImplementedError


class LocalQueue(AbstractQueue):
    def __init__(self, queries, queueName, strategy: Strategy):
        super().__init__()
        self.queue = queueName
        (j, s, r) = queries.getAcquired()
        self.job = j
        self.set = s
        self.strategy = strategy
        self.queries = queries

    def acquire(self) -> bool:
        if self.job is not None:
            return True
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        p = self.queries.getNextJobInQueue(self.queue)
        if p is not None and self.queries.acquireJob(p):
            (j, s, r) = self.queries.getAcquired()
            self.job = j
            self.set = s
            return True
        return False

    def release(self) -> None:
        self.queries.release(self.job, self.set)
        self.job = None
        self.set = None

    def decrement(self) -> None:
        if self.job is not None:
            self.queries.decrement(self.job, self.set)

    def as_dict(self) -> dict:
        return dataclasses.asdict(
            QueueData(
                name=self.queue,
                strategy=self.strategy.name,
                jobs=[j.as_dict() for j in self.queries.getJobsAndSets(self.queue)],
                active_set=None,  # TODO?
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
        self.update_cb = update_cb
        self.lan = None

    # ---------- LAN queue methods ---------

    def connect(self):
        path = Path(self.basedir) / self.ns
        os.makedirs(path, exist_ok=True)
        self.lan = LANPrintQueue(self.ns, self.addr, path, self._on_ready, self._logger)

    def _on_ready(self, _):
        self._logger.info(f"Queue {self.ns} ready")
        self.update_cb(self.ns)

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

    def decrement(self) -> None:
        if self.job is not None:
            j = Job.from_dict(self.job)
            j.decrement()
            self.lan.q.jobs[self.job.hash] = j.as_dict()

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
    def __init__(self, queries, strategy):
        super().__init__()
        self.queries = queries
        self.strategy = strategy
        self.queues = {}
        self.run = None
        self.active_queue = None

    def update_peer_state(self, status, run):
        for q in self.queues.values():
            if hasattr(q, "update_peer_state"):
                q.update_peer_state(status, run)

    def add(self, name: str, q: AbstractQueue):
        if hasattr(q, "connect"):
            q.connect()
        self.queues[name] = q

    def remove(self, name: str):
        if hasattr(self.queues[name], "destroy"):
            self.queues[name].destroy()
        del self.queues[name]

    def get_set_or_acquire(self) -> Optional[Set]:
        s = self.get_set()
        if s is not None:
            return s
        if self.acquire():
            return self.get_set()
        return None

    def begin_run(self) -> Optional[Run]:
        if self.active_queue is not None:
            self.run = self.queries.beginRun(
                self.active_queue.get_job(), self.active_queue.get_set()
            )

    def get_run(self) -> Optional[Run]:
        return self.run

    def end_run(self, result) -> None:
        if self.active_queue is not None:
            self.queries.endRun(
                self.active_queue.get_job(), self.active_queue.get_set(), self.run
            )
            self.active_queue.decrement()

    # ---------- AbstractQueue Implementation -----------

    def acquire(self) -> bool:
        if self.strategy != Strategy.IN_ORDER:
            raise Exception("Unimplemented strategy " + self.strategy.name)
        if self.active_queue is not None:
            return True
        for k, q in self.queues.items():
            if q.acquire():
                self.active_queue = q
                self.run = queries.getActiveRun(
                    self.active_queue.get_job(), self.active_queue.get_set()
                )
                return True
        return False

    def release(self) -> None:
        if self.active_queue is not None:
            self.active_queue.release()
            self.active_queue = None

    def decrement(self) -> None:
        if self.active_queue is not None:
            return self.active_queue.decrement()

    def as_dict(self) -> dict:
        return dataclasses.asdict(
            QueueData(
                name=self.name,
                strategy=self.strategy.name,
                jobs=[],
                active_set=None,  # TODO?
            )
        )
