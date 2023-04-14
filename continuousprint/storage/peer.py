from .database import JobView, SetView
from pathlib import Path
from .queries import getint
from requests.exceptions import HTTPError


class PeerQueueView:
    def __init__(self, q):
        self.q = q
        self.name = q.ns


class PeerJobView(JobView):
    def _load_set(self, data, idx):
        s = PeerSetView()
        s.load_dict(data, self, idx)
        return s

    def load_dict(self, data: dict, queue):
        super().load_dict(data, queue)
        self.peer = data["peer_"]
        self.hash = data.get("hash")
        self.rn = data.get("rn")
        self.rd = data.get("rd")

    def as_dict(self):
        d = super().as_dict()
        d["peer_"] = self.peer
        d["hash"] = self.hash
        if self.rn is not None:
            d["rn"] = self.rn
            d["rd"] = self.rd
            try:
                d["rank"] = self.rn / self.rd
            except ZeroDivisionError:
                d["rank"] = 0
        return d

    def save(self):
        self.queue.q.set_job(self.id, self.as_dict())

    def refresh_sets(self):
        for s in self.sets:
            s.remaining = s.count
            s.completed = 0
        self.save()


class ResolveError(Exception):
    pass


class PeerSetView(SetView):
    def load_dict(self, data, job, rank):
        super().load_dict(data, job, rank)
        self._resolved = None

    def save(self):
        self.job.save()

    def resolve(self, override=None) -> str:
        if self._resolved is None:
            try:
                self._resolved = self.job.queue.q.resolve(self.path, self.job.hash)
            except HTTPError as e:
                raise ResolveError(f"Failed to resolve {self.path}") from e
        return super().resolve(override)
