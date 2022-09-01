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
    def as_dict(self) -> dict:
        pass

    @abstractmethod
    def remove_jobs(self, job_ids) -> dict:
        pass

    @abstractmethod
    def reset_jobs(self, job_ids) -> dict:
        pass


class AbstractEditableQueue(AbstractQueue):
    """Use for queues that are directly editable."""

    @abstractmethod
    def mv_job(self, job_id, after_id):
        pass

    @abstractmethod
    def edit_job(self, job_id, data):
        pass

    @abstractmethod
    def get_job_view(self, job_id):
        pass

    @abstractmethod
    def import_job_from_view(self, job_view):
        """Imports a JobView into storage. Returns ID of the imported job"""
        pass


class AbstractFactoryQueue(AbstractEditableQueue):
    """Use for queues where you can construct new jobs/sets"""

    @abstractmethod
    def add_job(self, name="") -> JobView:
        pass

    @abstractmethod
    def add_set(self, job_id, data) -> SetView:
        pass

    @abstractmethod
    def import_job(self, gjob_path, out_dir) -> dict:
        pass

    @abstractmethod
    def export_job(self, job_id):
        pass
