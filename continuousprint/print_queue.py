import json
import time
from typing import Optional

class QueueJob:
  pass
  # TODO


class QueueItem:
    # See QueueItem in continuousprint.js for matching JS object
    def __init__(
        self,
        name,
        path,
        sd,
        start_ts=None,
        end_ts=None,
        result=None,
        job="",
        run=0,
        retries=0,
    ):
        self.name = name
        self.path = path
        if type(sd) == str:
            sd = sd.lower() == "true"
        if type(sd) != bool:
            raise Exception("SD must be bool, got %s" % (type(sd)))
        self.sd = sd
        self.job = job
        self.run = run
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.result = result
        self.retries = retries

    def __eq__(self, other):
        return (
            self.name == other.name
            and self.path == other.path
            and self.sd == other.sd
            and self.job == other.job
            and self.run == other.run
        )

class PrintQueueInterface:
    def addJob(self, job: QueueJob):
      raise Exception("Unimplemented")
      
    def removeJob(self, name: str) -> QueueJob:
      raise Exception("Unimplemented")

    def peekJob(self) -> QueueJob:
      raise Exception("Unimplemented")

    def acquireJob(self) -> QueueJob:
      raise Exception("Unimplemented")

    def releaseJob(self, result: str):
      raise Exception("Unimplemented")

# This is a simple print queue that tracks the order of items
# and persists state to Octoprint settings
class PrintQueue(PrintQueueInterface):
    def __init__(self, settings, key, logger=None):
        self.key = key
        self._logger = logger
        self._settings = settings
        self.q = []
        self._load()

    def _save(self):
        self._settings.set([self.key], json.dumps([i.__dict__ for i in self.q]))
        self._settings.save()

    def _load(self):
        items = []
        for v in json.loads(self._settings.get([self.key])):
            if v.get("path") is None:
                if self._logger is not None:
                    self._logger.error(f"Invalid queue item {str(v)}, ignoring")
                continue
            items.append(
                QueueItem(
                    name=v.get(
                        "name", v["path"]
                    ),  # Use path if name not given (old plugin version data may do this)
                    path=v["path"],
                    sd=v.get("sd", False),
                    start_ts=v.get("start_ts"),
                    end_ts=v.get("end_ts"),
                    result=v.get("result"),
                    job=v.get("job"),
                    run=v.get("run"),
                    retries=v.get("retries", 0),
                )
            )
        self.assign(items)

    def _validate(self, item):
        if not isinstance(item, QueueItem):
            raise Exception("Invalid queue item: %s" % item)

    def assign(self, items):
        for v in items:
            self._validate(v)
        self.q = list(items)
        self._save()

    def clear(self, keep_fn):
        self._load()
        self.q = [i for i in self.q if keep_fn(i)]
        self._save()
    
    def _next_available_idx(self):
        self._load()
        for (i, item) in enumerate(self.q):
            if item.end_ts is None:
                return i
        return None

    def startActiveItem(self, **kwargs):
        idx = self._next_available_idx()
        if idx is not None:
            self._active = self.q[idx]

    def getActiveItem(self) -> Optional[QueueItem]:
        return self._active
    
    def completeActiveItem(self, result, end_ts = int(time.time())):
        self._active.end_ts = end_ts
        self._active.result = result
        self.q[self._active.idx] = self._active
        self._save()
        self._active = None
    
    def getNext(self) -> Optional[QueueItem]:
        self._load()
        idx = self._next_available_idx()
        if idx is not None:
            return self.q[idx]
