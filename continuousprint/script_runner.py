import time
from io import BytesIO

from octoprint.filemanager.util import StreamWrapper
from octoprint.filemanager.destinations import FileDestinations
from octoprint.printer import InvalidFileLocation, InvalidFileType
from .storage.lan import ResolveError


class ScriptRunner:
    def __init__(
        self,
        _msg,
        _get_key,
        _file_manager,
        _logger,
        _printer,
        _refresh_ui_state,
        keys,
        temp_files,
    ):
        self._keys = keys
        self._temp_files = temp_files
        self._msg = _msg
        self._get_key = _get_key
        self._file_manager = _file_manager
        self._logger = _logger
        self._printer = _printer
        self._refresh_ui_state = _refresh_ui_state

    def execute_gcode(self, key):
        gcode = self._get_key(key)
        file_wrapper = StreamWrapper(key.setting, BytesIO(gcode.encode("utf-8")))
        path = self._temp_files[key.setting]
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
        return self.execute_gcode(self._keys.FINISHED_SCRIPT)

    def cancel_print(self):
        self._msg("Print cancelled", type="error")
        self._printer.cancel_print()

    def wait_for_bed_cooldown(self):
        self._logger.info("Running bed cooldown script")
        bed_cooldown_script = self._get_key(Keys.BED_COOLDOWN_SCRIPT).split("\n")
        self._printer.commands(bed_cooldown_script, force=True)
        self._logger.info("Preparing for Bed Cooldown")
        self._printer.set_temperature("bed", 0)  # turn bed off
        start_time = time.time()
        timeout = float(self._get_key(self._keys.BED_COOLDOWN_TIMEOUT))
        threshold = float(self._get_key(self._keys.BED_COOLDOWN_THRESHOLD))

        while (time.time() - start_time) <= (
            60 * timeout
        ):  # timeout converted to seconds
            bed_temp = self._printer.get_current_temperatures()["bed"]["actual"]
            if bed_temp <= threshold:
                self._logger.info(f"Cooldown threshold of {threshold} has been met")
                return

        self._logger.info(f"Timeout of {timeout} minutes exceeded")
        return

    def clear_bed(self):
        if self._get_key(self._keys.BED_COOLDOWN_ENABLED):
            self.wait_for_bed_cooldown()
        return self.execute_gcode(self._keys.CLEARING_SCRIPT)

    def start_print(self, item):
        self._msg(f"Job {item.job.name}: printing {item.path}")

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
