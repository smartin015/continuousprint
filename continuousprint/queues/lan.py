from peerprint.lan_queue import LANPrintQueue
from ..storage.lan import LANJobView
from ..storage.database import JobView
from pathlib import Path
import os
from .abstract import AbstractJobQueue, QueueData, Strategy

class LANQueue(AbstractJobQueue):
    def __init__(
        self, ns, addr, basedir, logger, strategy: Strategy, update_cb, fileshare, profile
    ):
        super().__init__()
        self._logger = logger
        self._profile = profile
        self.strategy = strategy
        self.ns = ns
        self.basedir = basedir
        self.addr = addr
        self.lan = None
        self.update_cb = update_cb
        self._fileshare = fileshare

    # ---------- LAN queue methods ---------

    def is_ready(self) -> bool:
        return self.lan.q.is_ready()

    def connect(self, testing=False):
        if self.basedir is not None:
            path = Path(self.basedir) / self.ns
            os.makedirs(path, exist_ok=True)
        else:
            path = None
        self.lan = LANPrintQueue(
            self.ns, self.addr, path, self._on_update, self._logger, testing=testing
        )

    def _on_update(self):
        self.update_cb(self)

    def destroy(self):
        self.lan.destroy()

    def update_peer_state(self, name, status, run):
        if self.lan is not None and self.lan.q is not None:
            self.lan.q.syncPeer(
                dict(
                    name=name,
                    status=status,
                    run=run,
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

    def submit_job(self, j: JobView) -> bool:
        filepaths = dict([(s.path, self._path_on_disk(s.path)) for s in j.sets])
        manifest = j.as_dict()
        if manifest.get("created") is None:
            manifest["created"] = int(time.time())

        # Note: postJob strips fields from manifest in-place
        hash_ = self._fileshare.post(manifest, filepaths)
        self.q.queues[queue_name].set_job(hash_, manifest)

    def reset_job(self, job_ids) -> dict:
        pass

    def remove_job(self, job_ids) -> dict:
        pass

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
            has_work = job.normalize()
            compatible = job.is_compatible(self._profile)
            if has_work and compatible:
                s = job.next_set(self._profile)
                if s is not None:
                    return (job, s)
                else:
                    self._logger.debug(f"Skipping job {job.name}; no runnable sets")
            else:
                self._logger.debug(f"Skipping job {job.name}; has_work={has_work}, is_compatible={compatible}")
        return (None, None)

    def acquire(self) -> bool:
        if self.lan is None or self.lan.q is None:
            return False
        (job, s) = self._peek()
        self._logger.debug(f"acquire() candidate:\n{job}\n{s}")
        if job is not None and s is not None and self.lan.q.acquireJob(job.id):
            self.job = job
            self.set = s
            self._logger.debug(f"acquire() success")
            return True
        else:
            self._logger.debug(f"acquire() failed or job/set not given")
            return False

    def release(self) -> None:
        if self.job is not None:
            self.lan.q.releaseJob(self.job.id)
            self.job = None
            self.set = None

    def decrement(self) -> None:
        if self.job is not None:
            has_work = self.set.decrement(save=True)
            if has_work:
                print("Still has work, going for next set")
                self.set = self.job.next_set(self._profile)
                return True
            else:
                print("No more work; releasing")
                self.release()
                return False

    def as_dict(self) -> dict:
        active_set = None
        assigned = self.get_set()
        if assigned is not None:
            active_set = assigned.id
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
                active_set=active_set,
            )
        )
