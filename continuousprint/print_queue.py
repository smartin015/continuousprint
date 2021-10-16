import json

# This is a simple print queue that tracks the order of items
# and persists state to Octoprint settings
class PrintQueue:
    VALID_ITEM_KEYS = ["count", "name", "path", "sd", "times_run"]  # Must be sorted

    def __init__(self, settings, key):
        self.key = key
        self._settings = settings
        self.q = []
        self._load()

    def _save(self):
        self._settings.set([self.key], json.dumps(self.q))
        self._settings.save()

    def _load(self):
        self.q = json.loads(self._settings.get([self.key]))

    def _validate(self, item):
        ik = list(item.keys())
        ik.sort()
        if ik != self.VALID_ITEM_KEYS:
            raise ValueError(
                f"PrintQueue item must have keys {self.VALID_ITEM_KEYS}; received item with {ik}"
            )

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

    def add(self, item):
        self._validate(item)
        self._load()
        self.q.append(item)
        self._save()

    def move(self, fromidx, toidx):
        self._load()
        v = self.q.pop(fromidx)
        self.q.insert(toidx, v)
        self._save()

    def pop(self):
        self._load()
        v = self.q.pop(0)
        self._save()
        return v

    def peek(self):
        self._load()
        return self.q[0] if len(self.q) > 0 else None

    def setCount(self, i, n):
        self._load()
        self.q[i]["count"] = n
        self._save()
