from typing import Optional
from ..storage.database import Run, SetView
from .base import AbstractQueue, Strategy
import dataclasses


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

    def update_peer_state(self, *args):
        for q in self.queues.values():
            if hasattr(q, "update_peer_state"):
                q.update_peer_state(*args)

    def add(self, name: str, q: AbstractQueue):
        self.queues[name] = q

    def get(self, name: str):
        return self.queues.get(name)

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

    def get_set_or_acquire(self) -> Optional[SetView]:
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

    def remove_jobs(self, job_ids):
        raise Exception("Call contained queue to remove jobs")

    def reset_jobs(self, job_ids):
        raise Exception("Call contained queue to reset jobs")
