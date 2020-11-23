# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import flask, json
from octoprint.server.util.flask import restricted_access
from octoprint.events import eventManager, Events

class ContinuousprintPlugin(octoprint.plugin.SettingsPlugin,
							octoprint.plugin.TemplatePlugin,
							octoprint.plugin.AssetPlugin,
							octoprint.plugin.StartupPlugin,
							octoprint.plugin.BlueprintPlugin,
							octoprint.plugin.EventHandlerPlugin):
	print_history = []
	enabled = False
	paused = False
	looped = False;
	temp= None


	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		return dict(
			cp_queue="[]",
			cp_bed_clearing_script="M17 ;enable steppers\nM91 ; Set relative for lift\nG0 Z10 ; lift z by 10\nG90 ;back to absolute positioning\nM190 R25 ; set bed to 25 for cooldown\nG4 S90 ; wait for temp stabalisation\nM190 R30 ;verify temp below threshold\nG0 X200 Y235 ;move to back corner\nG0 X110 Y235 ;move to mid bed aft\nG0 Z1v ;come down to 1MM from bed\nG0 Y0 ;wipe forward\nG0 Y235 ;wipe aft\nG28 ; home",
			cp_queue_finished="M18 ; disable steppers\nM104 T0 S0 ; extruder heater off\nM140 S0 ; heated bed heater off\nM300 S880 P300 ; beep to show its finished"
		)




	##~~ StartupPlugin mixin
	def on_after_startup(self):
		self._logger.info("Continuous Print Plugin started")
	
	
	
	
	##~~ Event hook
	def on_event(self, event, payload):
		from octoprint.events import Events
		##  Print complete check it was the print in the bottom of the queue and not just any print
		if event == Events.PRINT_DONE:
			if self.enabled == True:
				self.complete_print(payload)
		
		# On fail stop all prints
		if event == Events.PRINT_FAILED or event == Events.PRINT_CANCELLED:
			self.enabled = False # Set enabled to false
			self._plugin_manager.send_plugin_message(self._identifier, dict(type="error", msg="Print queue cancelled"))
		
		if event == Events.PRINTER_STATE_CHANGED:
				# If the printer is operational and the last print succeeded then we start next print
				state = self._printer.get_state_id()
				if state  == "OPERATIONAL":
					self.start_next_print()
			
		if event == Events.FILE_SELECTED:
			# Add some code to clear the print at the bottom
			self._logger.info("File selected")
			bed_clearing_script=self._settings.get(["cp_bed_clearing_script"])

		if event == Events.UPDATED_FILES:
			self._plugin_manager.send_plugin_message(self._identifier, dict(type="updatefiles", msg=""))

	def complete_print(self, payload):
		queue = json.loads(self._settings.get(["cp_queue"]))
		if payload["path"]==queue[0]["path"]:
			# move the print to the end of the queue
			self.temp = queue[0]
			queue.pop(0)
			if self.looped==True and self.temp!=None:
				queue.append(self.temp)
			self._settings.set(["cp_queue"], json.dumps(queue))
			self._settings.save()
			# Add to the history
			self.print_history.append(dict(
				name = payload["name"],
				time = payload["time"]
			))

			# Clear down the bed
			self.clear_bed()

			# Tell the UI to reload
			self._plugin_manager.send_plugin_message(self._identifier, dict(type="reload", msg=""))
		else:
			enabled = False

	def parse_gcode(self, input_script):
		script = []
		for x in input_script:
			if x.find("[PAUSE]", 0) > -1:
				self.paused = True
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="paused", msg="Queue paused"))
			else:
				script.append(x)
		return script

	def clear_bed(self):
		self._logger.info("Clearing bed")
		bed_clearing_script=self._settings.get(["cp_bed_clearing_script"]).split("\n")	
		self._printer.commands(self.parse_gcode(bed_clearing_script))
		
	def complete_queue(self):
		self.enabled = False # Set enabled to false
		self._plugin_manager.send_plugin_message(self._identifier, dict(type="complete", msg="Print Queue Complete"))
		queue_finished_script = self._settings.get(["cp_queue_finished"]).split("\n")
		self._printer.commands(self.parse_gcode(queue_finished_script))

	def start_next_print(self):
		if self.enabled == True and self.paused == False:
			queue = json.loads(self._settings.get(["cp_queue"]))
				
			
			if len(queue) > 0:
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="popup", msg="Starting print: " + queue[0]["name"]))
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="reload", msg=""))

				sd = False
				if queue[0]["sd"] == "true":
					sd = True
				try:
					self._printer.select_file(queue[0]["path"], sd)
					self._logger.info(queue[0]["path"])
					self._printer.start_print()
				except InvalidFileLocation:
					self._plugin_manager.send_plugin_message(self._identifier, dict(type="popup", msg="ERROR file not found"))
				except InvalidFileType:
					self._plugin_manager.send_plugin_message(self._identifier, dict(type="popup", msg="ERROR file not gcode"))
			else:
				self.complete_queue()
			
			
			
	##~~ APIs
	@octoprint.plugin.BlueprintPlugin.route("/loop", methods=["GET"])
	@restricted_access
	def loop(self):
		self.looped=True
		
		
	@octoprint.plugin.BlueprintPlugin.route("/unloop", methods=["GET"])
	@restricted_access
	def unloop(self):
		self.looped=False
		
	@octoprint.plugin.BlueprintPlugin.route("/queue", methods=["GET"])
	@restricted_access
	def get_queue(self):
		queue = json.loads(self._settings.get(["cp_queue"]))
		
		for x in self.print_history:
			queue.append(x)
		
		return flask.jsonify(queue=queue)
		
	@octoprint.plugin.BlueprintPlugin.route("/queueup", methods=["GET"])
	@restricted_access
	def queue_up(self):
		index = int(flask.request.args.get("index", 0))
		queue = json.loads(self._settings.get(["cp_queue"]))
		orig = queue[index]
		queue[index] = queue[index-1]
		queue[index-1] = orig	
		self._settings.set(["cp_queue"], json.dumps(queue))
		self._settings.save()
		return flask.jsonify(queue=queue)
		
	@octoprint.plugin.BlueprintPlugin.route("/queuedown", methods=["GET"])
	@restricted_access
	def queue_down(self):
		index = int(flask.request.args.get("index", 0))
		queue = json.loads(self._settings.get(["cp_queue"]))
		orig = queue[index]
		queue[index] = queue[index+1]
		queue[index+1] = orig	
		self._settings.set(["cp_queue"], json.dumps(queue))
		self._settings.save()		
		return flask.jsonify(queue=queue)
			
	@octoprint.plugin.BlueprintPlugin.route("/addqueue", methods=["POST"])
	@restricted_access
	def add_queue(self):
		queue = json.loads(self._settings.get(["cp_queue"]))
		queue.append(dict(
			name=flask.request.form["name"],
			path=flask.request.form["path"],
			sd=flask.request.form["sd"],
			count=flask.request.form["count"]
		))
		self._settings.set(["cp_queue"], json.dumps(queue))
		self._settings.save()
		return flask.make_response("success", 200)
	
	@octoprint.plugin.BlueprintPlugin.route("/removequeue", methods=["DELETE"])
	@restricted_access
	def remove_queue(self):
		queue = json.loads(self._settings.get(["cp_queue"]))
		self._logger.info(flask.request.args.get("index", 0))
		queue.pop(int(flask.request.args.get("index", 0)))
		self._settings.set(["cp_queue"], json.dumps(queue))
		self._settings.save()
		return flask.make_response("success", 200)
	
	@octoprint.plugin.BlueprintPlugin.route("/startqueue", methods=["GET"])
	@restricted_access
	def start_queue(self):
		self.print_history = []
		self.paused = False
		self.enabled = True # Set enabled to true
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
			cp_bed_clearing_script=self._settings.get(["cp_bed_clearing_script"]),
			cp_queue_finished=self._settings.get(["cp_queue_finished"]),
			cp_paused=self.paused
		)
	def get_template_configs(self):
		return [
			dict(type="settings", custom_bindings=False, template="continuousprint_settings.jinja2"),
			dict(type="tab", custom_bindings=False, template="continuousprint_tab.jinja2")
		]

	##~~ AssetPlugin
	def get_assets(self):
		return dict(
			js=["js/continuousprint.js"]
		)


	##~~ Softwareupdate hook
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

				# update method: pip
				pip="https://github.com/Zinc-OS/continuousprint/archive/{target_version}.zip"
			)
		)


__plugin_name__ = "Continuous Print"
__plugin_pythoncompat__ = ">=2.7,<4" # python 2 and 3

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = ContinuousprintPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

