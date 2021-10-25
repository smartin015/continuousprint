# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import flask, json
from octoprint.server.util.flask import restricted_access
from octoprint.events import eventManager, Events

from .print_queue import PrintQueue, QueueItem


QUEUE_KEY = "cp_queue"
LOOPED_KEY = "cp_looped"
CLEARING_SCRIPT_KEY = "cp_bed_clearing_script"
FINISHED_SCRIPT_KEY = "cp_queue_finished"

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

    ##~~ SettingsPlugin
    def get_settings_defaults(self):
        d = {}
        d[QUEUE_KEY] = "[]"
        d[CLEARING_SCRIPT_KEY] = (
            "M17 ;enable steppers\n"
            "G91 ; Set relative for lift\n"
            "G0 Z10 ; lift z by 10\n"
            "G90 ;back to absolute positioning\n"
            "M190 R25 ; set bed to 25 for cooldown\n"
            "G4 S90 ; wait for temp stabalisation\n"
            "M190 R30 ;verify temp below threshold\n"
            "G0 X200 Y235 ;move to back corner\n"
            "G0 X110 Y235 ;move to mid bed aft\n"
            "G0 Z1v ;come down to 1MM from bed\n"
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
        d[LOOPED_KEY] = "false"
        return d

    ##~~ StartupPlugin
    def on_after_startup(self):
        self._settings.save()
        self.q = PrintQueue(self._settings, QUEUE_KEY)
        self.d = ContinuousPrintDriver(
                    queue = self.q,
                    bed_clear_script_fn = self.run_bed_clear_script,
                    finish_script_fn = self.run_finish_script,
                    start_print_fn = self.start_print,
                    cancel_print_fn = self.cancel_print,
                    logger = self._logger,
                )
        self._logger.info("Continuous Print Plugin started")

    ##~~ EventHandlerPlugin
    def on_event(self, event, payload):
        # TODO reload UI should be triggered in some way
        # self._msg(type="reload") # reload UI
        if event == Events.PRINT_DONE:
            self.d.on_print_success()
        elif event == Events.PRINT_FAILED:
            self.d.on_print_failed()
        elif event == Events.PRINT_CANCELLED:
            self.d.on_print_cancelled()
        elif event == Events.PRINT_PAUSED:
            self.d.on_print_paused()
        # elif event == Events.PRINTER_STATE_CHANGED:
        #     if self._printer.get_state_id() == "OPERATIONAL": # "operational" implies proor print success
        #         self.start_next_print()
        elif event == Events.UPDATED_FILES: # TODO necessary?
            self._msg(type="updatefiles")

    def run_bed_clear_script(self):
        self._logger.info("Clearing bed")
        bed_clearing_script = self._settings.get([CLEARING_SCRIPT_KEY]).split("\n")
        self._printer.commands(bed_clearing_script, force=True)

    def run_finish_script(self, run_finish_script=True):
        self._msg("Print Queue Complete", type="complete")
        if run_finish_script:
            queue_finished_script = self._settings.get([FINISHED_SCRIPT_KEY]).split("\n")
            self._printer.commands(queue_finished_script, force=True)

    def cancel_print(self):
        self._msg("Print cancelled", type="error")
        self._printer.cancel_print()

    def start_print(self, item):
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

    def state_json(self):
        # Values are stored serialized, so we need to create a json string and inject them
        resp = ('{"looped": %s, "queue": %s}' % (
                self._settings.get([LOOPED_KEY]),
                self._settings.get([QUEUE_KEY]),
            ))
        print(resp)
        return resp
            

    ##~~ APIs
    @octoprint.plugin.BlueprintPlugin.route("/state", methods=["GET"])
    @restricted_access
    def state(self):
        return self.state_json()

    @octoprint.plugin.BlueprintPlugin.route("/set_loop", methods=["GET"])
    @restricted_access
    def set_loop(self):
        self._settings.set(["cp_looped"], "true" if flask.request.args.get("looped") == "true" else "false")
        return flask.make_response("success", 200)

    @octoprint.plugin.BlueprintPlugin.route("/move", methods=["POST"])
    @restricted_access
    def move(self):
        self.q.move(
                int(flask.request.form["idx"]),
                int(flask.request.form["count"]),
                int(flask.request.form["offs"]),
                )
        return self.state_json()

    @octoprint.plugin.BlueprintPlugin.route("/add", methods=["POST"])
    @restricted_access
    def add(self):
        idx = flask.request.form.get("idx")
        self.q.add([QueueItem(
                name=i["name"],
                path=i["path"],
                sd=i["sd"],
            ) for i in json.loads(flask.request.form["items"])], int(idx) if idx is not None else None)
        return self.state_json()

    @octoprint.plugin.BlueprintPlugin.route("/remove", methods=["POST"])
    @restricted_access
    def remove(self):
        self.q.remove(
                int(flask.request.form["idx"]),
                int(flask.request.form["count"]),
                )
        return self.state_json()


    @octoprint.plugin.BlueprintPlugin.route("/start", methods=["GET"])
    @restricted_access
    def start(self):
        if flask.request.args.get("clear_history", False):
            while self.q.peek().end_ts is not None:
                self.q.pop()

        self.d.set_active(active=True, printer_ready=(self._printer.get_state_id() == "OPERATIONAL"))
        return flask.make_response("success", 200)

    ##~~  TemplatePlugin
    def get_template_vars(self):
        return dict(
            cp_enabled=(self.d.active),
            cp_bed_clearing_script=self._settings.get([CLEARING_SCRIPT_KEY]),
            cp_queue_finished=self._settings.get([FINISHED_SCRIPT_KEY]),
        )

    def get_template_configs(self):
        return [
            dict(
                type="settings",
                custom_bindings=False,
                template="continuousprint_settings.jinja2",
            ),
            dict(
                type="tab", custom_bindings=False, template="continuousprint_tab.jinja2"
            ),
        ]

    ##~~ AssetPlugin
    def get_assets(self):
        return dict(js=[
            "js/continuousprint_api.js",
            "js/continuousprint.js",
            ], css=["css/continuousprint.css"])

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
                user="Zinc-OS",
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
                pip="https://github.com/Zinc-OS/continuousprint/archive/{target_version}.zip",
            )
        )


__plugin_name__ = "Continuous Print"
__plugin_pythoncompat__ = ">=3.8.3,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = ContinuousprintPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
