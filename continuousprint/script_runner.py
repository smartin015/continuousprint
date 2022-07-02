import time
from io import BytesIO

from octoprint.filemanager.util import StreamWrapper
from octoprint.filemanager.destinations import FileDestinations
from octoprint.printer import InvalidFileLocation, InvalidFileType
from .storage.lan import ResolveError
from .data import Keys, TEMP_FILES


class ScriptRunner:
    def __init__(
        self,
        msg,
        get_key,
        file_manager,
        logger,
        printer,
        refresh_ui_state,
    ):
        self._msg = msg
        self._get_key = get_key
        self._file_manager = file_manager
        self._logger = logger
        self._printer = printer
        self._refresh_ui_state = refresh_ui_state

    def _wrap_stream(self, name, gcode):
        return StreamWrapper(name, BytesIO(gcode.encode("utf-8")))

    def _execute_gcode(self, key):
        gcode = self._get_key(key)
        file_wrapper = self._wrap_stream(key.setting, gcode)
        path = TEMP_FILES[key.setting]
        added_file = self._file_manager.add_file(
            FileDestinations.LOCAL,
            path,
            file_wrapper,
            allow_overwrite=True,
        )
        self._logger.info(f"Wrote file {path}")
        self._printer.select_file(path, sd=False, printAfterSelect=True)
        return added_file

    def run_finish_script(self):
        self._msg("Print Queue Complete", type="complete")
        return self._execute_gcode(Keys.FINISHED_SCRIPT)

    def cancel_print(self):
        self._msg("Print cancelled", type="error")
        self._printer.cancel_print()

    def start_cooldown(self):
        self._msg("Running bed cooldown script")
        self._execute_gcode(Keys.BED_COOLDOWN_SCRIPT)
        self._printer.set_temperature("bed", 0)  # turn bed off

    def clear_bed(self):
        if self._get_key(Keys.BED_COOLDOWN_ENABLED):
            self.wait_for_bed_cooldown()
        return self._execute_gcode(Keys.CLEARING_SCRIPT)

    def start_print(self, item):
        self._msg(f"{item.job.name}: printing {item.path}")

        path = item.path
        # LAN set objects may not link directly to the path of the print file.
        # In this case, we have to resolve the path by syncing files / extracting
        # gcode files from .gjob. This works without any extra FileManager changes
        # only becaue self._fileshare was configured with a basedir in the OctoPrint
        # file structure
        if hasattr(item, "resolve"):
            try:
                path = item.resolve()
            except ResolveError as e:
                self._logger.error(e)
                self._msg(f"Could not resolve LAN print path {path}", type="error")
                return False
            self._logger.info(f"Resolved LAN print path to {path}")

        try:
            self._logger.info(f"Attempting to print {path} (sd={item.sd})")
            self._printer.select_file(path, item.sd, printAfterSelect=True)
        except InvalidFileLocation as e:
            self._logger.error(e)
            self._msg("File not found: " + path, type="error")
            return False
        except InvalidFileType as e:
            self._logger.error(e)
            self._msg("File not gcode: " + path, type="error")
            return False
        self._refresh_ui_state()
        return True
