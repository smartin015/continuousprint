import json
import time


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
        materials=[],
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
        self.materials = materials
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


# This is a simple print queue that tracks the order of items
# and persists state to Octoprint settings
class PrintQueue:
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
                    materials=v.get("materials", []),
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

    def __len__(self):
        self._load()
        return len(self.q)

    def __delitem__(self, i):
        self._load()
        del self.q[i]
        self._save()

    def __getitem__(self, i):
        self._load()
        return self.q[i]

    def __setitem__(self, i, v):
        self._validate(v)
        self._load()
        self.q[i] = v
        self._save()

    def json(self):
        return self._settings.get([self.key])

    def add(self, items, idx=None):
        for v in items:
            self._validate(v)
        if idx is None:
            idx = len(self.q)
        self._load()
        self.q[idx:idx] = items
        self._save()

    def remove(self, idx, num=0):
        self._load()
        del self.q[idx : idx + num]
        self._save()

    def move(self, fromidx, num, offs):
        self._load()
        slc = self.q[fromidx : fromidx + num]
        self.q = self.q[0:fromidx] + self.q[fromidx + num :]
        self.q = self.q[0 : fromidx + offs] + slc + self.q[fromidx + offs :]
        self._save()

    def pop(self):
        self._load()
        v = self.q.pop(0)
        self._save()
        return v

    def peek(self):
        self._load()
        return self.q[0] if len(self.q) > 0 else None

    def available(self):
        self._load()
        return list(filter(lambda i: i.end_ts is None, self.q))

    def complete(self, path, result):
        self._load()
        for item in self.q:
            if item.end_ts is None and item.path == path:
                item.end_ts = int(time.time())
                item.result = result
                self._save()
                return
        raise Exception("Completed item with path %s not found in queue" % path)
