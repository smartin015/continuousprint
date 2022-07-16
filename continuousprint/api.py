import octoprint.plugin
from enum import Enum
from octoprint.access.permissions import Permissions, ADMIN_GROUP
from octoprint.server.util.flask import restricted_access
import flask
import json
from collections import namedtuple
from .storage import queries
from .storage.database import DEFAULT_QUEUE, Queue, Set, Job
from .driver import Action as DA
from abc import ABC, abstractmethod


Creds = namedtuple("Credentials", ["user", "groups", "admin"])


def get_creds():
    # https://flask-login.readthedocs.io/en/latest/#your-user-class
    # https://github.com/OctoPrint/OctoPrint/blob/f430257d7072a83692fc2392c683ed8c97ae47b6/src/octoprint/server/api/access.py#L171
    from flask_login import current_user
    from octoprint.server import userManager

    usr = userManager.find_user(current_user.get_name())
    return Creds(
        usr.get_id(),
        [g.get_name() for g in usr.groups],
        Permissions.PLUGIN_CONTINUOUSPRINT_QUEUE_ADMIN.can(),
    )


class Permission(Enum):
    STARTSTOP = (
        "Start and Stop Queue",
        "Allows for starting and stopping the queue",
        True,
    )
    ADDSET = ("Add set to queue", "Allows for adding print sets to the queue", True)
    ADDJOB = (
        "Add job to queue",
        "Allows for adding print jobs (groups of sets) to the queue",
        True,
    )
    EDITJOB = ("Edit job", "Allows for editing / reordering queue jobs", True)
    EXPORTJOB = ("Export job", "Allows for saving a print job as a .gjob file", False)
    RMJOB = ("Remove job", "Allows for removing jobs from the queue", False)
    GETHISTORY = (
        "Get history",
        "Allows for fetching history of print runs by Continuous Print",
        False,
    )
    CLEARHISTORY = (
        "Clear history",
        "Allows for deleting all continuous print history data",
        True,
    )
    GETQUEUES = ("Get queue", "Allows for fetching metadata on all print queues", False)
    EDITQUEUES = (
        "Edit queues",
        "Allows for adding/removing queues and rearranging them",
        True,
    )
    QUEUE_ADMIN = (
        "Queue administrator",
        "Skip user/group permissions checks when performing operations",
        True,
    )

    def __init__(self, longname, desc, dangerous):
        self.longname = longname
        self.desc = desc
        self.dangerous = dangerous

    def as_dict(self):
        return dict(
            key=self.name,
            name=self.longname,
            description=self.desc,
            roles=["admin", f"continuousprint-{self.name.lower()}"],
            dangerous=self.dangerous,
            default_groups=[ADMIN_GROUP],
        )


def cpq_permission(perm: Permission, field=None):
    def cpq_permission_decorator(func):
        def cpq_permission_wrapper(*args, **kwargs):
            if not getattr(Permissions, f"PLUGIN_CONTINUOUSPRINT_{perm.name}").can():
                return flask.make_response(f"Insufficient Rights ({perm.name})", 403)
            return func(*args, **kwargs, creds=get_creds())

        # the BlueprintPlugin decorator used below relies on the original function name
        # to map the function to an HTTP handler
        # See https://github.com/OctoPrint/OctoPrint/blob/f430257d7072a83692fc2392c683ed8c97ae47b6/src/octoprint/plugin/types.py#L1378
        cpq_permission_wrapper.__name__ = func.__name__
        return cpq_permission_wrapper

    return cpq_permission_decorator


