import uuid
import os
import json
from typing import Optional
from bisect import bisect_left
from peerprint.wan.wan_queue import PeerPrintQueue, ChangeType
from peerprint.wan.proc import ServerProcessOpts as PPOpts
from ..storage.peer import PeerJobView, PeerQueueView, PeerSetView
from pathlib import Path
from .base import AbstractEditableQueue, QueueData, Strategy, ValidationError
import dataclasses


class Codec:
    PROTOCOL_JSON = "json"

    @classmethod
    def decode(self, data, protocol, logger):
        if protocol == Codec.PROTOCOL_JSON:
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {str(e)}")
        else:
            logger.error(f"No decoder for protocol '{protocol}'")

    @classmethod
    def encode(self, manifest):
        return (json.dumps(manifest).encode("utf8"), self.PROTOCOL_JSON)


class WANQueue(AbstractEditableQueue):
    def __init__(
        self,
        binary_path,
        opts,
        logger,
        strategy: Strategy,
        update_cb,
        fileshare,
        keydir,
        profile,
        path_on_disk_fn,
    ):
        super().__init__()
        self._logger = logger
        self._profile = profile
        self.strategy = strategy
        self.ns = opts.queue
        self.job_id = None
        self.set_id = None
        self.update_cb = update_cb
        self._fileshare = fileshare
        self._path_on_disk = path_on_disk_fn

        self.wq = PeerPrintQueue(
            opts,
            Codec,
            binary_path,
            self._on_update,
            logger=self._logger,
            keydir=keydir,
        )

    # ---------- WAN queue methods ---------

    def is_ready(self) -> bool:
        return self.wq.is_ready()

    def connect(self):
        self.wq.connect()

    def _on_update(self, changetype, prev, nxt):
        print("TODO filter change", changetype)
        self.update_cb(self)

    def destroy(self):
        self.wq.destroy()

    def update_peer_state(self, status, profile):
        if self.wq is not None:
            self.wq.syncPeer(status, profile)

    def set_job(self, jid: str, manifest: dict):
        # Preserve peer address of job if present in the manifest
        return self.wq.setJob(jid, manifest, addr=manifest.get("peer_", None))

    # -------- Wrappers around PeerPrintQueue ------

    def _get_jobs(self) -> list:
        return list(self.wq.getJobs().values())

    def _get_job(self, jid) -> dict:
        return self.wq.getJobs().get(jid)

    def _get_peers(self) -> list:
        return self.wq.getPeers().sample

    # --------- begin AbstractQueue --------

    def get_job(self) -> Optional[PeerJobView]:
        # Override to ensure the latest data is received
        return self.get_job_view(self.job_id)

    def get_set(self) -> Optional[PeerSetView]:
        print("get_set with set_id", self.set_id)
        if self.job_id is not None and self.set_id is not None:
            # Linear search through sets isn't efficient, but it works.
            j = self.get_job_view(self.job_id)
            for s in j.sets:
                if s.id == self.set_id:
                    return s

    def resolve(self, path, peer, hash_):
        base_dir = self.q.get_gjob_dirpath(self.peer, self.hash)
        return str(Path(base_dir) / self.path)

    def _peek(self):
        if self.wq is None:
            return (None, None)
        for data in self._get_jobs():
            acq = data.get("acquired_by_")
            if acq is not None and acq != self.addr:
                continue  # Acquired by somebody else, so don't consider for scheduling
            job = PeerJobView()
            job.load_dict(data, PeerQueueView(self))
            s = job.next_set(self._profile)
            if s is not None:
                return (job, s)
        return (None, None)

    def acquire(self) -> bool:
        if self.wq is None:
            return False
        (job, s) = self._peek()
        if job is not None and s is not None:
            self._logger.debug(f"acquire() candidate:\n{job}\n{s}")
            if self.wq.acquireJob(job.id):
                self.job_id = job.id
                self.set_id = s.id
                self._logger.debug(
                    f"acquire() success for job id {job.id}, set id {s.id}"
                )
                return True
            else:
                self._logger.debug("acquire() failed")
                return False
        else:
            return False

    def release(self) -> None:
        if self.job_id is not None:
            self.wq.releaseJob(self.job_id)
            self.job_id = None
            self.set_id = None

    def decrement(self) -> None:
        if self.job_id is not None:
            next_set = self.get_set().decrement(self._profile)
            if next_set:
                self._logger.debug("Still has work, going for next set")
                self.set_id = next_set.id
                return True
            else:
                self._logger.debug("No more work; releasing")
                self.release()
                return False
        else:
            raise Exception("Cannot decrement; no job acquired")

    def _active_set(self):
        assigned = self.get_set()
        if assigned is not None:
            return assigned.id
        return None

    def as_dict(self) -> dict:
        jobs = []
        peers = {}
        if self.wq is not None:
            jobs = self._get_jobs()
            peers = self._get_peers()
            for j in jobs:
                j["queue"] = self.ns

        return dataclasses.asdict(
            QueueData(
                name=self.ns,
                addr="",
                strategy=self.strategy.name,
                jobs=jobs,
                peers=peers,
                active_set=self._active_set(),
            )
        )

    def reset_jobs(self, job_ids) -> dict:
        for jid in job_ids:
            j = self._get_job(jid)
            if j is None:
                continue

            j["remaining"] = j["count"]
            for s in j.get("sets", []):
                s["remaining"] = s["count"]
                s["completed"] = 0
            self.wq.setJob(jid, j, addr=j["peer_"])

    def remove_jobs(self, job_ids) -> dict:
        n = 0
        for jid in job_ids:
            if self.wq.removeJob(jid) is not None:
                n += 1
        return dict(jobs_deleted=n)

    # --------- end AbstractQueue ------

    # --------- AbstractEditableQueue implementation ------

    def get_job_view(self, job_id):
        j = self._get_job(job_id)
        if j is not None:
            job = PeerJobView()
            job.load_dict(j, PeerQueueView(self))
            print("Loaded view:", job.as_dict())
            return job

    def import_job_from_view(self, j, jid=None):
        err = self._validate_job(j)
        if err is not None:
            raise ValidationError(err)
        filepaths = dict([(s.path, self._path_on_disk(s.path, s.sd)) for s in j.sets])
        manifest = j.as_dict()
        if manifest.get("created") is None:
            manifest["created"] = int(time.time())
        # Note: post mutates manifest by stripping fields
        manifest["hash"] = self._fileshare.post(manifest, filepaths)
        manifest["id"] = jid if jid is not None else self._gen_uuid()

        # Propagate peer if importing from a PeerJobView
        # But don't fail with AttributeError if it's just a JobView
        self.wq.setJob(manifest["id"], manifest, addr=getattr(j, "peer", None))
        return manifest["id"]

    def mv_job(self, job_id, after_id):
        self.wq.jobs.mv(job_id, after_id)

    def _path_exists(self, fullpath):
        return Path(fullpath).exists()

    def _validate_job(self, j: PeerJobView) -> str:
        peer_profiles = set([p.profile or "UNKNOWN" for p in self._get_peers()])

        for s in j.sets:
            sprof = set(s.profiles())
            # All sets in the job *must* have an assigned profile
            if len(sprof) == 0:
                return f"validation for job {j.name} failed - set {s.path} has no assigned profile"

            # At least one printer in the queue must have a compatible proile
            if len(peer_profiles.intersection(sprof)) == 0:
                return f"validation for job {j.name} failed - no match for set {s.path} with profiles {sprof} (connected printer profiles: {peer_profiles})"

            # All set paths must resolve to actual files
            fullpath = self._path_on_disk(s.path, s.sd)
            if fullpath is None or not self._path_exists(fullpath):
                return f"validation for job {j.name} failed - file not found at {s.path} (is it stored on disk and not SD?)"

    def _gen_uuid(self) -> str:
        for i in range(100):
            result = uuid.uuid4()
            if self._get_job(result) is None:
                return str(result)
        raise Exception("UUID generation failed - too many ID collisions")

    def edit_job(self, job_id, data) -> bool:
        # For lan queues, "editing" a job is basically resubmission of the whole thing.
        # This is because the backing .gjob format is a single file containing the full manifest.
        j = self.get_job_view(job_id)
        for (k, v) in data.items():
            if k in ("id", "peer_", "queue"):
                continue
            if k == "sets":
                j.updateSets(
                    v
                )  # Set data must be translated into views, done by updateSets()
            else:
                setattr(j, k, v)

        # Exchange the old job for the new job (reuse job ID)
        jid = self.import_job_from_view(j, j.id)
        return self._get_job(jid)
