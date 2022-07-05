from peerprint.lan_queue import LANPrintQueue
from ..storage.lan import LANJobView
from ..storage.database import JobView
from pathlib import Path
from .abstract import AbstractJobQueue, QueueData, Strategy
import dataclasses


class LANQueue(AbstractJobQueue):
    def __init__(
        self,
        ns,
        addr,
        logger,
        strategy: Strategy,
        update_cb,
        fileshare,
        profile,
        path_on_disk_fn,
    ):
        super().__init__()
        self._logger = logger
        self._profile = profile
        self.strategy = strategy
        self.ns = ns
        self.addr = addr
        self.lan = None
        self.update_cb = update_cb
        self._fileshare = fileshare
        self._path_on_disk = path_on_disk_fn
        self.lan = LANPrintQueue(self.ns, self.addr, self._on_update, self._logger)

    # ---------- LAN queue methods ---------

    def is_ready(self) -> bool:
        return self.lan.q.is_ready()

    def connect(self):
        self.lan.connect()

    def _on_update(self):
        self.update_cb(self)

    def destroy(self):
        self.lan.destroy()

    def update_peer_state(self, name, status, run, profile):
        if self.lan is not None and self.lan.q is not None:
            self.lan.q.syncPeer(
                dict(
                    active_set=self._active_set(),
                    name=name,
                    status=status,
                    run=run,
                    profile=profile,
                    fs_addr=f"{self._fileshare.host}:{self._fileshare.port}",
                )
            )

    def set_job(self, hash_: str, manifest: dict):
        return self.lan.q.setJob(hash_, manifest)

    def resolve_set(self, peer, hash_, path) -> str:
        # Get fileshare address from the peer
        peerstate = self.lan.q.getPeers().get(peer)
        if peerstate is None:
            raise Exception(
                "Cannot resolve set {path} within job hash {hash_}; peer state is None"
            )

        # fetch unpacked job from fileshare (may be cached) and return the real path
        gjob_dirpath = self._fileshare.fetch(peerstate["fs_addr"], hash_, unpack=True)
        return str(Path(gjob_dirpath) / path)

    # --------- AbstractJobQueue implementation ------

    def _validate_job(self, j: JobView) -> str:
        peer_profiles = set(
            [
                p.get("profile", dict()).get("name", "UNKNOWN")
                for p in self.lan.q.getPeers().values()
            ]
        )

        for s in j.sets:
            sprof = set(s.profiles())
            # All sets in the job *must* have an assigned profile
            if len(sprof) == 0:
                return f"validation for job {j.name} failed - set {s.path} has no assigned profile"

            # At least one printer in the queue must have a compatible proile
            if len(peer_profiles.intersection(sprof)) == 0:
                return f"validation for job {j.name} failed - no match for set {s.path} with profiles {sprof}, candidates {peer_profiles}"

            # All set paths must resolve to actual files
            fullpath = self._path_on_disk(s.path)
            if not Path(fullpath).exists():
                return (
                    f"validation for job {j.name} failed - file not found at {fullpath}"
                )

    def submit_job(self, j: JobView) -> bool:
        err = self._validate_job(j)
        if err is not None:
            self._logger.warning(err)
            return Exception(err)
        filepaths = dict([(s.path, self._path_on_disk(s.path)) for s in j.sets])
        manifest = j.as_dict()
        if manifest.get("created") is None:
            manifest["created"] = int(time.time())
        # Note: postJob strips fields from manifest in-place
        hash_ = self._fileshare.post(manifest, filepaths)
        self.lan.q.setJob(hash_, manifest)

    def reset_jobs(self, job_ids) -> dict:
        for jid in job_ids:
            j = self.lan.q.jobs.get(jid)
            if j is None:
                continue
            (addr, manifest) = j

            manifest["remaining"] = manifest["count"]
            for s in manifest.get("sets", []):
                s["remaining"] = s["count"]
            self.lan.q.setJob(jid, manifest, addr=addr)

    def remove_jobs(self, job_ids) -> dict:
        for jid in job_ids:
            self.lan.q.removeJob(jid)

    # --------- AbstractQueue implementation --------

    def _peek(self):
        if self.lan is None or self.lan.q is None:
            return (None, None)
        jobs = self.lan.q.getJobs()
        jobs.sort(
            key=lambda j: j["created"]
        )  # Always creation order - there is no reordering in lan queue
        for data in jobs:
            self._logger.debug(data)
            acq = data.get("acquired_by_")
            if acq is not None and acq != self.addr:
                self._logger.debug(f"Skipping job; acquired by {acq}")
                continue  # Acquired by somebody else, so don't consider for scheduling
            job = LANJobView(data, self)
            s = job.next_set(self._profile)
            if s is not None:
                return (job, s)
            else:
                self._logger.debug(f"Skipping job {job.name}; no compatible sets")
        return (None, None)

    def acquire(self) -> bool:
        if self.lan is None or self.lan.q is None:
            return False
        (job, s) = self._peek()
        self._logger.debug(f"acquire() candidate:\n{job}\n{s}")
        if job is not None and s is not None and self.lan.q.acquireJob(job.id):
            self.job = job
            self.set = s
            self._logger.debug("acquire() success")
            return True
        else:
            self._logger.debug("acquire() failed or job/set not given")
            return False

    def release(self) -> None:
        if self.job is not None:
            self.lan.q.releaseJob(self.job.id)
            self.job = None
            self.set = None

    def decrement(self) -> None:
        if self.job is not None:
            next_set = self.set.decrement(self._profile)
            if next_set:
                self._logger.debug("Still has work, going for next set")
                self.set = next_set
                return True
            else:
                self._logger.debug("No more work; releasing")
                self.release()
                return False

    def _active_set(self):
        assigned = self.get_set()
        if assigned is not None:
            return assigned.id
        return None

    def as_dict(self) -> dict:
        jobs = []
        peers = {}
        if self.lan.q is not None:
            jobs = self.lan.q.getJobs()
            jobs.sort(
                key=lambda j: j["created"]
            )  # Always creation order - there is no reordering in lan queue
            peers = self.lan.q.getPeers()

        return dataclasses.asdict(
            QueueData(
                name=self.lan.ns,
                addr=self.addr,
                strategy=self.strategy.name,
                jobs=jobs,
                peers=peers,
                active_set=self._active_set(),
            )
        )
