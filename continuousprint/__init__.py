# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import octoprint.util
import flask
import json
import time
from io import BytesIO
from octoprint.server.util.flask import restricted_access
from octoprint.events import Events
from octoprint.access.permissions import Permissions, ADMIN_GROUP
import octoprint.filemanager
from octoprint.filemanager.util import StreamWrapper
from octoprint.filemanager.destinations import FileDestinations
from octoprint.util import RepeatedTimer


from .print_queue import PrintQueue, QueueItem
from .driver import ContinuousPrintDriver, Action as DA, Printer as DP

QUEUE_KEY = "cp_queue"
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

    def _update_driver_settings(self):
        self.d.set_retry_on_pause(
            self._settings.get([RESTART_ON_PAUSE_KEY]),
            self._settings.get([RESTART_MAX_RETRIES_KEY]),
            self._settings.get([RESTART_MAX_TIME_KEY]),
        )

    # part of SettingsPlugin
    def get_settings_defaults(self):
        d = {}
        d[QUEUE_KEY] = "[]"
        d[CLEARING_SCRIPT_KEY] = (
            "M17 ;enable steppers\n"
            "G91 ; Set relative for lift\n"
            "G0 Z10 ; lift z by 10\n"
            "G90 ;back to absolute positioning\n"
            "M190 R25 ; set bed to 25 and wait for cooldown\n"
            "G0 X200 Y235 ;move to back corner\n"
            "G0 X110 Y235 ;move to mid bed aft\n"
            "G0 Z1 ;come down to 1MM from bed\n"
            "G0 Y0 ;wipe forward\n"
            "G0 Y235 ;wipe aft\n"
            "G28 ; home"
        )
        d[FINISHED_SCRIPT_KEY] = (
            "M18 ; disable steppers\n"
            "M104 T0 S0 ; extruder heater off\n"
            "M140 S0 ; heated bed heater off\n"
            "M300 S880 P300 ; beep to show its finished"
        )
        d[RESTART_MAX_RETRIES_KEY] = 3
        d[RESTART_ON_PAUSE_KEY] = False
        d[RESTART_MAX_TIME_KEY] = 60 * 60
        d[BED_COOLDOWN_ENABLED_KEY] = False
        d[BED_COOLDOWN_SCRIPT_KEY] = "; Put script to run before bed cools here\n"
        d[BED_COOLDOWN_THRESHOLD_KEY] = 30
        d[BED_COOLDOWN_TIMEOUT_KEY] = 60
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

        self._settings.save()
        self.q = PrintQueue(self._settings, QUEUE_KEY)
        self.d = ContinuousPrintDriver(
            queue=self.q,
            script_runner=self,
            logger=self._logger,
        )
        self.update(DA.DEACTIVATE) # Initializes and passes printer state
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

        if self.d.action(a, p, path):
          self._msg(type="reload") # Reload UI when new state is added

    # part of EventHandlerPlugin
    def on_event(self, event, payload):
        if not hasattr(self, "d"):  # Ignore any messages arriving before init
            return

        current_file = self._printer.get_current_job().get("file", {}).get("name")
        is_current_path = current_file == self.d.current_path()
        is_finish_script = current_file == TEMP_FILES[FINISHED_SCRIPT_KEY]

        # This custom event is only defined when OctoPrint-TheSpaghettiDetective plugin is installed.
        # try to fetch the attribute but default to None
        tsd_command = getattr(
            octoprint.events.Events, "PLUGIN_THESPAGHETTIDETECTIVE_COMMAND", None
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
            print(payload.get('user'))
            if payload.get('user') is not None:
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

    def _write_temp_gcode(self, key):
        gcode = self._settings.get([key])
        file_wrapper = StreamWrapper(key, BytesIO(gcode.encode("utf-8")))
        added_file = self._file_manager.add_file(
            octoprint.filemanager.FileDestinations.LOCAL,
            TEMP_FILES[key],
            file_wrapper,
            allow_overwrite=True,
        )
        self._logger.info(f"Wrote file {added_file}")
        return added_file

    def run_finish_script(self):
        self._msg("Print Queue Complete", type="complete")
        path = self._write_temp_gcode(FINISHED_SCRIPT_KEY)
        self._printer.select_file(path, sd=False, printAfterSelect=True)
        return path

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

        while (time.time() - start_time) <= (60 * float(self._settings.get(["bed_cooldown_timeout"]))):  # timeout converted to seconds
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
        path = self._write_temp_gcode(CLEARING_SCRIPT_KEY)
        self._printer.select_file(path, sd=False, printAfterSelect=True)
        return path

    def start_print(self, item, clear_bed=True):
        self._msg("Starting print: " + item.name)
        self._msg(type="reload")
        try:
            self._printer.select_file(item.path, item.sd)
            self._logger.info(item.path)
            self._printer.start_print()
        except InvalidFileLocation:
            self._msg("File not found: " + item.path, type="error")
        except InvalidFileType:
            self._msg("File not gcode: " + item.path, type="error")
        return item.path

    def state_json(self, extra_message=None):
        # Values are stored json-serialized, so we need to create a json string and inject them into it
        q = self._settings.get([QUEUE_KEY])

        # Format extra message as key:value
        if extra_message is not None:
            extra_message = f', extra_message: "{extra_message}"'
        else:
            extra_message = ""

        # IMPORTANT: Non-additive changes to this response string must be released in a MAJOR version bump
        # (e.g. 1.4.1 -> 2.0.0).
        resp = '{"active": %s, "status": "%s", "queue": %s%s}' % (
            "true" if self._active() else "false",
            "Initializing" if not hasattr(self, "d") else self.d.status,
            q,
            extra_message,
        )
        return resp

    # Listen for resume from printer ("M118 //action:queuego") #from @grtrenchman
    def resume_action_handler(self, comm, line, action, *args, **kwargs):
        if not action == "queuego":
            return
        self.update(DA.ACTIVATE)

    # Public API method returning the full state of the plugin in JSON format.
    # See `state_json()` for return values.
    @octoprint.plugin.BlueprintPlugin.route("/state", methods=["GET"])
    @restricted_access
    def state(self):
        return self.state_json()

    # Public method - enables/disables management and returns the current state
    # IMPORTANT: Non-additive changes to this method MUST be done via MAJOR version bump
    # (e.g. 1.4.1 -> 2.0.0)
    @octoprint.plugin.BlueprintPlugin.route("/set_active", methods=["POST"])
    @restricted_access
    def set_active(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_STARTQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        self.update(DA.ACTIVATE if flask.request.form["active"] == "true" else DA.DEACTIVATE)
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
    @octoprint.plugin.BlueprintPlugin.route("/assign", methods=["POST"])
    @restricted_access
    def assign(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_ASSIGNQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        items = json.loads(flask.request.form["items"])
        self.q.assign(
            [
                QueueItem(
                    name=i["name"],
                    path=i["path"],
                    sd=i["sd"],
                    job=i["job"],
                    run=i["run"],
                    start_ts=i.get("start_ts"),
                    end_ts=i.get("end_ts"),
                    result=i.get("result"),
                    retries=i.get("retries"),
                )
                for i in items
            ]
        )
        return self.state_json()

    # DEPRECATED
    @octoprint.plugin.BlueprintPlugin.route("/move", methods=["POST"])
    @restricted_access
    def move(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_CHQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        idx = int(flask.request.form["idx"])
        count = int(flask.request.form["count"])
        offs = int(flask.request.form["offs"])
        self.q.move(idx, count, offs)
        depr = "DEPRECATED: plugin/continuousprint/move is no longer used and will be removed in the next major release."
        self._logger.warn(depr)
        return self.state_json(depr)

    # DEPRECATED
    @octoprint.plugin.BlueprintPlugin.route("/add", methods=["POST"])
    @restricted_access
    def add(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_ADDQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        idx = flask.request.form.get("idx")
        if idx is None:
            idx = len(self.q)
        else:
            idx = int(idx)
        items = json.loads(flask.request.form["items"])
        self.q.add(
            [
                QueueItem(
                    name=i["name"],
                    path=i["path"],
                    sd=i["sd"],
                    job=i["job"],
                    run=i["run"],
                )
                for i in items
            ],
            idx,
        )
        depr = "DEPRECATED: plugin/continuousprint/add is no longer used and will be removed in the next major release."
        self._logger.warn(depr)
        return self.state_json(depr)

    # DEPRECATED
    @octoprint.plugin.BlueprintPlugin.route("/remove", methods=["POST"])
    @restricted_access
    def remove(self):
        if not Permissions.PLUGIN_CONTINUOUSPRINT_RMQUEUE.can():
            return flask.make_response("Insufficient Rights", 403)
            self._logger.info("attempt failed due to insufficient permissions.")
        idx = int(flask.request.form["idx"])
        count = int(flask.request.form["count"])
        self.q.remove(idx, count)

        depr = "DEPRECATED: plugin/continuousprint/remove is no longer used and will be removed in the next major release."
        self._logger.warn(depr)
        return self.state_json(depr)

    # DEPRECATED
    @octoprint.plugin.BlueprintPlugin.route("/reset", methods=["POST"])
    @restricted_access
    def reset(self):
        idxs = json.loads(flask.request.form["idxs"])
        for idx in idxs:
            i = self.q[idx]
            i.start_ts = None
            i.end_ts = None
        self.q.remove(idx, len(idxs))
        depr = "DEPRECATED: plugin/continuousprint/reset is no longer used and will be removed in the next major release."
        self._logger.warn(depr)
        return self.state_json(depr)

    # part of TemplatePlugin
    def get_template_vars(self):
        return dict(
            cp_enabled=self._active(),
            cp_bed_clearing_script=self._settings.get([CLEARING_SCRIPT_KEY]),
            cp_queue_finished=self._settings.get([FINISHED_SCRIPT_KEY]),
            cp_restart_on_pause_enabled=self._settings.get_boolean(
                [RESTART_ON_PAUSE_KEY]
            ),
            cp_restart_on_pause_max_seconds=self._settings.get_int(
                [RESTART_MAX_TIME_KEY]
            ),
            cp_restart_on_pause_max_restarts=self._settings.get_int(
                [RESTART_MAX_RETRIES_KEY]
            ),
        )

    def get_template_configs(self):
        return [
            dict(
                type="settings",
                custom_bindings=False,
                template="continuousprint_settings.jinja2",
            ),
            dict(
                type="tab",
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
                "js/continuousprint_queueitem.js",
                "js/continuousprint_queueset.js",
                "js/continuousprint_job.js",
                "js/continuousprint_viewmodel.js",
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
                description="Allows for starting queue",
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
            dict(
                key="ASSIGNQUEUE",
                name="Assign the whole Queue",
                description="Allows for loading the whole queue from JSON",
                roles=["admin", "continuousprint-assign"],
                dangerous=True,
                default_groups=[ADMIN_GROUP],
            ),
        ]


__plugin_name__ = "Continuous Print"
__plugin_pythoncompat__ = ">=3.6,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = ContinuousprintPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.access.permissions": __plugin_implementation__.add_permissions,
        "octoprint.comm.protocol.action": __plugin_implementation__.resume_action_handler,
        # register to listen for "M118 //action:" commands
    }
