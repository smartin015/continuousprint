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

	print_complete=False

	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		return dict(
			cp_enabled=False,
			cp_queue="[]",
			cp_bed_clearing_script=""
		)




	##~~ StartupPlugin mixin
	def on_after_startup(self):
		self._settings.set(["cp_enabled"], False)
		self._settings.save()
		self._logger.info("Continuous Print Plugin started")
	
	
	
	
	##~~ Event hook
	def on_event(self, event, payload):
		from octoprint.events import Events
		##  Print complete check it was the print in the bottom of the queue and not just any print
		if event == Events.PRINT_DONE:
			if self._settings.get_boolean(["cp_enabled"]) == True:
				queue = json.loads(self._settings.get(["cp_queue"]))
				self._logger.info(payload["path"])
				self._logger.info(queue[0]["path"])
				if payload["path"]==queue[0]["path"]:
					queue.pop(0)
					self._settings.set(["cp_queue"], json.dumps(queue))
					self._settings.save()
					
					# Clear down the bed
					self._logger.info("Clearing bed")
					bed_clearing_script=self._settings.get(["cp_bed_clearing_script"])
					self._logger.info(bed_clearing_script.split("\n"))
					self._printer.commands(bed_clearing_script.split("\n"))					
					
					self._plugin_manager.send_plugin_message(self._identifier, dict(type="reload", msg=""))
				else:
					self._settings.set(["cp_enabled"], False)
					self._settings.save()
					
		
		# On fail stop all prints
		if event == Events.PRINT_FAILED or event == Events.PRINT_CANCELLED:
			self._settings.set(["cp_enabled"], False) # Set enabled to false
			self._settings.save()
			self._plugin_manager.send_plugin_message(self._identifier, dict(type="popup", msg="Print queue cancelled"))
		
		if event == Events.PRINTER_STATE_CHANGED:
			# If the printer is operational and the last print succeeded then we start next print
			state = self._printer.get_state_id()
			if state  == "OPERATIONAL":
				self.start_next_print()
		
		if event == Events.FILE_SELECTED:
			# Add some code to clear the print at the bottom
			self._logger.info("File selected")
			bed_clearing_script=self._settings.get(["cp_bed_clearing_script"])

	def start_next_print(self):
		if self._settings.get_boolean(["cp_enabled"]) == True:
			queue = json.loads(self._settings.get(["cp_queue"]))
			if len(queue) > 0:
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="popup", msg="Automatically starting print: " + queue[0]["name"]))
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
				self._settings.set(["cp_enabled"], False) # Set enabled to false
				self._settings.save()
				self._plugin_manager.send_plugin_message(self._identifier, dict(type="complete", msg="Print Queue Complete"))
			
			
	##~~ APIs
	@octoprint.plugin.BlueprintPlugin.route("/queue", methods=["GET"])
	@restricted_access
	def get_queue(self):
		queue = json.loads(self._settings.get(["cp_queue"]))
		return flask.jsonify(queue=queue)
			
	@octoprint.plugin.BlueprintPlugin.route("/addqueue", methods=["POST"])
	@restricted_access
	def add_queue(self):
		queue = json.loads(self._settings.get(["cp_queue"]))
		queue.append(dict(
			name=flask.request.form["name"],
			path=flask.request.form["path"],
			sd=flask.request.form["sd"]
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
		self._settings.set(["cp_enabled"], True) # Set enabled to true
		self._settings.save()
		self.start_next_print()
		return flask.make_response("success", 200)
	
	
	##~~  TemplatePlugin
	def get_template_vars(self):
		return dict(
			cp_enabled=self._settings.get_boolean(["cp_enabled"]),
			cp_bed_clearing_script=self._settings.get(["cp_bed_clearing_script"])
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
				user="nukeem",
				repo="continuousprint",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/nukeem/continuousprint/archive/{target_version}.zip"
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

