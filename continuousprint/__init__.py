# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.util import RepeatedTimer

from .data import (
    PRINTER_PROFILES,
    GCODE_SCRIPTS,
    Keys,
    CustomEvents,
    ASSETS,
    TEMPLATES,
    update_info,
)
from .storage import queries
from .api import Permission as CPQPermission
from .plugin import CPQPlugin


class ContinuousprintPlugin(
    octoprint.plugin.BlueprintPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.EventHandlerPlugin,
):

    # -------------------- Begin BlueprintPlugin --------------------

    def get_blueprint(self):
        # called before on_startup, but we need the plugin to provide the blueprint
        self.on_startup()
        return self._plugin.get_blueprint()

    def get_blueprint_kwargs(self):
        return self._plugin.get_blueprint_kwargs()

    def is_blueprint_protected(self):
        return self._plugin.is_blueprint_protected()

    def get_blueprint_api_prefixes(self):
        return self._plugin.get_blueprint_api_prefixes()

    # --------------------- End BlueprintPlugin --------------------

    # --------------------- Begin StartupPlugin ---------------------

    def on_startup(self, host=None, port=None):
        if not hasattr(self, "_plugin"):
            self._plugin = CPQPlugin(
                self._printer,
                self._settings,
                self._file_manager,
                self._plugin_manager,
                queries,
                self.get_plugin_data_folder(),
                self._logger,
                self._identifier,
                self._basefolder,
                self._event_bus.fire,
            )

    def on_after_startup(self):
        self._plugin.start()

        # It's possible to miss events or for some weirdness to occur in conditionals. Adding a watchdog
        # timer with a periodic tick ensures that the driver knows what the state of the printer is.
        self.watchdog = RepeatedTimer(5.0, self._plugin.tick)
        self.watchdog.start()
        self._logger.info("Continuous Print Plugin started")

    # ------------------------ End StartupPlugin ---------------------------

    # ------------------------ Begin EventHandlerPlugin --------------------

    def register_custom_events(*args, **kwargs):
        return [CustomEvents.__members__.values()]

    def on_event(self, event, payload):
        if not hasattr(self, "_plugin"):
            return
        return self._plugin.on_event(event, payload)

    # ----------------------- End EventHandlerPlugin --------------------

    # ---------------------- Begin SettingsPlugin --------------------

    def get_settings_defaults(self):
        return dict(
            [(member.setting, member.default) for member in Keys.__members__.values()]
        )

    # --------------------- End SettingsPlugin ----------------------

    # ---------------------- Begin TemplatePlugin -------------------
    def get_template_vars(self):
        return dict(
            printer_profiles=list(PRINTER_PROFILES.values()),
            gcode_scripts=list(GCODE_SCRIPTS.values()),
            custom_events=[e.as_dict() for e in CustomEvents],
            local_ip=self._plugin.get_local_ip(),
        )

    def get_template_configs(self):
        return TEMPLATES

    # -------------------- End TemplatePlugin ----------------

    # -------------------- Begin AssetPlugin ----------------
    def get_assets(self):
        return ASSETS

    # -------------------- End AssetPlugin

    # ---------------------------- Begin Plugin Hooks ------------------------------

    def get_update_information(self):
        return update_info(self._plugin_version)

    def add_permissions(*args, **kwargs):
        return [p.as_dict() for p in CPQPermission.__members__.values()]

    # Listen for resume from printer ("M118 //action:queuego") #from @grtrenchman
    def resume_action_handler(self, comm, line, action, *args, **kwargs):
        if not action == "queuego":
            return
        self._plugin.resume_action()

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
    }
