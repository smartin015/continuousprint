# coding=utf-8
from __future__ import absolute_import

import json
import time
import traceback
from pathlib import Path
import octoprint.plugin
import octoprint.util
from octoprint.events import Events
import octoprint.filemanager
from octoprint.filemanager.util import DiskFileWrapper
from octoprint.filemanager.destinations import FileDestinations
from octoprint.util import RepeatedTimer

from peerprint.filesharing import Fileshare
from .driver import Driver, Action as DA, Printer as DP
from .queues.lan import LANQueue
from .queues.multi import MultiQueue
from .queues.local import LocalQueue
from .storage.database import (
    migrateFromSettings,
    init as init_db,
    ARCHIVE_QUEUE,
)
from .data import (
    PRINTER_PROFILES,
    GCODE_SCRIPTS,
    Keys,
    PRINT_FILE_DIR,
    TEMP_FILES,
    ASSETS,
    TEMPLATES,
    update_info,
)
from .storage import queries
from .script_runner import ScriptRunner
from .api import ContinuousPrintAPI, Permission as CPQPermission

UPDATE_PD = 1


class ContinuousprintPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.EventHandlerPlugin,
    ContinuousPrintAPI,
):
    def _on_queue_update(self, q, now=time.time()):
        self._logger.debug("_on_queue_update")
        self._sync_state()

    def _on_settings_updated(self):
        self.d.set_retry_on_pause(
            self._get_key(Keys.RESTART_ON_PAUSE),
            self._get_key(Keys.RESTART_MAX_RETRIES),
            self._get_key(Keys.RESTART_MAX_TIME),
        )

    def _rm_temp_files(self):
        # Clean up any file references from prior runs
        for path in TEMP_FILES.values():
            if self._file_manager.file_exists(FileDestinations.LOCAL, path):
                self._file_manager.remove_file(FileDestinations.LOCAL, path)

    def _set_key(self, k, v):
        return self._settings.set([k.setting], v)

    def _get_key(self, k, default=None):
        v = self._settings.get([k.setting])
        return v if v is not None else default

    # --------------------- Begin StartupPlugin ---------------------

    def _setup_thirdparty_plugin_integration(self):
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
            self._set_key(Keys.RESTART_ON_PAUSE, True)
        else:
            self._set_key(Keys.RESTART_ON_PAUSE, False)

        # SpoolManager plugin isn't required, but does enable material-based printing if it exists
        # Code based loosely on https://github.com/OllisGit/OctoPrint-PrintJobHistory/ (see _getPluginInformation)
        smplugin = self._plugin_manager.plugins.get("SpoolManager")
        if smplugin is not None and smplugin.enabled:
            self._spool_manager = smplugin.implementation
            self._logger.info("SpoolManager found - enabling material selection")
            self._set_key(Keys.MATERIAL_SELECTION, True)
        else:
            self._spool_manager = None
            self._set_key(Keys.MATERIAL_SELECTION, True)
        self._settings.save()

        # Try to fetch plugin-specific events, defaulting to None otherwise

        # This custom event is only defined when OctoPrint-TheSpaghettiDetective plugin is installed.
        self.EVENT_TSD_COMMAND = getattr(
            octoprint.events.Events, "PLUGIN_THESPAGHETTIDETECTIVE_COMMAND", None
        )
        # These events are only defined when OctoPrint-SpoolManager plugin is installed.
        self.EVENT_SPOOL_SELECTED = getattr(
            octoprint.events.Events, "PLUGIN__SPOOLMANAGER_SPOOL_SELECTED", None
        )
        self.EVENT_SPOOL_DESELECTED = getattr(
            octoprint.events.Events, "PLUGIN__SPOOLMANAGER_SPOOL_DESELECTED", None
        )

    def on_after_startup(self):
        self._setup_thirdparty_plugin_integration()

        init_db(
            db_path=Path(self.get_plugin_data_folder()) / "queue.sqlite3",
            logger=self._logger,
        )

        fileshare_dir = self._path_on_disk(f"{PRINT_FILE_DIR}/fileshare/")
        self._fileshare = Fileshare("0.0.0.0:0", fileshare_dir, self._logger)
        self._fileshare.connect()

        # Migrate from old JSON state if needed
        state_data = self._get_key(Keys.QUEUE)
        try:
            if state_data is not None and state_data != "[]":
                settings_state = json.loads(state_data)
                migrateFromSettings(settings_state)
                self._get_key(Keys.QUEUE)
        except Exception:
            self._logger.error(f"Could not migrate old json state: {state_data}")
            self._logger.error(traceback.format_exc())

        self._printer_profile = PRINTER_PROFILES[
            self._get_key(data.Keys.PRINTER_PROFILE)
        ]
        self.q = MultiQueue(
            queries, queues.abstract.Strategy.IN_ORDER, self._sync_history
        )  # TODO set strategy for this and all other queue creations
        for q in queries.getQueues():
            if q.addr is not None:
                try:
                    lq = LANQueue(
                        q.name,
                        q.addr,
                        self._logger,
                        queues.abstract.Strategy.IN_ORDER,
                        self._on_queue_update,
                        self._fileshare,
                        self._printer_profile,
                        self._path_on_disk,
                    )
                    lq.connect()
                    self.q.add(q.name, lq)
                except ValueError:
                    self._logger.error(
                        f"Unable to join network queue (name {q.name}, addr {q.addr}) due to ValueError"
                    )
            elif q.name != ARCHIVE_QUEUE:
                self.q.add(
                    q.name,
                    LocalQueue(
                        queries,
                        q.name,
                        queues.abstract.Strategy.IN_ORDER,
                        self._printer_profile,
                        self._path_on_disk,
                    ),
                )

        self._runner = ScriptRunner(
            self.popup,
            self._get_key,
            self._file_manager,
            self._logger,
            self._printer,
            self._sync_state,
            Keys,
            data.TEMP_FILES,
        )
        self.d = Driver(
            queue=self.q,
            script_runner=self._runner,
            logger=self._logger,
        )
        self._update(DA.DEACTIVATE)  # Initializes and passes printer state
        self._on_settings_updated()
        self._rm_temp_files()

        # It's possible to miss events or for some weirdness to occur in conditionals. Adding a watchdog
        # timer with a periodic tick ensures that the driver knows what the state of the printer is.
        self.watchdog = RepeatedTimer(5.0, lambda: self._update(DA.TICK))
        self.watchdog.start()
        self._logger.info("Continuous Print Plugin started")

    # ------------------------ End StartupPlugin ---------------------------

    # ------------------------ Begin EventHandlerPlugin --------------------

    def on_event(self, event, payload):
        if not hasattr(self, "d"):  # Ignore any messages arriving before init
            return
        if event is None:
            return

        current_file = self._printer.get_current_job().get("file", {}).get("name")
        is_current_path = current_file == self.d.current_path()

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
            self._update(DA.SUCCESS)
        elif event == Events.PRINT_FAILED:
            # Note that cancelled events are already handled directly with Events.PRINT_CANCELLED
            self._update(DA.FAILURE)
        elif event == Events.PRINT_CANCELLED:
            if payload.get("user") is not None:
                self._update(DA.DEACTIVATE)
            else:
                self._update(DA.TICK)
        elif (
            is_current_path
            and event == self.EVENT_TSD_COMMAND
            and payload.get("cmd") == "pause"
            and payload.get("initiator") == "system"
        ):
            self._update(DA.SPAGHETTI)
        elif event == self.EVENT_SPOOL_SELECTED:
            self._update(DA.TICK)
        elif event == self.EVENT_SPOOL_DESELECTED:
            self._update(DA.TICK)
        elif is_current_path and event == Events.PRINT_PAUSED:
            self._update(DA.TICK)
        elif is_current_path and event == Events.PRINT_RESUMED:
            self._update(DA.TICK)
        elif (
            event == Events.PRINTER_STATE_CHANGED
            and self._printer.get_state_id() == "OPERATIONAL"
        ):
            self._update(DA.TICK)
        elif event == Events.SETTINGS_UPDATED:
            self._on_settings_updated()

    # ----------------------- End EventHandlerPlugin --------------------

    #  ---------------------- Begin ContinuousPrintAPI -------------------

    def _msg(self, data):
        # See continuousprint_viewmodel.js onDataUpdaterPluginMessage
        self._plugin_manager.send_plugin_message(self._identifier, data)

    def _path_on_disk(self, path):
        return self._file_manager.path_on_disk(FileDestinations.LOCAL, path)

    def _path_in_storage(self, path):
        return self._file_manager.path_in_storage(FileDestinations.LOCAL, path)

    def _update(self, a: DA):
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
            self._sync_state()

        run = self.q.get_run()
        if run is not None:
            run = run.as_dict()
        netname = self._get_key(Keys.NETWORK_NAME)
        self.q.update_peer_state(netname, p.name, run)

    def _state_json(self):
        # IMPORTANT: Non-additive changes to this response string must be released in a MAJOR version bump
        # (e.g. 1.4.1 -> 2.0.0).
        db_qs = dict([(q.name, q.rank) for q in queries.getQueues()])
        qs = [
            dict(q.as_dict(), rank=db_qs[name])
            for name, q in self.q.queues.items()
            if name != "archive"
        ]
        qs.sort(key=lambda q: q["rank"])

        active = self.d.state != self.d._state_inactive if hasattr(self, "d") else False
        resp = {
            "active": active,
            "profile": self._get_key(Keys.PRINTER_PROFILE),
            "status": "Initializing" if not hasattr(self, "d") else self.d.status,
            "queues": qs,
        }
        return json.dumps(resp)

    def _history_json(self):
        h = queries.getHistory()

        if self.q.run is not None:
            for row in h:
                if row["run_id"] == self.q.run:
                    row["active"] = True
                    break
        return json.dumps(h)

    def _get_queue(self, name):
        return self.q.get(name)

    def _commit_queues(self, added, removed):
        for name in removed:
            self.q.remove(name)
        for a in added:
            try:
                lq = LANQueue(
                    a["name"],
                    a["addr"],
                    self._logger,
                    queues.abstract.Strategy.IN_ORDER,
                    self._on_queue_update,
                    self._fileshare,
                    self._printer_profile,
                    self._path_on_disk,
                )  # TODO specify strategy
                lq.connect()
                self.q.add(a["name"], lq)
            except ValueError:
                self._logger.error(
                    f"Unable to join network queue (name {qdata['name']}, addr {qdata['addr']}) due to ValueError"
                )

        # We trigger state update rather than returning it here, because this is called by the settings viewmodel
        # (not the main viewmodel that displays the queues)
        self._sync_state()

    # ----------------------- End ContinuousPrintAPI -----------------

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
        self._update(DA.ACTIVATE)
        self._sync_state()

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
