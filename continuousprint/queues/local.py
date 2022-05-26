from .abstract import Strategy, QueueData, AbstractEditableQueue
from ..storage.database import JobView, SetView
import os
from peerprint.filesharing import unpack_job
import dataclasses


class LocalQueue(AbstractEditableQueue):
    def __init__(
        self,
        queries,
        queueName: str,
        strategy: Strategy,
        profile: dict,
        path_on_disk_fn,
    ):
        super().__init__()
        self._path_on_disk = path_on_disk_fn
        self.ns = queueName
        self._profile = profile
        j = queries.getAcquiredJob()
        self.job = j
        self.set = j.next_set(self._profile) if j is not None else None
        self.strategy = strategy
        self.queries = queries

    # --------------------- Begin AbstractQueue ------------------

    def acquire(self) -> bool:
        if self.job is not None:
            return True
        if self.strategy != Strategy.IN_ORDER:
            raise NotImplementedError
        p = self.queries.getNextJobInQueue(self.ns, self._profile)
        if p is not None and self.queries.acquireJob(p):
            self.job = p
            self.set = p.next_set(self._profile)
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

        has_work = self.set.decrement(save=True)
        if has_work:
            self.set = self.job.next_set(self._profile)
            return True
        else:
            self.release()
            return False

    def as_dict(self) -> dict:
        active_set = self.get_set()
        if active_set is not None:
            active_set = active_set.id
        return dataclasses.asdict(
            QueueData(
                name=self.ns,
                strategy=self.strategy.name,
                jobs=[j.as_dict() for j in self.queries.getJobsAndSets(self.ns)],
                active_set=active_set,
            )
        )

    # -------------- end AbstractQueue ------------------

    # -------------- begin AbstractEditableQueue -----------

    def add_job(self) -> JobView:
        return self.queries.newEmptyJob(self.ns)

    def add_set(self, job_id, data) -> SetView:
        return self.queries.appendSet(self.ns, job_id, data)

    def mv_set(self, set_id, after_id, dest_job):
        return self.queries.moveSet(set_id, after_id, dest_job)

    def mv_job(self, job_id, after_id):
        return self.queries.moveJob(job_id, after_id)

    def edit_job(self, job_id, data):
        return self.queries.updateJob(job_id, data)

    def rm_multi(self, job_ids, set_ids) -> dict:
        return self.queries.remove(job_ids, set_ids)

    def import_job(self, gjob_path: str) -> dict:
        out_dir = str(Path(gjob_path).stem)
        os.makedirs(dirname, exist_ok=True)
        manifest, filepaths = unpack_job(
            self._path_on_disk(gjob_path), self._path_on_disk(dirname)
        )
        return self.queries.importJob(self.ns, manifest, out_dir)

    def export_job(self, job_id: int, dest_dir: str) -> str:
        j = self.queries.getJob(job_id)
        filepaths = dict([(s.path, self._path_on_disk(s.path)) for s in j.sets])
        with tempfile.NamedTemporaryFile(
            suffix=".gjob", dir=dest_dir, delete=False
        ) as tf:
            pack_job(j.as_dict(), filepaths, tf.name)
            path = str(Path(dest_dir) / packed_name(j.name))
            os.rename(tf.name, path)
            return path

    def reset_jobs(self, job_ids):
        return self.queries.resetJobs(job_ids)

    # ------------------- end AbstractEditableQueue ---------------
