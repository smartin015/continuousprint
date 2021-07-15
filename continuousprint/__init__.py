# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import flask, json
from octoprint.server.util.flask import restricted_access
from octoprint.events import eventManager, Events

from .print_queue import PrintQueue


QUEUE_KEY = "cp_queue"
LOOPED_KEY = "cp_looped"
HISTORY_KEY = "cp_print_history"
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

    print_history = []
    enabled = False
    paused = False
    item = None

    ##~~ SettingsPlugin mixin
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
        d[HISTORY_KEY] = "[]"
        return d

    ##~~ StartupPlugin mixin
    def on_after_startup(self):
        self._settings.save()
        self.q = PrintQueue(self._settings, QUEUE_KEY)
        self._logger.info("Continuous Print Plugin started")

    def _msg(self, msg="", type="popup"):
        self._plugin_manager.send_plugin_message(
            self._identifier, dict(type=type, msg=msg)
        )

    ##~~ Event hook
    def on_event(self, event, payload):
        try:
            ##  Print complete check it was the print in the bottom of the queue and not just any print
            if event == Events.PRINT_DONE:
                if self.enabled == True:
                    self.complete_print(payload)

            # On fail stop all prints
            if event == Events.PRINT_FAILED or event == Events.PRINT_CANCELLED:
                self.enabled = False  # Set enabled to false
                self._msg("Print queue cancelled", type="error")

            if event == Events.PRINTER_STATE_CHANGED:
                # If the printer is operational and the last print succeeded then we start next print
                state = self._printer.get_state_id()
                if state == "OPERATIONAL":
                    if self.enabled == True and self.paused == False:
                        self.start_next_print()

            if event == Events.FILE_SELECTED:
                # Add some code to clear the print at the bottom
                self._logger.info("File selected")
                bed_clearing_script = self._settings.get(["cp_bed_clearing_script"])

            if event == Events.UPDATED_FILES:
                self._msg(type="updatefiles")
        except Exception as error:
            raise error
            self._logger.exception("Exception when handling event.")

    def complete_print(self, payload):
        item = self.q.pop()
        if payload["path"] == item["path"] and item["count"] > 0:

            # check to see if loop count is set. If it is increment times run.
            if "times_run" not in item:
                item["times_run"] = 0

            item["times_run"] += 1

            # On complete_print, remove the item from the queue
            # if the item has run for loop count  or no loop count is specified and
            # if looped is True requeue the item.
            if item["times_run"] >= item["count"]:
                item["times_run"] = 0
                queue.pop(0)
                self.looped = looped
                if bool(self._settings.get([LOOPED_KEY])) and item != None:
                    self.q.add(item)

            # Add to the print History
            print_history = json.loads(self._settings.get(["cp_print_history"]))
            # 	#calculate time
            # 	time=payload["time"]/60;
            # 	suffix="mins"
            # 	if time>60:
            # 		time = time/60
            # 		suffix = "hours"
            # 		if time>24:
            # 			time= time/24
            # 			suffix= "days"
            # 	#Add to the print History
            # 	inPrintHistory=False
            # 	if len(print_history)==1 and item["path"]==print_history[0]["path"]:
            # 		print_history[0]=dict(
            # 			path = payload["path"],
            # 			name = payload["name"],
            # 			time = (print_history[0]["time"]+payload["time"])/(print_history[0]["times_run"]+1),
            # 			times_run =  print_history[0]["times_run"]+1,
            # 			title = print_history[0]["title"]+" "+print_history[i]["times_run"]+". " + str(int(time))+suffix
            # 		)
            # 		inPrintHistory=True
            # 	if len(print_history)>1:
            # 		for i in range(0,len(print_history)-1):
            # 			if item["path"]==print_history[i]["path"] and InPrintHistory != True:
            # 				print_history[i]=dict(
            # 					path = payload["path"],
            # 					name = payload["name"],
            # 					time = (print_history[i]["time"]+payload["time"])/(print_history[i]["times_run"]+1),
            # 					times_run =  print_history[i]["times_run"]+1,
            # 					title = print_history[i]["title"]+" "+print_history[i]["times_run"]+". " + str(int(time))+suffix
            # 				)
            # 				inPrintHistory=True
            # 	if inPrintHistory == False:
            # 		print_history.append(dict(
            # 			path = payload["path"],
            # 			name = payload["name"],
            # 			time = payload["time"],
            # 			times_run =  item["times_run"],
            # 			title="Print Times: 1. "+str(int(time))+suffix
            # 		))
            #
            print_history.append(dict(name=payload["name"], time=payload["time"]))

            # save print history
            self._settings.set([HISTORY_KEY], json.dumps(print_history))
            self._settings.save()

            # Clear down the bed
            if len(self.q) > 0:
                self.clear_bed()

            # Tell the UI to reload
            self._msg(type="reload")
        else:
            enabled = False

    def parse_gcode(self, input_script):
        script = []
        for x in input_script:
            if x.find("[PAUSE]", 0) > -1:
                self.paused = True
                self._msg("Queue paused", type="paused")
            else:
                script.append(x)
        return script

    def clear_bed(self):
        self._logger.info("Clearing bed")
        bed_clearing_script = self._settings.get([CLEARING_SCRIPT_KEY]).split("\n")
        self._printer.commands(self.parse_gcode(bed_clearing_script), force=True)

    def complete_queue(self):
        self.enabled = False  # Set enabled to false
        self._msg("Print Queue Complete", type="complete")
        queue_finished_script = self._settings.get([FINISHED_SCRIPT_KEY]).split("\n")
        self._printer.commands(
            self.parse_gcode(queue_finished_script, force=True)
        )  # send queue finished script to the printer

    def start_next_print(self):
        if self.paused or not self.enabled:
            return

        if len(self.q) == 0:
            self.complete_queue()
            return

        item = self.q.peek()
        self._msg("Starting print: " + item["name"])
        self._msg(type="reload")

        sd = item["sd"] == "true"
        try:
            self._printer.select_file(item["path"], sd)
            self._logger.info(item["path"])
            self._printer.start_print()
        except InvalidFileLocation:
            self._msg("File not found: " + item["path"], type="error")
        except InvalidFileType:
            self._msg("File not gcode: " + item["path"], type="error")

    ##~~ APIs
    @octoprint.plugin.BlueprintPlugin.route("/looped", methods=["GET"])
    @restricted_access
    def looped(self):
        return self._settings.get(["cp_looped"])

    @octoprint.plugin.BlueprintPlugin.route("/loop", methods=["GET"])
    @restricted_access
    def loop(self):
        self._settings.set(["cp_looped"], "true")

    @octoprint.plugin.BlueprintPlugin.route("/unloop", methods=["GET"])
    @restricted_access
    def unloop(self):
        self._settings.set(["cp_looped"], "false")

    @octoprint.plugin.BlueprintPlugin.route("/queue", methods=["GET"])
    @restricted_access
    def get_queue(self):
        return self.q.json()

    @octoprint.plugin.BlueprintPlugin.route("/print_history", methods=["GET"])
    @restricted_access
    def get_print_history(self):
        # return flask.jsonify(queue=json.loads(self._settings.get(["cp_print_history"])))
        return '{"queue":' + self._settings.get(["cp_print_history"]) + "}"

    @octoprint.plugin.BlueprintPlugin.route("/queueup", methods=["GET"])
    @restricted_access
    def queue_up(self):
        i = int(flask.request.args.get("index", 0))
        self.q.move(i, i - 1)
        return self.q.json()

    @octoprint.plugin.BlueprintPlugin.route("/change", methods=["GET"])
    @restricted_access
    def change(self):
        self.q.setCount(
            int(flask.request.args.get("index")), int(flask.request.args.get("count"))
        )
        return self.q.json()

    @octoprint.plugin.BlueprintPlugin.route("/queuedown", methods=["GET"])
    @restricted_access
    def queue_down(self):
        i = int(flask.request.args.get("index", 0))
        self.q.move(i, i + 1)
        return self.q.json()

    @octoprint.plugin.BlueprintPlugin.route("/addqueue", methods=["POST"])
    @restricted_access
    def add_queue(self):
        self.q.add(
            dict(
                name=flask.request.form["name"],
                path=flask.request.form["path"],
                sd=flask.request.form["sd"],
                count=int(flask.request.form["count"]),
                times_run=0,
            )
        )
        return flask.make_response("success", 200)

    @octoprint.plugin.BlueprintPlugin.route("/removequeue", methods=["DELETE"])
    @restricted_access
    def remove_queue(self):
        del self.q[int(flask.request.args.get("index", 0))]
        return flask.make_response("success", 200)

    @octoprint.plugin.BlueprintPlugin.route("/startqueue", methods=["GET"])
    @restricted_access
    def start_queue(self):
        self._settings.set(["cp_print_history"], "[]")  # Clear Print History
        self._settings.save()
        self.paused = False
        self.enabled = True  # Set enabled to true
        self.start_next_print()
        return flask.make_response("success", 200)

    @octoprint.plugin.BlueprintPlugin.route("/resumequeue", methods=["GET"])
    @restricted_access
    def resume_queue(self):
        self.paused = False
        self.start_next_print()
        return flask.make_response("success", 200)

    ##~~  TemplatePlugin
    def get_template_vars(self):
        return dict(
            cp_enabled=self.enabled,
            cp_bed_clearing_script=self._settings.get([CLEARING_SCRIPT_KEY]),
            cp_queue_finished=self._settings.get([FINISHED_SCRIPT_KEY]),
            cp_paused=self.paused,
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
        return dict(js=["js/continuousprint.js"], css=["css/continuousprint.css"])

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
__plugin_pythoncompat__ = ">=2.7,<4"  # python 2 and 3


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = ContinuousprintPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
