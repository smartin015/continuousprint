from .database import JobView, SetView
from requests.exceptions import HTTPError


class LANQueueView:
    def __init__(self, lq):
        self.lq = lq
        self.name = lq.ns


class LANJobView(JobView):
    def __init__(self, manifest, lq):
        for attr in ("name", "count", "created"):
            setattr(self, attr, manifest[attr])
        self.remaining = manifest.get("remaining", self.count)
        self.queue = LANQueueView(lq)
        self.id = manifest["id"]
        self.peer = manifest["peer_"]
        self.sets = []
        self.draft = manifest.get("draft", False)
        self.acquired = manifest.get("acquired", False)
        self.sets = [LANSetView(s, self, i) for i, s in enumerate(manifest["sets"])]

    def save(self):
        self.queue.lq.set_job(self.id, self.as_dict())

    def refresh_sets(self):
        for s in self.sets:
            s.remaining = s.count
        self.save()


class ResolveError(Exception):
    pass


class LANSetView(SetView):
    def __init__(self, data, job, rank):
        self.job = job
        self.sd = False
        self.rank = rank
        self.id = f"{job.id}_{rank}"
        for attr in ("path", "count"):
            setattr(self, attr, data[attr])
        self.remaining = data.get("remaining", self.count)
        self.completed = data.get("completed", 0)
        self.material_keys = ",".join(data.get("materials", []))
        self.profile_keys = ",".join(data.get("profiles", []))
        self._resolved = None

    def resolve(self) -> str:
        if self._resolved is None:
            try:
                self._resolved = self.job.queue.lq.resolve_set(
                    self.job.peer, self.job.id, self.path
                )
            except HTTPError as e:
                raise ResolveError(f"Failed to resolve {self.path}") from e
        return self._resolved

    def save(self):
        self.job.save()
