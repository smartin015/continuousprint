import uuid
import time
import json
from threading import Thread
from typing import Optional
from bisect import bisect_left
from ..storage.peer import PeerJobView, PeerQueueView, PeerSetView
from ..storage.database import JobView, SetView
from ..storage.rank import Rational, rational_intermediate
from peerprint.client import CompletionType
from pathlib import Path
from .base import AbstractEditableQueue, QueueData, Strategy, ValidationError
import dataclasses


class NetworkQueue(AbstractEditableQueue):
    def __init__(
        self,
        ns,
        peerprint,
        logger,
        strategy: Strategy,
        update_cb,
        profile,
        path_on_disk_fn,
    ):
        super().__init__()
        self._logger = logger
        self._profile = profile
        self.strategy = strategy
        self.ns = ns
        self._peerprint = peerprint
        self._printer_name = None
        self.job_id = None
        self.set_id = None
        self.server_id = None
        self.update_cb = update_cb
        self._fileshare = peerprint.get_plugin().fileshare
        self._path_on_disk = path_on_disk_fn

    @property
    def _client(self):
        # Put this in a function so client can be lazy initialized and we still get it
        return self._peerprint.get_plugin().client

    # ---------- Network queue methods ---------

    def connect(self):
        self._logger.debug("Waiting for p2p server...")
        while True:
            if self._client.is_ready() and self._client.ping():
                break
            time.sleep(1.0)

        conns = [c.network for c in self._client.get_connections()]
        if self.ns not in conns:
            raise Exception(
                f'Network queue "{self.ns}" init failure - no such connection on peerprint server, candidates {conns}'
            )

        self.server_id = self._client.get_id(self.ns)
        self._logger.debug(f"p2p server ready, ID is {self.server_id}")

        self._loop = True
        Thread(target=self._loop_stream, daemon=True).start()

    def __del__(self):
        self._loop = False

    def resolve(self, path, hash_):
        dirpath = self.get_gjob_dirpath(hash_)
        return str(Path(dirpath) / path)

    def is_ready(self) -> bool:
        return self._client.is_ready()

    def _loop_stream(self):
        while self._loop:
            self._logger.debug("starting event stream")
            evts = self._client.stream_events(self.ns)
            for e in evts:
                self._on_update(e)
            # Delay to prevent overwhelming server
            # TODO switch to random exponential backoff
            time.sleep(5.0)

    def _on_update(self, e):
        # self._logger.debug(f"network event: {e}")
        self.update_cb(self)

    def _set_completion(self, uuid, timestamp, typ):
        return self._client.set_completion(
            self.ns,
            uuid=uuid,
            completer=self.server_id,
            client=self._printer_name,
            timestamp=timestamp,
            type=int(typ),
            completer_state=json.dumps(
                dict(profile=self._profile, printer=self._printer_name)
            ).encode("utf8"),
        )

    def update_peer_state(self, name, status, profile):
        # Store info in memory to decorate completions later on
        self._printer_name = name
        self._profile = profile

        if self._client is not None:
            self._client.set_status(
                self.ns,
                active_unit=json.dumps(self._active_set()),
                name=name,
                status=str(status),
                profile=json.dumps(profile),
            )

    def _last_rank(self):
        greatest = (0, 1, 0.0)
        for r in self._client.get_records(self.ns):
            if greatest is None or r.record.rank.gen > greatest[2]:
                greatest = (r.record.rank.num, r.record.rank.den, r.record.rank.gen)
        return greatest

    def set_job(self, jid: str, manifest: dict):
        rank = dict(
            [
                (k, manifest.get(l))
                for k, l in (("num", "rn"), ("den", "rd"), ("gen", "rank"))
            ]
        )
        if None in rank.values():
            n = self._last_rank()
            rank = dict(num=n[0] + 1, den=n[1], gen=float((n[0] + 1) / n[1]))

        approver = manifest.get("peer_")
        if approver is None or approver == "":
            approver = self.server_id
        # self._logger.debug(f"set_record with approver {approver} (manifest approver {manifest.get("peer_")}, server-id {self.server_id} {type(self.server_id)})")

        return self._client.set_record(
            self.ns,
            manifest=json.dumps(manifest),
            # Preserve peer address of job if present in the manifest
            approver=approver,
            uuid=jid,
            created=getattr(manifest, "created", int(time.time())),
            tags=getattr(manifest, "tags", []),
            rank=rank,
        )

    def get_gjob_dirpath(self, hash_):
        # fetch unpacked job from fileshare (may be cached) and return the real path
        return self._fileshare.fetch(hash_, unpack=True)

    # -------- Wrappers around NetworkQueue to add/remove metadata ------

    def _get_jobs(self) -> list:
        if not self._client.is_ready():
            return []

        acquiredBy = dict()
        tombstones = set()
        for c in self._client.get_completions(self.ns):
            if c.completion.timestamp > 0 and c.completion.type == int(
                CompletionType.TOMBSTONE
            ):
                tombstones.add(c.completion.uuid)
            elif c.completion.timestamp == 0 and c.completion.type == int(
                CompletionType.ACQUIRE
            ):
                acquiredBy[c.completion.uuid] = c.completion.client

        # Filter to newest records not tombstoned
        records = {}
        for r in self._client.get_records(self.ns):
            if r.record.uuid in tombstones:
                continue
            cur = records.get(r.record.uuid)
            if cur is not None and cur.record.created > r.record.created:
                continue
            records[r.record.uuid] = r

        # Convert to dict object
        rs = []
        for r in records.values():
            rdata = json.loads(r.record.manifest)
            acquirer = acquiredBy.get(r.record.uuid)
            rdata["acquired"] = acquirer is not None
            if rdata["acquired"] and acquirer != self._printer_name:
                rdata["acquired_by"] = acquirer
            rdata["rn"] = r.record.rank.num
            rdata["rd"] = r.record.rank.den
            rdata["rank"] = r.record.rank.gen
            rs.append(rdata)
        rs.sort(key=lambda r: r["rank"])
        return rs

    def _get_job(self, jid) -> dict:
        if not self._client.is_ready() or jid is None:
            return None

        acquiredBy = None
        for c in self._client.get_completions(self.ns, uuid=jid):
            if c.completion.timestamp > 0 and c.completion.type == int(
                CompletionType.TOMBSTONE
            ):
                # Even if a job record exists, a tombstone completion may
                # hide it from view.
                # We persist the original record so its deletion can propagate.
                return None
            elif c.completion.timestamp == 0 and c.completion.type == int(
                CompletionType.ACQUIRE
            ):
                acquiredBy = c.completion.client

        best = None
        for r in self._client.get_records(self.ns, uuid=jid):
            # print("_get_job record check", r.record.uuid, r.record.created)
            if best is None or r.record.created > best.record.created:
                best = r

        if best is not None:
            data = json.loads(best.record.manifest)
            data["acquired"] = acquiredBy is not None
            if acquiredBy is not None and acquiredBy != self._printer_name:
                data["acquired_by"] = acquiredBy
            data["rn"] = best.record.rank.num
            data["rd"] = best.record.rank.den
            data["rank"] = best.record.rank.gen
            return data

    def _get_peers(self) -> list:
        if not self._client.is_ready():
            return []
        return list(self._client.get_peers(self.ns))

    # --------- begin AbstractQueue --------

    def get_job(self) -> Optional[JobView]:
        if self.job_id is not None:
            # Override to ensure the latest data is received
            return self.get_job_view(self.job_id)

    def get_set(self) -> Optional[SetView]:
        if self.job_id is not None and self.set_id is not None:
            # Linear search through sets isn't efficient, but it works.
            j = self.get_job_view(self.job_id)
            if j is not None:
                for s in j.sets:
                    if s.id == self.set_id:
                        return s

    def _peek(self):
        if not self.is_ready():
            return (None, None)
        for data in self._get_jobs():
            # skip if another peer is working on the job
            peer_completions = set(
                [
                    c.completion.completer
                    for c in self._client.get_completions(self.ns, data["id"])
                    if c.completion.completer != self.server_id
                    and c.completion.client != self._printer_name
                    and c.completion.type != int(CompletionType.RELEASE)
                ]
            )
            if len(peer_completions) > 0:
                continue

            job = PeerJobView()
            job.load_dict(data, PeerQueueView(self))
            s = job.next_set(self._profile)
            if s is not None:
                return (job, s)
        return (None, None)

    def acquire(self) -> bool:
        if not self.is_ready():
            return False
        (job, s) = self._peek()
        if job is None or s is None:
            # Spammy debug log
            # self._logger.debug("acquire() failed; no available job")
            return False

        self._set_completion(job.id, 0, CompletionType.ACQUIRE)
        self.job_id = job.id
        self.set_id = s.id
        return True

    def release(self) -> None:
        if self.job_id is not None:
            self._set_completion(self.job_id, 0, CompletionType.RELEASE)
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
            self.set_job(jid, j)

    def remove_jobs(self, job_ids) -> dict:
        n = 0
        for jid in job_ids:
            # No need to check for job existence; peers will just ignore
            # it if they don't have a matching record.
            self._set_completion(jid, int(time.time()), CompletionType.TOMBSTONE)
            n += 1
        return dict(jobs_deleted=n)

    # --------- end AbstractQueue ------

    # --------- AbstractEditableQueue implementation ------

    def get_job_view(self, job_id):
        j = self._get_job(job_id)
        if j is not None:
            v = PeerJobView()
            v.load_dict(j, PeerQueueView(self))
            return v

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

        if jid is None:
            jid = self._gen_uuid()
        manifest["id"] = jid

        # Propagate peer if importing from a PeerJobView
        # But don't fail with AttributeError if it's just a JobView
        manifest["peer_"] = getattr(j, "peer", None)
        self.set_job(jid, manifest)
        return jid

    def mv_job(self, job_id, after_id, before_id):
        # See `.storage.rank` for details on rational-based
        # ordering via Stern-Brocot tree
        # TODO memoize fetch somehow
        manifest = self._get_job(job_id)
        bj = self._get_job(before_id)
        aj = self._get_job(after_id)

        br = Rational(bj["rn"], bj["rd"]) if bj is not None else Rational(1, 0)
        ar = Rational(aj["rn"], aj["rd"]) if aj is not None else Rational(0, 1)
        # Ordering is <after>, <job>, <before>
        # So "after" comes before "before". Yes, it's weird.
        newRank = rational_intermediate(ar, br)
        # self._logger.debug(f"rational_intermediate({ar}, {br}) => {newRank}")

        manifest["rn"] = newRank.n
        manifest["rd"] = newRank.d
        manifest["rank"] = float(newRank.n) / float(newRank.d)
        self.set_job(job_id, manifest)

    def _path_exists(self, fullpath):
        return Path(fullpath).exists()

    def _validate_job(self, j: JobView) -> str:
        peer_profiles = set()
        for peer in self._get_peers():
            for printer in peer.get("clients", []):
                try:
                    p = json.loads(printer.get("profile"))
                    peer_profiles.add(p.get("name", "UNKNOWN"))
                except json.decoder.JSONDecodeError:
                    self._logger.warning(
                        "Failed to decode profile for peer", peer.get("name")
                    )
        peer_profiles.add(
            self._profile.get("name", "UNKNOWN")
        )  # We're always in the queue
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
            result = str(uuid.uuid4())
            if self._get_job(result) is None:
                return result
        raise Exception("UUID generation failed - too many ID collisions")

    def edit_job(self, job_id, data) -> str:
        # For lan queues, "editing" a job is basically resubmission of the whole thing.
        # This is because the backing .gjob format is a single file containing the full manifest.

        j = self.get_job_view(job_id)
        for (k, v) in data.items():
            if k in ("id", "peer_", "queue"):
                continue
            if k == "sets":
                # Set data must be translated into views
                j.sets = []
                for i, s in enumerate(v):
                    sv = PeerSetView()
                    sv.load_dict(s, j, i)
                    j.sets.append(sv)

            else:
                setattr(j, k, v)

        # We must resolve the set paths so we have them locally, as editing can
        # also occur on servers other than the one that submitted the job.
        for s in j.sets:
            s.path = s.resolve()

        # We are also now the source of this job
        j.peer = self.server_id

        # Exchange the old job for the new job (reuse job ID)
        jid = self.import_job_from_view(j, j.id)
        return self._get_job(jid)
