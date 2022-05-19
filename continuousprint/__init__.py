# coding=utf-8
from __future__ import absolute_import

import flask
import json
import yaml
import os
import time
import traceback
import tempfile
from pathlib import Path
from io import BytesIO

import octoprint.plugin
import octoprint.util
from octoprint.server.util.flask import restricted_access
from octoprint.events import Events
from octoprint.access.permissions import Permissions, ADMIN_GROUP
import octoprint.filemanager
from octoprint.filemanager.util import StreamWrapper, DiskFileWrapper
from octoprint.filemanager.destinations import FileDestinations
from octoprint.util import RepeatedTimer
from octoprint.printer import InvalidFileLocation, InvalidFileType

from peerprint.filesharing import pack_job, unpack_job, packed_name
from .driver import Driver, Action as DA, Printer as DP
from .queues import MultiQueue, LocalQueue, LANQueue, Strategy
from .storage.database import (
    migrateFromSettings,
    init as init_db,
    DEFAULT_QUEUE,
    ARCHIVE_QUEUE,
)
from .storage import queries

QUEUE_KEY = "cp_queue"
PRINTER_PROFILE_KEY = "cp_printer_profile"
CLEARING_SCRIPT_KEY = "cp_bed_clearing_script"
FINISHED_SCRIPT_KEY = "cp_queue_finished_script"
TEMP_FILES = dict(
    [(k, f"{k}.gcode") for k in [FINISHED_SCRIPT_KEY, CLEARING_SCRIPT_KEY]]
)
RESTART_MAX_RETRIES_KEY = "cp_restart_on_pause_max_restarts"
RESTART_ON_PAUSE_KEY = "cp_restart_on_pause_enabled"
RESTART_MAX_TIME_KEY = "cp_restart_on_pause_max_seconds"
BED_COOLDOWN_ENABLED_KEY = "bed_cooldown_enabled"
BED_COOLDOWN_SCRIPT_KEY = "cp_bed_cooldown_script"
BED_COOLDOWN_THRESHOLD_KEY = "bed_cooldown_threshold"
BED_COOLDOWN_TIMEOUT_KEY = "bed_cooldown_timeout"
MATERIAL_SELECTION_KEY = "cp_material_selection_enabled"


class ContinuousprintPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.BlueprintPlugin,
    octoprint.plugin.EventHandlerPlugin,
):
    def _msg(self, msg="", type="popup"):
        self._plugin_manager.send_plugin_message(
            self._identifier, dict(type=type, msg=msg)
        )

    def _refresh_ui_state(self):
        # See continuousprint_viewmodel.js onDataUpdaterPluginMessage
        self._logger.info("Refreshing UI state")
        self._plugin_manager.send_plugin_message(
            self._identifier, dict(type="setstate", state=self.state_json())
        )

    def _refresh_ui_history(self):
        self._plugin_manager.send_plugin_message(
            self._identifier, dict(type="sethistory", history=self.history_json())
        )

    def _on_queue_update(self, q):
        self._logger.info("Update from queue:" + q.ns)
        self._refresh_ui_state()

    def _update_driver_settings(self):
        self.d.set_retry_on_pause(
            self._settings.get([RESTART_ON_PAUSE_KEY]),
            self._settings.get([RESTART_MAX_RETRIES_KEY]),
            self._settings.get([RESTART_MAX_TIME_KEY]),
        )

    # part of SettingsPlugin
    def get_settings_defaults(self):
        base = os.path.dirname(__file__)
        with open(os.path.join(base, "data/printer_profiles.yaml"), "r") as f:
            self._printer_profiles = yaml.safe_load(f.read())["PrinterProfile"]
        with open(os.path.join(base, "data/gcode_scripts.yaml"), "r") as f:
            self._gcode_scripts = yaml.safe_load(f.read())["GScript"]

        d = {}
        d[QUEUE_KEY] = None
        d[CLEARING_SCRIPT_KEY] = ""
        d[FINISHED_SCRIPT_KEY] = ""

        for s in self._gcode_scripts:
            name = s["name"]
            gcode = s["gcode"]
            if name == "Pause":
                d[CLEARING_SCRIPT_KEY] = gcode
            elif name == "Generic Off":
                d[FINISHED_SCRIPT_KEY] = gcode
        d[RESTART_MAX_RETRIES_KEY] = 3
        d[RESTART_ON_PAUSE_KEY] = False
        d[RESTART_MAX_TIME_KEY] = 60 * 60
        d[BED_COOLDOWN_ENABLED_KEY] = False
        d[BED_COOLDOWN_SCRIPT_KEY] = "; Put script to run before bed cools here\n"
        d[BED_COOLDOWN_THRESHOLD_KEY] = 30
        d[BED_COOLDOWN_TIMEOUT_KEY] = 60
        d[MATERIAL_SELECTION_KEY] = False
        d[PRINTER_PROFILE_KEY] = "Generic"
        return d

    def _active(self):
        return self.d.state != self.d._state_inactive if hasattr(self, "d") else False

    def _rm_temp_files(self):
        # Clean up any file references from prior runs
        for path in TEMP_FILES.values():
            if self._file_manager.file_exists(FileDestinations.LOCAL, path):
                self._file_manager.remove_file(FileDestinations.LOCAL, path)

    # part of StartupPlugin
    def on_after_startup(self):
        # Turn on "restart on pause" when TSD plugin is detected (must be version 1.8.11 or higher for custom event hook)
        if (
            getattr(
                octoprint.events.Events, "PLUGIN_THESPAGHETTIDETECTIVE_COMMAND", None
            )
            is not None
        ):
            self._logger.info(
                "Has TSD plugin with custom events integration - enabling failure automation"
            )
            self._settings.set([RESTART_ON_PAUSE_KEY], True)
        else:
            self._settings.set([RESTART_ON_PAUSE_KEY], False)

        # SpoolManager plugin isn't required, but does enable material-based printing if it exists
        # Code based loosely on https://github.com/OllisGit/OctoPrint-PrintJobHistory/ (see _getPluginInformation)
        smplugin = self._plugin_manager.plugins.get("SpoolManager")
        if smplugin is not None and smplugin.enabled:
            self._spool_manager = smplugin.implementation
            self._logger.info("SpoolManager found - enabling material selection")
            self._settings.set([MATERIAL_SELECTION_KEY], True)
        else:
            self._spool_manager = None
            self._settings.set([MATERIAL_SELECTION_KEY], False)

        self._settings.save()

        self.plugin_data_dir = Path(self.get_plugin_data_folder())
        init_db(
            db_path=self.plugin_data_dir / "queue.sqlite3",
            logger=self._logger,
        )

        # Migrate from old JSON state if needed
        state_data = self._settings.get([QUEUE_KEY])
        try:
            if state_data is not None and state_data != "[]":
                settings_state = json.loads(state_data)
                migrateFromSettings(settings_state)
                self._settings.set([QUEUE_KEY], None)
        except Exception:
            self._logger.error(f"Could not migrate old json state: {state_data}")
            self._logger.error(traceback.format_exc())

        profname = self._settings.get([PRINTER_PROFILE_KEY])
        for prof in self._printer_profiles:
            if prof["name"] == profname:
                self._printer_profile = dict(
                    model=prof["model"],
                    width=prof["width"],
                    depth=prof["depth"],
                    height=prof["height"],
                    formFactor=prof["formFactor"],
                    selfClearing=prof["selfClearing"],
                )
                break

        self.q = MultiQueue(
            queries, Strategy.IN_ORDER, self._refresh_ui_history
        )  # TODO set strategy for this and all other queue creations
        for q in queries.getQueues():
            if q.addr is not None:
                try:
                    self.q.add(
                        q.name,
                        LANQueue(
                            q.name,
                            q.addr,
                            self.plugin_data_dir,
                            self._logger,
                            Strategy.IN_ORDER,
                            self._on_queue_update,
                        ),
                    )
                except ValueError:
                    self._logger.error(
                        f"Unable to join network queue (name {q.name}, addr {q.addr}) due to ValueError"
                    )
            elif q.name != ARCHIVE_QUEUE:
                self.q.add(q.name, LocalQueue(queries, q.name, Strategy.IN_ORDER))

        self.d = Driver(
            queue=self.q,
            script_runner=self,
            logger=self._logger,
        )
        self.update(DA.DEACTIVATE)  # Initializes and passes printer state
        self._update_driver_settings()
        self._rm_temp_files()
        self.next_pause_is_spaghetti = False

        # It's possible to miss events or for some weirdness to occur in conditionals. Adding a watchdog
        # timer with a periodic tick ensures that the driver knows what the state of the printer is.
        self.watchdog = RepeatedTimer(5.0, lambda: self.update(DA.TICK))
        self.watchdog.start()
        self._logger.info("Continuous Print Plugin started")

    def update(self, a: DA):
        # Access current file via `get_current_job` instead of `is_current_file` because the latter may go away soon
        # See https://docs.octoprint.org/en/master/modules/printer.html#octoprint.printer.PrinterInterface.is_current_file
        # Avoid using payload.get('path') as some events may not express path info.
        path = self._printer.get_current_job().get("file", {}).get("name")
        pstate = self._printer.get_state_id()
        p = DP.BUSY
        if pstate == "OPERATIONAL":
            p = DP.IDLE
        elif pstate == "PAUSED":
            p = DP.PAUSED

        materials = []
        if self._spool_manager is not None:
            # We need *all* selected spools for all tools, so we must look it up from the plugin itself
            # (event payload also excludes color hex string which is needed for our identifiers)
            materials = self._spool_manager.api_getSelectedSpoolInformations()
            materials = [
                f"{m['material']}_{m['colorName']}_{m['color']}"
                if m is not None
                else None
                for m in materials
            ]

        if self.d.action(a, p, path, materials):
            self._refresh_ui_state()

        run = self.q.get_run()
        if run is not None:
            run = run.as_dict()
        self.q.update_peer_state(p.name, run)

    # part of EventHandlerPlugin
    def on_event(self, event, payload):
        if not hasattr(self, "d"):  # Ignore any messages arriving before init
            return

        current_file = self._printer.get_current_job().get("file", {}).get("name")
        is_current_path = current_file == self.d.current_path()

        # Try to fetch plugin-specific events, defaulting to None otherwise

        # This custom event is only defined when OctoPrint-TheSpaghettiDetective plugin is installed.
        tsd_command = getattr(
            octoprint.events.Events, "PLUGIN_THESPAGHETTIDETECTIVE_COMMAND", None
        )
        # This event is only defined when OctoPrint-SpoolManager plugin is installed.
        spool_selected = getattr(
            octoprint.events.Events, "PLUGIN__SPOOLMANAGER_SPOOL_SELECTED", None
        )
        spool_deselected = getattr(
            octoprint.events.Events, "PLUGIN__SPOOLMANAGER_SPOOL_DESELECTED", None
        )

        if event == Events.METADATA_ANALYSIS_FINISHED:
            # OctoPrint analysis writes to the printing file - we must remove
            # our temp files AFTER analysis has finished or else we'll get a "file not found" log error.
            # We do so when either we've finished printing or when the temp file is no longer selected
            if self._printer.get_state_id() != "OPERATIONAL":
                for path in TEMP_FILES.values():
                    if self._printer.is_current_file(path, sd=False):
                        return
            self._rm_temp_files()
        elif event == Events.PRINT_DONE:
            self.update(DA.SUCCESS)
        elif event == Events.PRINT_FAILED:
            # Note that cancelled events are already handled directly with Events.PRINT_CANCELLED
            self.update(DA.FAILURE)
        elif event == Events.PRINT_CANCELLED:
            if payload.get("user") is not None:
                self.update(DA.DEACTIVATE)
            else:
                self.update(DA.TICK)
        elif (
            is_current_path
            and tsd_command is not None
            and event == tsd_command
            and payload.get("cmd") == "pause"
            and payload.get("initiator") == "system"
        ):
            self.update(DA.SPAGHETTI)
        elif spool_selected is not None and event == spool_selected:
            self.update(DA.TICK)
        elif spool_deselected is not None and event == spool_deselected:
            self.update(DA.TICK)
        elif is_current_path and event == Events.PRINT_PAUSED:
            self.update(DA.TICK)
        elif is_current_path and event == Events.PRINT_RESUMED:
            self.update(DA.TICK)
        elif (
            event == Events.PRINTER_STATE_CHANGED
            and self._printer.get_state_id() == "OPERATIONAL"
        ):
            self.update(DA.TICK)
        elif event == Events.UPDATED_FILES:
            self._msg(type="updatefiles")
        elif event == Events.SETTINGS_UPDATED:
            self._update_driver_settings()

    def execute_gcode(self, key):
        gcode = self._settings.get([key])
        file_wrapper = StreamWrapper(key, BytesIO(gcode.encode("utf-8")))
        path = TEMP_FILES[key]
        added_file = self._file_manager.add_file(
            octoprint.filemanager.FileDestinations.LOCAL,
            path,
            file_wrapper,
            allow_overwrite=True,
        )
        self._logger.info(f"Wrote file {path}")
        self._printer.select_file(path, sd=False, printAfterSelect=True)
        return added_file

    def run_finish_script(self):
        self._msg("Print Queue Complete", type="complete")
        return self.execute_gcode(FINISHED_SCRIPT_KEY)

    def cancel_print(self):
        self._msg("Print cancelled", type="error")
        self._printer.cancel_print()

    def wait_for_bed_cooldown(self):
        self._logger.info("Running bed cooldown script")
        bed_cooldown_script = self._settings.get(["cp_bed_cooldown_script"]).split("\n")
        self._printer.commands(bed_cooldown_script, force=True)
        self._logger.info("Preparing for Bed Cooldown")
        self._printer.set_temperature("bed", 0)  # turn bed off
        start_time = time.time()

        while (time.time() - start_time) <= (
            60 * float(self._settings.get(["bed_cooldown_timeout"]))
        ):  # timeout converted to seconds
            bed_temp = self._printer.get_current_temperatures()["bed"]["actual"]
            if bed_temp <= float(self._settings.get(["bed_cooldown_threshold"])):
                self._logger.info(
                    f"Cooldown threshold of {self._settings.get(['bed_cooldown_threshold'])} has been met"
                )
                return

        self._logger.info(
            f"Timeout of {self._settings.get(['bed_cooldown_timeout'])} minutes exceeded"
        )
        return

    def clear_bed(self):
        if self._settings.get(["bed_cooldown_enabled"]):
            self.wait_for_bed_cooldown()
        return self.execute_gcode(CLEARING_SCRIPT_KEY)

    def start_print(self, item):
        self._msg(f"Job {item.job.name}: printing {item.path}")
        try:
            self._logger.info(f"Attempting to print {item.path} (sd={item.sd})")
            self._printer.select_file(item.path, item.sd, printAfterSelect=True)
        except InvalidFileLocation as e:
            self._logger.error(e)
            self._msg("File not found: " + item.path, type="error")
        except InvalidFileType as e:
            self._logger.error(e)
            self._msg("File not gcode: " + item.path, type="error")
        self._refresh_ui_state()
        return True

    def state_json(self):
        # IMPORTANT: Non-additive changes to this response string must be released in a MAJOR version bump
        # (e.g. 1.4.1 -> 2.0.0).
        db_qs = dict([(q.name, q.rank) for q in queries.getQueues()])
        qs = [
            dict(q.as_dict(), rank=db_qs[name])
            for name, q in self.q.queues.items()
            if name != "archive"
        ]
        qs.sort(key=lambda q: q["rank"])

        resp = {
            "active": self._active(),
            "status": "Initializing" if not hasattr(self, "d") else self.d.status,
            "queues": qs,
        }
        return json.dumps(resp)

    # Public API method returning the full state of the plugin in JSON format.
    # See `state_json()` for return values.
    @octoprint.plugin.BlueprintPlugin.route("/state", methods=["GET"])
    @restricted_access
    def get_state(self):
        return self.state_json()

    # Listen for resume from printer ("M118 //action:queuego") #from @grtrenchman
    def resume_action_handler(self, comm, line, action, *args, **kwargs):
        if not action == "queuego":
            return
        self.update(DA.ACTIVATE)
        self._refresh_ui_state()

    # Public method - enables/disables management and returns the current state
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/set_active", methods=["POST"])
    @restricted_access
    def set_active(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_STARTQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        self.update(
            DA.ACTIVATE if flask.request.form["active"] == "true" else DA.DEACTIVATE
        )
        return self.state_json()

    # PRIVATE API method - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/clear", methods=["POST"])
    @restricted_access
    def clear(self):
        i = 0
        keep_failures = flask.request.form["keep_failures"] == "true"
        keep_non_ended = flask.request.form["keep_non_ended"] == "true"
        self._logger.info(
            f"Clearing queue (keep_failures={keep_failures}, keep_non_ended={keep_non_ended})"
        )
        changed = []
        while i < len(self.q):
            v = self.q[i]
            self._logger.info(f"{v.name} -- end_ts {v.end_ts} result {v.result}")
            if v.end_ts is None and keep_non_ended:
                i = i + 1
            elif v.result == "failure" and keep_failures:
                i = i + 1
            else:
                del self.q[i]
                changed.append(i)
        return self.state_json()

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/set/add", methods=["POST"])
    @restricted_access
    def add_set(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_ADDQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        return json.dumps(
            queries.appendSet(
                DEFAULT_QUEUE, flask.request.form["job"], flask.request.form
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/add", methods=["POST"])
    @restricted_access
    def add_job(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_ADDQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        j = queries.newEmptyJob(DEFAULT_QUEUE)
        return json.dumps(j.as_dict())

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/set/mv", methods=["POST"])
    @restricted_access
    def mv_set(self):
        queries.moveSet(
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
    def mv_job(self):
        queries.moveJob(
            int(flask.request.form["id"]),
            int(
                flask.request.form["after_id"]
            ),  # Move to after this job (-1 for beginning of queue)
        )
        return json.dumps("ok")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/submit", methods=["POST"])
    @restricted_access
    def submit_job(self):
        j = queries.getJob(int(flask.request.form["id"]))
        queue_name = flask.request.form["queue"]
        filepaths = dict(
            [
                (
                    s.path,
                    self._file_manager.path_on_disk(FileDestinations.LOCAL, s.path),
                )
                for s in j.sets
            ]
        )
        # TODO less invasive structuring
        self.q.queues[queue_name].lan.q.submitJob(j.as_dict(), filepaths)

        # Remove the job now that it's been submitted
        queries.remove(job_ids=[j.id])
        return self.state_json()

    @octoprint.plugin.BlueprintPlugin.route("/job/edit/begin", methods=["POST"])
    @restricted_access
    def edit_job_start(self):
        queries.updateJob(flask.request.form["id"], {"draft": True})
        return json.dumps("ok")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/edit/end", methods=["POST"])
    @restricted_access
    def edit_job_end(self):
        data = json.loads(flask.request.form.get("json"))
        return json.dumps(queries.updateJob(data["id"], data))

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/import", methods=["POST"])
    @restricted_access
    def import_job(self):
        path = Path(flask.request.form.get("path"))
        dirname = Path(
            self._file_manager.add_folder(FileDestinations.LOCAL, "/" + str(path.stem))
        )
        manifest, filepaths = unpack_job(
            self._file_manager.path_on_disk(FileDestinations.LOCAL, str(path)),
            self._file_manager.path_on_disk(FileDestinations.LOCAL, str(dirname)),
        )

        queueName = flask.request.form.get("queue")
        return json.dumps(queries.importJob(queueName, manifest, dirname).as_dict())

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/job/export", methods=["POST"])
    @restricted_access
    def export_job(self):
        jobs = [
            queries.getJob(int(jid)) for jid in flask.request.form.getlist("job_ids[]")
        ]
        results = []
        for j in jobs:
            filepaths = dict(
                [
                    (
                        s.path,
                        self._file_manager.path_on_disk(FileDestinations.LOCAL, s.path),
                    )
                    for s in j.sets
                ]
            )
            with tempfile.NamedTemporaryFile(suffix=".gjob") as tf:
                pack_job(j.as_dict(), filepaths, tf.name)
                name = packed_name(j.name)
                print(
                    f"Packed job {j.id} with files {filepaths} into {tf.name}; moving into filemanager as /{name}"
                )
                results.append(
                    self._file_manager.add_file(
                        FileDestinations.LOCAL,
                        f"/{name}",
                        DiskFileWrapper(name, tf.name, move=False),
                    )
                )
        return json.dumps(results)

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/multi/rm", methods=["POST"])
    @restricted_access
    def rm_multi(self):
        return json.dumps(
            queries.remove(
                job_ids=flask.request.form.getlist("job_ids[]"),
                set_ids=flask.request.form.getlist("set_ids[]"),
                queue_ids=flask.request.form.getlist("queue_ids[]"),
            )
        )

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/multi/reset", methods=["POST"])
    @restricted_access
    def reset_multi(self):
        jids = flask.request.form.getlist("job_ids[]")
        sids = flask.request.form.getlist("set_ids[]")
        return json.dumps(queries.replenish(jids, sids))

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
    def get_history(self):
        return self.history_json()

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/clearHistory", methods=["POST"])
    @restricted_access
    def clear_history(self):
        queries.clearHistory()
        return json.dumps("OK")

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues", methods=["GET"])
    @restricted_access
    def get_queues(self):
        return json.dumps([q.as_dict() for q in queries.getQueues()])

    # PRIVATE API METHOD - may change without warning.
    @octoprint.plugin.BlueprintPlugin.route("/queues/commit", methods=["POST"])
    @restricted_access
    def commit_queues(self):
        (absent_names, added) = queries.assignQueues(
            json.loads(flask.request.form.get("queues"))
        )
        for name in absent_names:
            self.q.remove(name)
        for a in added:
            try:
                self.q.add(
                    a["name"],
                    LANQueue(
                        a["name"],
                        a["addr"],
                        self.plugin_data_dir,
                        self._logger,
                        Strategy.IN_ORDER,
                        self._on_queue_update,
                    ),  # TODO specify strategy
                )
            except ValueError:
                self._logger.error(
                    f"Unable to join network queue (name {qdata['name']}, addr {qdata['addr']}) due to ValueError"
                )

        # We trigger state update rather than returning it here, because this is called by the settings viewmodel
        # (not the main viewmodel that displays the queues)
        self._refresh_ui_state()
        return json.dumps("OK")

    # part of TemplatePlugin
    def get_template_vars(self):
        return dict(
            printer_profiles=self._printer_profiles, gcode_scripts=self._gcode_scripts
        )

    def get_template_configs(self):
        return [
            dict(
                type="settings",
                custom_bindings=True,
                template="continuousprint_settings.jinja2",
            ),
            dict(
                type="tab",
                name="Continuous Print",
                custom_bindings=False,
                template="continuousprint_tab.jinja2",
            ),
        ]

    # part of AssetPlugin
    def get_assets(self):
        return dict(
            js=[
                "js/cp_modified_sortable.js",
                "js/cp_modified_knockout-sortable.js",
                "js/continuousprint_api.js",
                "js/continuousprint_history_row.js",
                "js/continuousprint_set.js",
                "js/continuousprint_job.js",
                "js/continuousprint_queue.js",
                "js/continuousprint_viewmodel.js",
                "js/continuousprint_settings.js",
                "js/continuousprint.js",
            ],
            css=["css/continuousprint.css"],
        )

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return dict(
            continuousprint=dict(
                displayName="Continuous Print Plugin",
                displayVersion=self._plugin_version,
                # version check: github repository
                type="github_release",
                user="smartin015",
                repo="continuousprint",
                current=self._plugin_version,
                stable_branch=dict(
                    name="Stable", branch="master", comittish=["master"]
                ),
                prerelease_branches=[
                    dict(
                        name="Release Candidate",
                        branch="rc",
                        comittish=["rc", "master"],
                    )
                ],
                # update method: pip
                pip="https://github.com/smartin015/continuousprint/archive/{target_version}.zip",
            )
        )

    def add_permissions(*args, **kwargs):
        return [
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

    def support_gjob_format(*args, **kwargs):
        return dict(machinecode=dict(gjob=["gjob"]))


__plugin_name__ = "Continuous Print"
__plugin_pythoncompat__ = ">=3.7,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = ContinuousprintPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.access.permissions": __plugin_implementation__.add_permissions,
        "octoprint.comm.protocol.action": __plugin_implementation__.resume_action_handler,
        "octoprint.filemanager.extension_tree": __plugin_implementation__.support_gjob_format,
        # register to listen for "M118 //action:" commands
    }
