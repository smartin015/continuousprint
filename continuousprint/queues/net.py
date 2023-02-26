import uuid
import time
import json
from threading import Thread
from typing import Optional
from bisect import bisect_left
from ..storage.peer import PeerJobView
from ..storage.database import JobView, SetView
from pathlib import Path
from .base import AbstractEditableQueue, QueueData, Strategy, ValidationError
import dataclasses


class NetworkQueue(AbstractEditableQueue):
    def __init__(
        self,
        ns,
        p2p_server,
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
        self._srv = p2p_server
        self.job_id = None
        self.set_id = None
        self.update_cb = update_cb
        self._fileshare = fileshare
        self._path_on_disk = path_on_disk_fn

    # ---------- Network queue methods ---------

    def connect(self):
        self._logger.debug("Waiting for p2p server...")
        while True:
            if self._srv.is_ready() and self._srv.ping():
                break
            time.sleep(1.0)
        Thread(target=self._loop_stream, daemon=True).start()

    def resolve(self, path, peer, hash_):
        raise NotImplementedError()

    def is_ready(self) -> bool:
        return self._srv.is_ready()

    def _loop_stream(self):
        while True:
            self._logger.debug("starting event stream")
            evts = self._srv.stream_events(self.ns)
            for e in evts:
                self._on_update(e)

    def _on_update(self, changetype, prev, nxt):
        self._logger.debug("_on_update:", e.__repr__())
        raise Exception("TODO")
        # self.update_cb(self)

    def update_peer_state(self, name, status, profile):
        if self._srv is not None:
            self._srv.set_status(
                self.ns,
                active_unit=json.dumps(self._active_set()),
                name=name,
                status=str(status),
                profile=str(profile),
            )

    def set_job(self, jid: str, manifest: dict):
        # Preserve peer address of job if present in the manifest
        # TODO construct spb.Record
        return self._srv.set_record(
            self.ns,
            manifest=manifest,
            approver=manifest.get("peer_", None),
            uuid=jid,
            # TODO rank, created,tags
        )

    def get_gjob_dirpath(self, cid):
        # fetch unpacked job from fileshare (may be cached) and return the real path
        return self._fileshare.fetch(hash_, unpack=True)

    # -------- Wrappers around NetworkQueue to add/remove metadata ------

    def _get_jobs(self) -> list:
        if not self._srv.is_ready():
            return []
        records = [r for r in self._srv.get_records(self.ns)]
        return [json.loads(r.manifest) for r in records]

    def _get_job(self, jid) -> dict:
        if not self._srv.is_ready():
            return None
        for r in self._srv.get_records(self.ns, uuid=jid):
            if r.approver == r.signer:
                return json.loads(r.manifest)

    def _get_peers(self) -> list:
        if not self._srv.is_ready():
            return []
        return [p for p in self._srv.get_peers(self.ns)]

    # --------- begin AbstractQueue --------

    def get_job(self) -> Optional[JobView]:
        # Override to ensure the latest data is received
        return self.get_job_view(self.job_id)

    def get_set(self) -> Optional[SetView]:
        if self.job_id is not None and self.set_id is not None:
            # Linear search through sets isn't efficient, but it works.
            j = self.get_job_view(self.job_id)
            for s in j.sets:
                if s.id == self.set_id:
                    return s

    def _peek(self):
        if not self.is_ready():
            return (None, None)
        for data in self._get_jobs():
            acq = data.get("acquired_by_")
            if acq is not None and acq != self.addr:
                continue  # Acquired by somebody else, so don't consider for scheduling
            job = PeerJobView(data, self)
            s = job.next_set(self._profile)
            if s is not None:
                return (job, s)
        return (None, None)

    def acquire(self) -> bool:
        if not self.is_ready():
            return False
        (job, s) = self._peek()
        if job is None or s is None:
            return False
        raise Exception("TODO set_completion to acquire job")
        # if acquireJob(job.id):
        #     self._logger.debug(f"acquire() candidate:\n{job}\n{s}")
        #     self.job_id = job.id
        #     self.set_id = s.id
        #     self._logger.debug("acquire() success")
        #     return True
        # else:
        #     self._logger.debug("acquire() failed")
        #     return False

    def release(self) -> None:
        if self.job_id is not None:
            raise Exception("TODO set_completion to release job")
            # releaseJob(self.job_id)
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
        if self.is_ready():
            jobs = self._get_jobs()
            peers = self._get_peers()
            for j in jobs:
                j["queue"] = self.ns

        return dataclasses.asdict(
            QueueData(
                name=self.ns,
                addr="p2p",
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
            raise Exception("TODO set_record to reset remaining/completed")
            # setJob(jid, j, addr=j["peer_"])

    def remove_jobs(self, job_ids) -> dict:
        n = 0
        for jid in job_ids:
            raise Exception("TODO set_record to delete job")
            # if removeJob(jid) is not None:
            #    n += 1
        return dict(jobs_deleted=n)

    # --------- end AbstractQueue ------

    # --------- AbstractEditableQueue implementation ------

    def get_job_view(self, job_id):
        j = self._get_job(job_id)
        if j is not None:
            return PeerJobView(j, self)

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
        raise Exception("TODO set_record to propagate job peer when importing rom view")
        # setJob(manifest["id"], manifest, addr=getattr(j, "peer", None))
        return manifest["id"]

    def mv_job(self, job_id, after_id, before_id):
        raise Exception("TODO set_record to move job rank")
        # jobs.mv(job_id, after_id)

    def _path_exists(self, fullpath):
        return Path(fullpath).exists()

    def _validate_job(self, j: JobView) -> str:
        peer_profiles = set(
            [p.get("profile", dict()).get("name", "UNKNOWN") for p in self._get_peers()]
        )
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

        # We must resolve the set paths so we have them locally, as editing can
        # also occur on servers other than the one that submitted the job.
        for s in j.sets:
            s.path = s.resolve()

        # We are also now the source of this job
        j.peer = self.addr

        # Exchange the old job for the new job (reuse job ID)
        jid = self.import_job_from_view(j, j.id)
        return self._get_job(jid)
