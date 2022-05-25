import octoprint.plugin
from octoprint.access.permissions import Permissions, ADMIN_GROUP
from octoprint.server.util.flask import restricted_access
import flask
from .storage import queries
from .driver import Action as DA
from abc import ABC, abstractmethod

def cpq_permission(suffix):
    def cpq_permission_decorator(func):
        def cpq_permission_wrapper(*args, **kwargs):
            if not getattr(Permissions, f'PLUGIN_CONTINUOUSPRINT_{suffix}').can():
                return flask.make_response(f"Insufficient Rights ({suffix})", 403)
            return func(*args, **kwargs)
        return cpq_permission_wrapper
    return cpq_permission_decorator


PERMISSIONS = [
    dict(
        key="STARTQUEUE",
        name="Start Queue",
        description="Allows for starting and stopping queue",
        roles=["admin", "continuousprint-start"],
        dangerous=True,
        default_groups=[ADMIN_GROUP],
    ),
    dict(
        key="ADDQUEUE",
        name="Add to Queue",
        description="Allows for adding prints to the queue",
        roles=["admin", "continuousprint-add"],
        dangerous=True,
        default_groups=[ADMIN_GROUP],
    ),
    dict(
        key="RMQUEUE",
        name="Remove Print from Queue ",
        description="Allows for removing prints from the queue",
        roles=["admin", "continuousprint-remove"],
        dangerous=True,
        default_groups=[ADMIN_GROUP],
    ),
    dict(
        key="CHQUEUE",
        name="Move items in Queue ",
        description="Allows for moving items in the queue",
        roles=["admin", "continuousprint-move"],
        dangerous=True,
        default_groups=[ADMIN_GROUP],
    ),
]

class ContinuousPrintAPI(ABC, octoprint.plugin.BlueprintPlugin):

    @abstractmethod
    def _update(self, a: DA):
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

    # Public API method returning the full state of the plugin in JSON format.
    # See `_state_json()` for return values.
    @octoprint.plugin.BlueprintPlugin.route("/state", methods=["GET"])
    @restricted_access
    def get_state(self):
        return self._state_json()

    # Public method - enables/disables management and returns the current state
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/set_active", methods=["POST"])
    @restricted_access
    @cpq_permission('STARTSTOP')
    def set_active(self):
        self._update(
            DA.ACTIVATE if flask.request.form["active"] == "true" else DA.DEACTIVATE
        )
        return self._state_json()

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/set/add", methods=["POST"])
    @restricted_access
    @cpq_permission('ADDSET')
    def add_set(self):
        return json.dumps(self._get_queue(DEFAULT_QUEUE).add_set(
            flask.request.form["job"], flask.request.form
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/add", methods=["POST"])
    @restricted_access
    @cpq_permission('ADDJOB')
    def add_job(self):
        return json.dumps(self._get_queue(DEFAULT_QUEUE).add_job().as_dict())

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/set/mv", methods=["POST"])
    @restricted_access
    @cpq_permission('EDITSET')
    def mv_set(self):
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
    @cpq_permission('EDITJOB')
    def mv_job(self):
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
    @cpq_permission('ADDJOB')
    def submit_job(self):
        j = queries.getJob(int(flask.request.form["id"]))
        # Submit to the queue and remove from its origin
        self._get_queue(flask.request.form["queue"]).submit_job(j, filepaths)
        self._get_queue(DEFAULT_QUEUE).remove(job_ids=[j.id])
        return self._state_json()

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/edit", methods=["POST"])
    @restricted_access
    @cpq_permission('EDITJOB')
    def edit_job(self):
        data = json.loads(flask.request.form.get("json"))
        return json.dumps(self._get_queue(DEFAULT_QUEUE).edit_job(data["id"], data))

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/import", methods=["POST"])
    @restricted_access
    @cpq_permission('ADDJOB')
    def import_job(self):
        return json.dumps(self._get_queue(flask.request.form["queue"])
                .import_job(flask.request.form["path"]).as_dict())

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/export", methods=["POST"])
    @restricted_access
    @cpq_permission('EXPORTJOB')
    def export_job(self):
        job_ids = [int(jid) for jid in flask.request.form.getlist("job_ids[]")]
        results = []
        root_dir = self._file_manager.path_on_disk(FileDestinations.LOCAL, "/")
        for jid in job_ids:
            self._logger.debug(f"Exporting job with ID {jid}")
            path = self._get_queue(DEFAULT_QUEUE).export_job(jid, root_dir)
            results.append(self._file_manager.path_in_storage(path))
            self._logger.debug(f"Export job {jid} to {path}")
        return json.dumps(results)

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/multi/rm", methods=["POST"])
    @restricted_access
    @cpq_permission('EDITJOB')
    def rm_multi(self):
        raise Exception("TODO if job_ids contains hashes, inspect ns param, get queue, and remove from there")
        return json.dumps(
            queries.remove(
                job_ids=flask.request.form.getlist("job_ids[]"),
                set_ids=flask.request.form.getlist("set_ids[]"),
                queue_ids=flask.request.form.getlist("queue_ids[]"),
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/reset", methods=["POST"])
    @restricted_access
    @cpq_permission('EDITJOB')
    def reset_multi(self):
        return json.dumps(self._get_queue(DEFAULT_QUEUE).reset_jobs(flask.request.form.getlist("job_ids[]")))

    def history_json(self):
        h = queries.getHistory()

        if self.q.run is not None:
            for row in h:
                if row["run_id"] == self.q.run:
                    row["active"] = True
                    break
        return json.dumps(h)

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/history", methods=["GET"])
    @restricted_access
    @cpq_permission('GETHISTORY')
    def get_history(self):
        return self.history_json()

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/clearHistory", methods=["POST"])
    @restricted_access
    @cpq_permission('CLEARHISTORY')
    def clear_history(self):
        queries.clearHistory()
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues", methods=["GET"])
    @restricted_access
    @cpq_permission('GETQUEUE')
    def get_queues(self):
        return json.dumps([q.as_dict() for q in queries.getQueues()])

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues/commit", methods=["POST"])
    @restricted_access
    @cpq_permission('EDITQUEUE')
    def commit_queues(self):
        (absent_names, added) = queries.assignQueues(
            json.loads(flask.request.form.get("queues"))
        )
        self._commit_queues(added, absent_names)
        return json.dumps("OK")
