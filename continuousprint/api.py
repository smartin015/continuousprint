import octoprint.plugin
from enum import Enum
from octoprint.access.permissions import Permissions, ADMIN_GROUP
from octoprint.server.util.flask import restricted_access
from .queues.base import ValidationError
from .automation import getInterpreter, genEventScript
import flask
import json
from .storage import queries
from .storage.database import DEFAULT_QUEUE, ARCHIVE_QUEUE
from .data import CustomEvents, Keys
from .driver import Action as DA
from abc import ABC, abstractmethod


class Permission(Enum):
    GETSTATE = (
        "Get state",
        "Allows for fetching queue and management state of Continuous Print",
        False,
    )
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
    RESETHISTORY = (
        "Reset history",
        "Allows for deleting all continuous print history data",
        True,
    )
    GETQUEUES = (
        "Get queues",
        "Allows for fetching metadata on all print queues",
        False,
    )
    EDITQUEUES = (
        "Edit queues",
        "Allows for adding/removing queues and rearranging them",
        True,
    )
    GETAUTOMATION = (
        "Get automation scripts and events",
        "Allows for fetching metadata on all scripts and the events they're configured for",
        False,
    )
    EDITAUTOMATION = (
        "Edit automation scripts and events",
        "Allows for adding/removing gcode scripts and registering them to execute when events happen",
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


def cpq_permission(perm: Permission):
    def cpq_permission_decorator(func):
        def cpq_permission_wrapper(*args, **kwargs):
            if not getattr(Permissions, f"PLUGIN_CONTINUOUSPRINT_{perm.name}").can():
                return flask.make_response(f"Insufficient Rights ({perm.name})", 403)
            return func(*args, **kwargs)

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
    def _path_on_disk(self, path, sd):
        pass

    @abstractmethod
    def _path_in_storage(self, path):
        pass

    @abstractmethod
    def _msg(self, data):
        pass

    @abstractmethod
    def _preprocess_set(self, data):
        pass  # Used to auto-fill underspecified sets, e.g. add profile based on gcode analysis

    @abstractmethod
    def _set_external_symbols(self, data):
        pass

    def popup(self, msg, type="popup"):
        return self._msg(dict(type=type, msg=msg))

    def _sync(self, attr, data):
        # self._logger.debug(f"Refreshing UI {attr}")
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
    @cpq_permission(Permission.GETSTATE)
    def get_state(self):
        return self._state_json()

    # Public method - enables/disables management and returns the current state
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/set_active", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.STARTSTOP)
    def set_active(self):
        active = flask.request.form["active"]
        if type(active) == str:
            active = active.lower().strip() == "true"

        self._update(DA.ACTIVATE if active else DA.DEACTIVATE)
        return self._state_json()

    # Public method - adds a new set to an existing job, or creates a new job and adds the set there.
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/set/add", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.ADDSET)
    def add_set(self):
        if flask.request.form.get("json"):
            data = self._preprocess_set(json.loads(flask.request.form.get("json")))
        else:
            # For backwards compatibility - this originally wasn't passed as a single json field
            data = self._preprocess_set(dict(**flask.request.form))
        jid = data.get("job")
        if jid is None:
            jid = ""
        return json.dumps(self._get_queue(DEFAULT_QUEUE).add_set(jid, data))

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/add", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.ADDJOB)
    def add_job(self):
        data = json.loads(flask.request.form.get("json"))
        return json.dumps(
            self._get_queue(DEFAULT_QUEUE).add_job(data.get("name")).as_dict()
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/mv", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def mv_job(self):
        src_id = flask.request.form["id"]
        after_id = flask.request.form["after_id"]
        before_id = flask.request.form.get("before_id")
        if after_id == "":  # Treat empty string as 'none' i.e. front of queue
            after_id = None
        if before_id == "":  # Treat empty as 'none' i.e. end of queue
            before_id = None
        sq = self._get_queue(flask.request.form["src_queue"])
        dq = self._get_queue(flask.request.form.get("dest_queue"))

        # Transfer into dest queue first
        if dq != sq:
            try:
                new_id = dq.import_job_from_view(sq.get_job_view(src_id))
            except ValidationError as e:
                return json.dumps(dict(error=str(e)))
            sq.remove_jobs([src_id])
            src_id = new_id

        # Finally, move the job
        dq.mv_job(src_id, after_id, before_id)
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/edit", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def edit_job(self):
        data = json.loads(flask.request.form.get("json"))
        q = self._get_queue(data["queue"])
        return json.dumps(q.edit_job(data["id"], data))

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/import", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.ADDJOB)
    def import_job(self):
        return json.dumps(
            self._get_queue(flask.request.form["queue"])
            .import_job(flask.request.form["path"])
            .as_dict()
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/export", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EXPORTJOB)
    def export_job(self):
        job_ids = [int(jid) for jid in flask.request.form.getlist("job_ids[]")]
        results = {"paths": [], "errors": []}
        root_dir = self._path_on_disk("/", sd=False)
        for jid in job_ids:
            self._logger.debug(f"Exporting job with ID {jid}")
            try:
                path = self._get_queue(DEFAULT_QUEUE).export_job(jid, root_dir)
            except ValueError as e:
                e = str(e)
                self._logger.error(e)
                results["errors"].append(e)
                continue
            results["paths"].append(self._path_in_storage(path))
            self._logger.debug(f"Exported job {jid} to {path}")
        return json.dumps(results)

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/rm", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.RMJOB)
    def rm_job(self):
        return json.dumps(
            self._get_queue(flask.request.form["queue"]).remove_jobs(
                flask.request.form.getlist("job_ids[]")
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/reset", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITJOB)
    def reset_multi(self):
        return json.dumps(
            self._get_queue(flask.request.form["queue"]).reset_jobs(
                flask.request.form.getlist("job_ids[]")
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/history/get", methods=["GET"])
    @restricted_access
    @cpq_permission(Permission.GETHISTORY)
    def get_history(self):
        return self._history_json()

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/history/reset", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.RESETHISTORY)
    def reset_history(self):
        queries.resetHistory()
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues/get", methods=["GET"])
    @restricted_access
    @cpq_permission(Permission.GETQUEUES)
    def get_queues(self):
        qs = dict()
        if self._get_key(Keys.NETWORK_QUEUES, False):
            for n in self._peerprint.get_plugin().client.get_connections():
                qs[n.network] = dict(
                    name=n.network, addr=n.addr, strategy="LINEAR", enabled=False
                )

        for q in queries.getQueues():
            if q.name == DEFAULT_QUEUE:
                qs[q.name] = q.as_dict()
                qs[q.name]["enabled"] = True
                qs[q.name]["rank"] = q.rank
            elif q.name in qs:
                qs[q.name]["enabled"] = True

        qs = list(qs.values())
        qs.sort(key=lambda q: q.get("rank", 99999999))
        return json.dumps(qs)

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues/edit", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITQUEUES)
    def edit_queues(self):
        queues = json.loads(flask.request.form.get("json"))
        queues = [q for q in queues if q["enabled"]]  # strip disabled queues
        (absent_names, added) = queries.assignQueues(queues)
        self._commit_queues(added, absent_names)
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/automation/edit", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITAUTOMATION)
    def edit_automation(self):
        data = json.loads(flask.request.form.get("json"))
        queries.assignAutomation(data["scripts"], data["preprocessors"], data["events"])
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/automation/get", methods=["GET"])
    @restricted_access
    @cpq_permission(Permission.GETAUTOMATION)
    def get_automation(self):
        return json.dumps(queries.getAutomation())

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/automation/external", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITAUTOMATION)
    def set_automation_external_symbols(self):
        self._set_external_symbols(flask.request.get_json())
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/automation/simulate", methods=["POST"])
    @restricted_access
    @cpq_permission(Permission.EDITAUTOMATION)
    def simulate_automation(self):
        symtable = json.loads(flask.request.form.get("symtable"))
        automation = json.loads(flask.request.form.get("automation"))
        interp, out, err = getInterpreter(symtable)
        symtable = interp.symtable.copy()  # Pick up defaults
        result = dict(
            gcode=genEventScript(automation, interp),
            symtable_diff={},
        )

        err.seek(0)
        result["stderr"] = err.read()
        out.seek(0)
        result["stdout"] = out.read()
        for k, v in interp.symtable.items():
            if k not in symtable or symtable[k] != v:
                result["symtable_diff"][k] = repr(v)
        self._logger.debug(f"Simulator result: {result}")
        return json.dumps(result)
