from typing import Optional
from enum import Enum, auto
import dataclasses
from ..storage.database import JobView, SetView
from abc import ABC, abstractmethod


class Strategy(Enum):
    IN_ORDER = auto()  # Jobs and sets printed in lexRank order
    LEAST_MANUAL = auto()  # Choose the job which produces the least manual changes


@dataclasses.dataclass
class QueueData:
    name: str
    strategy: str
    jobs: list
    active_set: int
    addr: Optional[str] = None
    peers: list = dataclasses.field(default_factory=list)


class AbstractQueue(ABC):
    """Base class for all queue types.

    Queues are composed of Jobs, which themselves are composed of Sets, as
    defined in storage/database.py.

    Additionally, a queue has "runs" which are individual attempts at printing
    a gcode file.
    """

    def __init__(self):
        self.job = None
        self.set = None

    def get_job(self) -> Optional[JobView]:
        return self.job

    def get_set(self) -> Optional[SetView]:
        return self.set

    @abstractmethod
    def acquire(self) -> bool:
        pass

    @abstractmethod
    def release(self) -> None:
        pass

    @abstractmethod
    def decrement(
        self,
    ) -> bool:  # Returns true if the job has more work, false if job complete+released
        pass

    @abstractmethod
    def reset_jobs(self, job_ids) -> dict:
        pass

    @abstractmethod
    def export_job(self, job_id):
        pass

    @abstractmethod
    def as_dict(self) -> dict:
        pass

class AbstractJobQueue(AbstractQueue):
    """LAN queues (potentially others in the future) act on whole jobs and do not allow
    edits to inner data"""

    @abstractmethod
    def submit_job(self, j: JobView) -> bool:
        pass
    @abstractmethod
    def remove_job(self, job_ids) -> dict:
        pass


class AbstractEditableQueue(AbstractQueue):
    """Some queues (e.g. local to a single printer) are directly editable."""
    @abstractmethod
    def add_job(self) -> JobView:
        pass
    @abstractmethod
    def add_set(self, job_id, data) -> SetView:
        pass
    @abstractmethod
    def mv_set(self, set_id, after_id, dest_job) -> SetView:
        pass
    @abstractmethod
    def mv_job(self, job_id, after_id):
        pass
    @abstractmethod
    def edit_job(self, job_id, data):
        pass
    @abstractmethod
    def rm_multi(self, job_ids, set_ids) -> dict:
        pass
    @abstractmethod
    def import_job(self, gjob_path, out_dir) -> dict:
        pass

