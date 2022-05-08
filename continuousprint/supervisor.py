import time
from enum import Enum, auto


class Strategy(Enum):
    IN_ORDER = auto()
    LEAST_MANUAL = auto()


class AbstractSupervisor:
    def __init__(self, queries):
        self.queries = queries
        self.assigned = None
        self.run = None

    def peek_job(self):
        raise NotImplementedError

    def acquire_job(self):
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

    def begin_run(self):
        s = self.get_assignment()
        if s is not None:
            self.run = self.queries.beginRun(s)
            return self.run

    def end_run(self, result):
        if self.run is not None:
            self.queries.endRun(self.get_assignment(), self.run, result)
            self.run = None
            raise Exception("TODO release job if done")

    def elapsed(self, now=None):
        if now is None:
            now = time.time()
        if self.run is not None:
            return now - self.run.start


# Local supervisor that manages the local (i.e. non-LAN) queue.
class LocalSupervisor(AbstractSupervisor):
    def __init__(self, queries, queueName, strategy: Strategy):
        super().__init__(queries)
        self.strategy = strategy
        self.queue = queueName

    def peek_job(self):
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        return self.queries.getNextJobInQueue(self.queue)

    def acquire_job(self, job):
        return job


class LANSupervisor(AbstractSupervisor):
    def __init__(self, queries, queueName, strategy: Strategy, server):
        super().__init__(queries)
        self.strategy = strategy
        self.queue = queueName
        self.server = server

    def peek_job(self):
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        return self.queries.getNextJobInQueue(self.queue)

    def acquire_job(self, job):
        self.server.acquireJob(job.id)
        return job


# A supervisor of supervisors, this class treats one or more supervisors as a queue of sorts.
class SuperSupervisor(AbstractSupervisor):
    def __init__(self, queries, strategy):
        super().__init__(queries)
        self.strategy = strategy
        self.supervisors = {}
        self.run = None

    def add(self, sup):
        self.supervisors[sup.queue] = sup

    def remove(self, name):
        del self.supervisors[name]

    def get_assignment(self):
        if self.assigned is not None:
            return self.assigned
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        candidates = []
        for s in self.supervisors.values():
            a = s.get_assignment()
            if a is not None:  # Favor ongoing assignments instead of starting new ones
                return a
        return None
