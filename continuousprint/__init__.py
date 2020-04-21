# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import eventManager, Events

class ContinuousprintPlugin(octoprint.plugin.SettingsPlugin,
                            octoprint.plugin.TemplatePlugin,
							octoprint.plugin.StartupPlugin, 
							 octoprint.plugin.EventHandlerPlugin,
							octoprint.plugin.types.OctoPrintPlugin):

	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		return dict(
			cp_enabled=False,
			cp_time=5
		)

	##~~ StartupPlugin mixin
	def on_after_startup(self):
		cp_enabled = self._settings.get_boolean(["cp_enabled"])
		cp_times = self._settings.get_int(["cp_time"])
		self._logger.info("Continuous Print Plugin started")
	
	##~~ ProgressPlugin hook
	def on_event(self, event, payload):
		from octoprint.events import Events
		if event == Events.PRINT_DONE:
			if self._settings.get_boolean(["cp_enabled"]) == True:
				self._logger.info("Print complete. Restarting")
				self._logger.info(payload)
				sd = True;
				if payload["origin"] == "local":
					sd = False;
					
				while (not self._printer.is_ready()):
					self._logger.info("Waiting")
					
				self._printer.select_file(payload["path"], sd)
				self._printer.start_print();

	##~~  TemplatePlugin
	def get_template_vars(self):
		return dict(
			cp_enabled=self._settings.get_boolean(["cp_enabled"]),
			cp_time=self._settings.get_int(["cp_time"])
		)
	def get_template_configs(self):
		return [
			dict(type="settings", custom_bindings=False)
		]


	##~~ Softwareupdate hook
	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
		# for details.
		return dict(
			continuousprint=dict(
				displayName="Continuousprint Plugin",
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

