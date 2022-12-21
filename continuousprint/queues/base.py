from typing import Optional
from enum import Enum, auto
import dataclasses
from ..storage.database import JobView, SetView
from abc import ABC, abstractmethod


class ValidationError(Exception):
    pass


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
    def resolve(self, path, peer, hash_) -> Optional[str]:
        raise NotImplementedError()

    @abstractmethod
    def acquire(self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def release(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def decrement(
        self,
    ) -> bool:  # Returns true if the job has more work, false if job complete+released
        raise NotImplementedError()

    @abstractmethod
    def as_dict(self) -> dict:
        raise NotImplementedError()

    @abstractmethod
    def remove_jobs(self, job_ids) -> dict:
        raise NotImplementedError()

    @abstractmethod
    def reset_jobs(self, job_ids) -> dict:
        raise NotImplementedError()


class AbstractEditableQueue(AbstractQueue):
    """Use for queues that are directly editable."""

    @abstractmethod
    def mv_job(self, job_id, after_id):
        raise NotImplementedError()

    @abstractmethod
    def edit_job(self, job_id, data):
        raise NotImplementedError()

    @abstractmethod
    def get_job_view(self, job_id):
        raise NotImplementedError()

    @abstractmethod
    def import_job_from_view(self, job_view):
        """Imports a JobView into storage. Returns ID of the imported job"""
        raise NotImplementedError()


class AbstractFactoryQueue(AbstractEditableQueue):
    """Use for queues where you can construct new jobs/sets"""

    @abstractmethod
    def add_job(self, name="") -> JobView:
        raise NotImplementedError()

    @abstractmethod
    def add_set(self, job_id, data) -> SetView:
        raise NotImplementedError()

    @abstractmethod
    def import_job(self, gjob_path, out_dir) -> dict:
        raise NotImplementedError()

    @abstractmethod
    def export_job(self, job_id):
        raise NotImplementedError()
