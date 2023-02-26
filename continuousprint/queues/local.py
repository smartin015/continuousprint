from .base import Strategy, QueueData, AbstractFactoryQueue
import tempfile
import shutil
import os
from ..storage.database import JobView, SetView
from peerprint.filesharing import pack_job, unpack_job, packed_name
from pathlib import Path
import dataclasses


class LocalQueue(AbstractFactoryQueue):
    def __init__(
        self,
        queries,
        queueName: str,
        strategy: Strategy,
        profile: dict,
        path_on_disk_fn,
        mkdir_fn,
    ):
        super().__init__()
        self._path_on_disk = path_on_disk_fn
        self._mkdir = mkdir_fn
        self.ns = queueName
        self._profile = profile
        j = queries.getAcquiredJob()
        self.job = j
        self.set = (
            j.next_set(self._profile, self._set_path_exists) if j is not None else None
        )
        self.strategy = strategy
        self.queries = queries

    def _set_path_exists(self, s):
        if type(s) == dict:
            path = self._path_on_disk(s["path"], s["sd"])
        else:
            path = self._path_on_disk(s.path, s.sd)
        if (
            path is None
        ):  # For SD cards etc. assume existence if we can't interrogate the storage layer
            return True
        return Path(path).exists()

    # --------------------- Begin AbstractQueue ------------------

    def resolve(self, path, peer, hash_):
        raise NotImplementedError()

    def acquire(self) -> bool:
        if self.job is not None:
            return True
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        p = self.queries.getNextJobInQueue(
            self.ns, self._profile, self._set_path_exists
        )
        if p is not None and self.queries.acquireJob(p):
            self.job = self.queries.getJob(p.id)  # Refetch job to get acquired state
            self.set = p.next_set(self._profile, self._set_path_exists)
            return True
        return False

    def release(self) -> None:
        if self.job is not None:
            self.queries.releaseJob(self.job)
        self.job = None
        self.set = None

    def decrement(self) -> bool:
        if self.set is None or self.job is None:
            self.release()
            return False

        has_work = self.set.decrement(self._profile) is not None
        earliest_job = self.queries.getNextJobInQueue(
            self.ns, self._profile, self._set_path_exists
        )
        if has_work and earliest_job == self.job and self.job.acquired:
            self.set = self.job.next_set(self._profile, self._set_path_exists)
            return True
        else:
            self.release()
            return False

    def as_dict(self) -> dict:
        active_set = self.get_set()
        if active_set is not None:
            active_set = active_set.id
        jobs = [j.as_dict() for j in self.queries.getJobsAndSets(self.ns)]
        for j in jobs:
            for s in j["sets"]:
                if not self._set_path_exists(s):
                    s["missing_file"] = True
        return dataclasses.asdict(
            QueueData(
                name=self.ns,
                strategy=self.strategy.name,
                jobs=jobs,
                active_set=active_set,
            )
        )

    def remove_jobs(self, job_ids):
        return self.queries.remove(job_ids=job_ids)

    def reset_jobs(self, job_ids):
        return self.queries.resetJobs(job_ids)

    # -------------- end AbstractQueue ------------------

    # -------------- begin AbstractEditableQueue -----------

    def get_job_view(self, job_id):
        return self.queries.getJob(job_id)

    def import_job_from_view(self, v, copy_fn=shutil.copytree):
        manifest = v.as_dict()

        # If importing from a non-local queue, we must also fetch/import the files so they're available locally.
        if hasattr(v, "get_base_dir"):
            dest_dir = f'ContinuousPrint/imports/{manifest["name"]}_{manifest["id"]}'
            gjob_dir = v.get_base_dir()
            copy_fn(gjob_dir, self._path_on_disk(dest_dir, False))
            for s in manifest["sets"]:
                s["path"] = os.path.join(dest_dir, s["path"])

        # TODO make transaction, move to storage/queries.py
        j = self.add_job()
        for (k, v) in manifest.items():
            if k in ("peer_", "sets", "id", "acquired", "queue"):
                continue
            setattr(j, k, v)
        j.save()
        for s in manifest["sets"]:
            del s["id"]
            self.add_set(j.id, s)
        return j.id

    def mv_job(self, job_id, after_id, before_id):
        return self.queries.moveJob(job_id, after_id)

    def edit_job(self, job_id, data):
        return self.queries.updateJob(job_id, data)

    # ------------------- end AbstractEditableQueue ---------------

    # ------------ begin AbstractFactoryQueue ------

    def add_job(self, name="") -> JobView:
        return self.queries.newEmptyJob(self.ns, name)

    def add_set(self, job_id, data) -> SetView:
        return self.queries.appendSet(self.ns, job_id, data)

    def import_job(self, gjob_path: str, draft=True) -> dict:
        out_dir = str(Path(gjob_path).stem)
        self._mkdir(out_dir)
        manifest, filepaths = unpack_job(
            self._path_on_disk(gjob_path, sd=False),
            self._path_on_disk(out_dir, sd=False),
        )
        return self.queries.importJob(self.ns, manifest, out_dir, draft)

    def export_job(self, job_id: int, dest_dir: str) -> str:
        j = self.queries.getJob(job_id)
        filepaths = dict([(s.path, self._path_on_disk(s.path, s.sd)) for s in j.sets])
        for name, fp in filepaths.items():
            if fp is None:
                raise ValueError(
                    f"{j.name} failed to resolve path for {name} (export jobs with files on disk, not SD)"
                )

        with tempfile.NamedTemporaryFile(
            suffix=".gjob", dir=dest_dir, delete=False
        ) as tf:
            pack_job(j.as_dict(), filepaths, tf.name)
            path = packed_name(j.name, dest_dir)
            os.rename(tf.name, path)
            return path

    # ------------------- end AbstractFactoryQueue ---------------
