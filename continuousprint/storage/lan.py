from .database import JobView, SetView
from pathlib import Path
from .queries import getint
from requests.exceptions import HTTPError


class LANQueueView:
    def __init__(self, lq):
        self.lq = lq
        self.name = lq.ns


class LANJobView(JobView):
    def __init__(self, manifest, lq):
        # === Fields present in JobView ===
        self.name = manifest.get("name", "")
        self.created = getint(manifest, "created")
        self.count = getint(manifest, "count")
        self.remaining = getint(manifest, "remaining", default=self.count)
        self.queue = LANQueueView(lq)
        self.id = manifest["id"]
        self.updateSets(manifest["sets"])
        self.draft = manifest.get("draft", False)
        self.acquired = manifest.get("acquired", False)

        # === LANJobView specific fields ===
        self.peer = manifest["peer_"]
        self.hash = manifest.get("hash")

    def get_base_dir(self):
        return self.queue.lq.get_gjob_dirpath(self.peer, self.hash)

    def remap_set_paths(self):
        # Replace all relative/local set paths with fully resolved paths
        for s in self.sets:
            s.path = s.resolve()

    def updateSets(self, sets_list):
        self.sets = [LANSetView(s, self, i) for i, s in enumerate(sets_list)]

    def save(self):
        # as_dict implemented in JobView doesn't handle LANJobView specific fields, so we must inject them here.
        d = self.as_dict()
        d["peer_"] = self.peer
        d["hash"] = self.hash
        self.queue.lq.set_job(self.id, d)

    def refresh_sets(self):
        for s in self.sets:
            s.remaining = s.count
            s.completed = 0
        self.save()


class ResolveError(Exception):
    pass


class LANSetView(SetView):
    def __init__(self, data, job, rank):
        self.job = job
        self.sd = False
        self.rank = int(rank)
        self.id = f"{job.id}_{rank}"
        for attr in ("path", "count"):
            setattr(self, attr, data[attr])
        self.remaining = getint(data, "remaining", default=self.count)
        self.completed = getint(data, "completed")
        self.metadata = data.get("metadata")
        self.material_keys = ",".join(data.get("materials", []))
        self.profile_keys = ",".join(data.get("profiles", []))
        self._resolved = None

    def resolve(self) -> str:
        if self._resolved is None:
            try:
                self._resolved = str(Path(self.job.get_base_dir()) / self.path)
            except HTTPError as e:
                raise ResolveError(f"Failed to resolve {self.path}") from e
        return self._resolved

    def save(self):
        self.job.save()