class ContinuousPrintAPI(ABC, octoprint.plugin.BlueprintPlugin):
    @abstractmethod
    def _update(self, a: DA):
        pass

    @abstractmethod
    def _history_json(self) -> str:
        pass

    @abstractmethod
    def _state_json(self) -> str:
        pass

    @abstractmethod
    def _commit_queues(self, added, removed):
        pass

    @abstractmethod
    def _get_queue(self, name):
        pass

    @abstractmethod
    def _path_on_disk(self, path):
        pass

    @abstractmethod
    def _path_in_storage(self, path):
        pass

    @abstractmethod
    def _msg(self, data):
        pass

    @abstractmethod
    def _preprocess_set(self, data):
        pass  # Can auto-fill things, e.g. profile based on gcode analysis

    def popup(self, msg, type="popup"):
        return self._msg(dict(type=type, msg=msg))

    def _sync(self, attr, data):
        self._logger.debug(f"Refreshing UI {attr}")
        msg = dict(type=f"set{attr}")
        msg[attr] = data
        self._msg(msg)

    def _sync_state(self):
        return self._sync("state", self._state_json())

    def _sync_history(self):
        return self._sync("history", self._history_json())

    # Public method - returns the full state of the plugin in JSON format.
    # See `_state_json()` for return values.
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/state/get", methods=["GET"])
    @restricted_access
    def get_state(self):
        return self._state_json()

    # Public method - enables/disables management and returns the current state
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/set_active", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.STARTSTOP)
    def set_active(self, creds):
        self._update(
            DA.ACTIVATE if flask.request.form["active"] == "true" else DA.DEACTIVATE
        )
        return self._state_json()

    # Public method - adds a new set to an existing job, or creates a new job and adds the set there.
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/set/add", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.ADDSET)
    def add_set(self, creds):
        data = self._preprocess_set(dict(**flask.request.form))
        return json.dumps(
            self._get_queue(DEFAULT_QUEUE).add_set(data.get("job", ""), data, creds)
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/add", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.ADDJOB)
    def add_job(self, creds):
        return json.dumps(
            self._get_queue(DEFAULT_QUEUE)
            .add_job(flask.request.form.get("name"))
            .as_dict()
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/set/mv", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def mv_set(self, creds):
        self._get_queue(DEFAULT_QUEUE).mv_set(
            int(flask.request.form["id"]),
            int(
                flask.request.form["after_id"]
            ),  # Move to after this set (-1 for beginning of job)
            int(
                flask.request.form["dest_job"]
            ),  # Move to this job (null for new job at end)
        )
        return json.dumps("ok")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/mv", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def mv_job(self, creds):
        self._get_queue(DEFAULT_QUEUE).mv_job(
            int(flask.request.form["id"]),
            int(
                flask.request.form["after_id"]
            ),  # Move to after this job (-1 for beginning of queue)
        )
        return json.dumps("ok")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/submit", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.ADDJOB)
    def submit_job(self, creds):
        j = queries.getJob(int(flask.request.form["id"]))
        # Submit to the queue and remove from its origin
        err = self._get_queue(flask.request.form["queue"]).submit_job(j)
        if err is None:
            self._logger.debug(
                self._get_queue(DEFAULT_QUEUE).remove_jobs(job_ids=[j.id])
            )
            return self._state_json()
        else:
            return json.dumps(dict(error=str(err)))

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/edit", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def edit_job(self, creds):
        data = json.loads(flask.request.form.get("json"))
        return json.dumps(
            self._get_queue(DEFAULT_QUEUE).edit_job(data["id"], data, creds)
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/import", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.ADDJOB)
    def import_job(self, creds):
        return json.dumps(
            self._get_queue(flask.request.form["queue"])
            .import_job(flask.request.form["path"])
            .as_dict()
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/export", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EXPORTJOB)
    def export_job(self, creds):
        job_ids = [int(jid) for jid in flask.request.form.getlist("job_ids[]")]
        results = []
        root_dir = self._path_on_disk("/")
        for jid in job_ids:
            self._logger.debug(f"Exporting job with ID {jid}")
            path = self._get_queue(DEFAULT_QUEUE).export_job(jid, root_dir)
            results.append(self._path_in_storage(path))
            self._logger.debug(f"Export job {jid} to {path}")
        return json.dumps(results)

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/rm", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def rm_job(self, creds):
        return json.dumps(
            self._get_queue(flask.request.form["queue"]).remove_jobs(
                flask.request.form.getlist("job_ids[]")
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/set/rm", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def rm_set(self, creds):
        return json.dumps(
            self._get_queue(DEFAULT_QUEUE).rm_multi(
                set_ids=flask.request.form.getlist("set_ids[]")
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/reset", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def reset_multi(self, creds):
        return json.dumps(
            self._get_queue(flask.request.form["queue"]).reset_jobs(
                flask.request.form.getlist("job_ids[]")
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/history/get", methods=["GET"])
    @restricted_access
    @cpq_permission(Permission.GETHISTORY)
    def get_history(self, creds):
        return self._history_json()

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/history/reset", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.CLEARHISTORY)
    def reset_history(self, creds):
        queries.resetHistory()
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues/get", methods=["GET"])
    @restricted_access
    @cpq_permission(Permission.GETQUEUES)
    def get_queues(self, creds):
        return json.dumps([q.as_dict() for q in queries.getQueues()])

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues/edit", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITQUEUES)
    def edit_queues(self, creds):
        queues = json.loads(flask.request.form.get("json"))
        (absent_names, added) = queries.assignQueues(queues)
        self._commit_queues(added, absent_names)
        return json.dumps("OK")
