# coding=utf-8

import os
import socket
import json
import time
import traceback
from pathlib import Path
from octoprint.events import Events
from octoprint.filemanager.destinations import FileDestinations
import octoprint.timelapse

from peerprint.filesharing import Fileshare
from .driver import Driver, Action as DA, Printer as DP
from .queues.lan import LANQueue
from .queues.multi import MultiQueue
from .queues.local import LocalQueue
from .queues.abstract import Strategy
from .storage.database import (
    migrateFromSettings,
    init as init_db,
    DEFAULT_QUEUE,
    ARCHIVE_QUEUE,
)
from .data import (
    PRINTER_PROFILES,
    GCODE_SCRIPTS,
    Keys,
    PRINT_FILE_DIR,
    TEMP_FILES,
)
from .api import ContinuousPrintAPI
from .script_runner import ScriptRunner


class CPQPlugin(ContinuousPrintAPI):
    def __init__(
        self,
        printer,
        settings,
        file_manager,
        plugin_manager,
        queries,
        data_folder,
        logger,
        identifier,
        basefolder,
    ):
        self._basefolder = basefolder
        self._printer = printer
        self._settings = settings
        self._file_manager = file_manager
        self._plugin_manager = plugin_manager
        self._queries = queries
        self._data_folder = data_folder
        self._logger = logger
        self._identifier = identifier

    def start(self):
        self._setup_thirdparty_plugin_integration()
        self._init_db()
        self._init_fileshare()
        self._init_queues()
        self._init_driver()

    def _on_queue_update(self, q, now=time.time()):
        self._logger.debug("_on_queue_update")
        self._sync_state()

    def _on_settings_updated(self):
        self.d.set_retry_on_pause(
            self._get_key(Keys.RESTART_ON_PAUSE, False),
            int(self._get_key(Keys.RESTART_MAX_RETRIES, 0)),
            int(self._get_key(Keys.RESTART_MAX_TIME, 0)),
        )

    def _set_key(self, k, v):
        return self._settings.set([k.setting], v)

    def _get_key(self, k, default=None):
        v = self._settings.get([k.setting])
        return v if v is not None else default

    def _add_folder(self, path):
        return self._file_manager.add_folder(
            FileDestinations.LOCAL, self._path_in_storage(path)
        )

    def resume_action(self):
        self._update(DA.ACTIVATE)
        self._sync_state()

    def get_local_ip(self):
        # https://stackoverflow.com/a/57355707
        hostname = socket.gethostname()
        try:
            return socket.gethostbyname(f"{hostname}.local")
        except socket.gaierror:
            return socket.gethostbyname(hostname)

    def _add_set(self, path, sd, draft=True):
        self._get_queue(DEFAULT_QUEUE).add_set(
            "", dict(path=path, sd="true" if sd else "false", count=1, jobDraft=draft)
        )
        self._sync_state()

    def _path_on_disk(self, path):
        return self._file_manager.path_on_disk(FileDestinations.LOCAL, path)

    def _path_in_storage(self, path):
        return self._file_manager.path_in_storage(FileDestinations.LOCAL, path)

    def _msg(self, data):
        # See continuousprint_viewmodel.js onDataUpdaterPluginMessage
        self._plugin_manager.send_plugin_message(self._identifier, data)

    def _setup_thirdparty_plugin_integration(self):
        # Turn on "restart on pause" when Obico plugin is detected (must be version 1.8.11 or higher for custom event hook)
        if getattr(octoprint.events.Events, "PLUGIN_OBICO_COMMAND", None) is not None:
            self._logger.info(
                "Has Obico plugin with custom events integration - enabling failure automation"
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
            self._set_key(Keys.MATERIAL_SELECTION, False)
        self._settings.save()

        # Try to fetch plugin-specific events, defaulting to None otherwise

        # This custom event is only defined when the Obico plugin is installed.
        self.EVENT_OBICO_COMMAND = getattr(
            octoprint.events.Events, "PLUGIN_OBICO_COMMAND", None
        )
        # These events are only defined when OctoPrint-SpoolManager plugin is installed.
        self.EVENT_SPOOL_SELECTED = getattr(
            octoprint.events.Events, "PLUGIN__SPOOLMANAGER_SPOOL_SELECTED", None
        )
        self.EVENT_SPOOL_DESELECTED = getattr(
            octoprint.events.Events, "PLUGIN__SPOOLMANAGER_SPOOL_DESELECTED", None
        )

    def _init_fileshare(self, fs_cls=Fileshare):
        fileshare_dir = self._path_on_disk(f"{PRINT_FILE_DIR}/fileshare/")
        fileshare_addr = f"{self.get_local_ip()}:0"
        self._logger.info(f"Starting fileshare with address {fileshare_addr}")
        self._fileshare = fs_cls(fileshare_addr, fileshare_dir, self._logger)
        self._fileshare.connect()

    def _init_db(self):
        init_db(
            db_path=Path(self._data_folder) / "queue.sqlite3",
            logger=self._logger,
        )

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

        self._queries.clearOldState()

    def _init_queues(self, lancls=LANQueue, localcls=LocalQueue):
        self._printer_profile = PRINTER_PROFILES.get(
            self._get_key(Keys.PRINTER_PROFILE)
        )
        self.q = MultiQueue(
            self._queries, Strategy.IN_ORDER, self._sync_history
        )  # TODO set strategy for this and all other queue creations
        for q in self._queries.getQueues():
            if q.addr is not None:
                try:
                    lq = lancls(
                        q.name,
                        q.addr,
                        self._logger,
                        Strategy.IN_ORDER,
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
                    localcls(
                        self._queries,
                        q.name,
                        Strategy.IN_ORDER,
                        self._printer_profile,
                        self._path_on_disk,
                        self._add_folder,
                    ),
                )

    def _init_driver(self, srcls=ScriptRunner, dcls=Driver):
        self._runner = srcls(
            self.popup,
            self._get_key,
            self._file_manager,
            self._logger,
            self._printer,
            self._sync_state,
        )
        self.d = dcls(
            queue=self.q,
            script_runner=self._runner,
            logger=self._logger,
        )
        self._update(DA.DEACTIVATE)  # Initializes and passes printer state
        self._on_settings_updated()

    def tick(self):
        # Catch/pass all exceptions to prevent errors from stopping the repeated timer.
        try:
            self._update(DA.TICK)
        except Exception:
            traceback.print_exc()

    def _delete_timelapse(self, full_path):
        # This borrows heavily from `octoprint.timelapse.deleteTimelapse`
        # (https://github.com/OctoPrint/OctoPrint/blob/f430257d7072a83692fc2392c683ed8c97ae47b6/src/octoprint/server/api/timelapse.py#L175)
        # We cannot use it directly as it's bundled into a Flask route
        try:
            thumb_path = octoprint.timelapse.create_thumbnail_path(full_path)
            os.remove(full_path)
            os.remove(thumb_path)
            return True
        except Exception:
            self._logger.warning(
                f"Failed to delete timelapse data ({full_path}, {thumb_path})"
            )
            self._logger.debug(traceback.format_exc())
            return False

    def on_event(self, event, payload):
        if not hasattr(self, "d"):  # Ignore any messages arriving before init
            return
        if event is None:
            return

        current_file = self._printer.get_current_job().get("file", {}).get("name")
        is_current_path = current_file == self.d.current_path()

        if (
            event == Events.UPLOAD
        ):  # https://docs.octoprint.org/en/master/events/index.html#file-handling
            upload_action = self._get_key(Keys.UPLOAD_ACTION, "do_nothing")
            if upload_action != "do_nothing":
                self._add_set(
                    path=payload["path"],
                    sd=payload["target"] != "local",
                    draft=(upload_action != "add_printable"),
                )
            else:
                return

        if event == Events.MOVIE_DONE:
            # Optionally delete time-lapses created from bed clearing/finishing scripts
            temp_files_base = [f.split("/")[-1] for f in TEMP_FILES.values()]
            if (
                payload["gcode"] in temp_files_base
                and self._get_key(Keys.AUTOMATION_TIMELAPSE_ACTION) == "auto_remove"
            ):
                if self._delete_timelapse(payload["movie"]):
                    self._logger.info(
                        f"Deleted temp file timelapse for {payload['gcode']}"
                    )
                return

            thumb_path = octoprint.timelapse.create_thumbnail_path(payload["movie"])
            if self._queries.annotateLastRun(
                payload["gcode"], payload["movie"], thumb_path
            ):
                self._logger.info(
                    f"Annotated run of {payload['gcode']} with timelapse details"
                )
                self._sync_history()
            return

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
            and event == self.EVENT_OBICO_COMMAND
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
            try:
                materials = self._spool_manager.api_getSelectedSpoolInformations()
                materials = [
                    f"{m['material']}_{m['colorName']}_{m['color']}"
                    if m is not None
                    else None
                    for m in materials
                ]
            except Exception:
                self._logger.warning(
                    "SpoolManager getSelectedSpoolInformations() returned error; skipping material assignment"
                )

        if self.d.action(a, p, path, materials):
            self._sync_state()

        run = self.q.get_run()
        if run is not None:
            run = run.as_dict()
        netname = self._get_key(Keys.NETWORK_NAME)
        self.q.update_peer_state(netname, p.name, run, self._printer_profile)

    def _state_json(self):
        # IMPORTANT: Non-additive changes to this response string must be released in a MAJOR version bump
        # (e.g. 1.4.1 -> 2.0.0).
        db_qs = dict([(q.name, q.rank) for q in self._queries.getQueues()])
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
            "statusType": "INIT" if not hasattr(self, "d") else self.d.status_type.name,
            "queues": qs,
        }
        return json.dumps(resp)

    def _history_json(self):
        h = self._queries.getHistory()

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
                    Strategy.IN_ORDER,
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
