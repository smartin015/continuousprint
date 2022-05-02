import time


class Supervisor:
    def __init__(self, queries, queueName):
        self.queue = queueName
        self.queries = queries
        self.assigned = None
        self.run = None

    def clear_cache(self):
        self.assigned = None

    def get_assignment(self):
        if self.assigned is None:
            self.assigned = self.queries.getNextSetInQueue(self.queue)
        return self.assigned

    def begin_run(self):
        s = self.get_assignment()
        if s is not None:
            self.run = self.queries.beginRun(s)
            return self.run

    def end_run(self, result):
        if self.run is not None:
            self.queries.endRun(self.get_assignment(), self.run, result)
            self.run = None
            self.clear_cache()  # Ensure we pick up the next assignment if we've tapped this one out

    def elapsed(self, now=None):
        if now is None:
            now = time.time()
        if self.run is not None:
            return now - self.run.start
