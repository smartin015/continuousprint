import time
from io import BytesIO
from pathlib import Path
from octoprint.filemanager.util import StreamWrapper
from octoprint.filemanager.destinations import FileDestinations
from octoprint.printer import InvalidFileLocation, InvalidFileType
from octoprint.server import current_user
from octoprint.slicing.exceptions import SlicingException
from .storage.peer import ResolveError
from .storage.database import STLResolveError
from .data import TEMP_FILE_DIR, CustomEvents, Keys
from .storage.queries import getAutomationForEvent
from .automation import genEventScript, getInterpreter


class ScriptRunner:
    def __init__(
        self,
        msg,
        file_manager,
        get_key,
        slicing_manager,
        logger,
        printer,
        refresh_ui_state,
        fire_event,
        spool_manager,
    ):
        self._msg = msg
        self._file_manager = file_manager
        self._slicing_manager = slicing_manager
        self._logger = logger
        self._printer = printer
        self._get_key = get_key
        self._refresh_ui_state = refresh_ui_state
        self._fire_event = fire_event
        self._spool_manager = spool_manager
        self._symbols = dict(
            current=dict(),
            external=dict(),
            metadata=dict(),
        )

    def _get_user(self):
        try:
            return current_user.get_name()
        except AttributeError:
            return None

    def _wrap_stream(self, name, gcode):
        return StreamWrapper(name, BytesIO(gcode.encode("utf-8")))

    def _execute_gcode(self, evt, gcode):
        file_wrapper = self._wrap_stream(evt.event, gcode)
        path = str(Path(TEMP_FILE_DIR) / f"{evt.event}.gcode")
        added_file = self._file_manager.add_file(
            FileDestinations.LOCAL,
            path,
            file_wrapper,
            allow_overwrite=True,
        )
        self._logger.info(f"Wrote file {path}")
        self._printer.select_file(
            path, sd=False, printAfterSelect=True, user=self._get_user()
        )
        return added_file

    def _do_msg(self, evt, running=False):
        if evt == CustomEvents.FINISH:
            self._msg("Print Queue Complete", type="complete")
        elif evt == CustomEvents.PRINT_CANCEL:
            self._msg("Print cancelled", type="error")

        if running:
            if evt == CustomEvents.COOLDOWN:
                self._msg("Running bed cooldown script")
            elif evt == CustomEvents.PRINT_SUCCESS:
                self._msg("Running success script")
            elif evt == CustomEvents.AWAITING_MATERIAL:
                self._msg("Running script while awaiting material")

    def set_current_symbols(self, symbols):
        last_path = self._symbols["current"].get("path")
        self._symbols["current"] = symbols.copy()

        # Current state can change metadata
        path = self._symbols["current"].get("path")
        if (
            path is not None
            and path != last_path
            and self._file_manager.file_exists(FileDestinations.LOCAL, path)
            and self._file_manager.has_analysis(FileDestinations.LOCAL, path)
        ):
            # See https://docs.octoprint.org/en/master/modules/filemanager.html#octoprint.filemanager.analysis.GcodeAnalysisQueue
            # for analysis values - or `.metadata.json` within .octoprint/uploads
            self._symbols["metadata"] = self._file_manager.get_metadata(
                FileDestinations.LOCAL, path
            )

    def set_external_symbols(self, symbols):
        assert type(symbols) is dict
        self._symbols["external"] = symbols

    def set_active(self, item, cb):
        path = item.path
        # Sets may not link directly to the path of the print file, instead to .gjob, .stl
        # or other format where unpacking or transformation is needed to get to .gcode.
        try:
            path = item.resolve()
        except ResolveError as e:
            self._logger.error(e)
            self._msg(f"Could not resolve print path for {path}", type="error")
            return False
        except STLResolveError as e:
            self._logger.warning(e)
            return self._start_slicing(item, cb)

        try:
            self._logger.info(f"Selecting {path} (sd={item.sd})")
            self._printer.select_file(
                path, sd=item.sd, printAfterSelect=False, user=self._get_user()
            )
            return True
        except InvalidFileLocation as e:
            self._logger.error(e)
            self._msg("File not found: " + path, type="error")
            return False
        except InvalidFileType as e:
            self._logger.error(e)
            self._msg("File not gcode: " + path, type="error")
            return False

    def verify_active(self):
        # SpoolManager does its filament estimation based on the current active
        # gcode file (the "job" in OctoPrint parlance).
        # Failing this verification should put the queue in a "needs action" state and prevent printing the next file.
        if self._spool_manager is not None:
            ap = self._spool_manager.allowed_to_print()
            ap = dict(
                misconfig=ap.get("metaOrAttributesMissing", False),
                nospool=ap.get("result", {}).get("noSpoolSelected", []),
                notenough=ap.get("result", {}).get("filamentNotEnough", []),
            )
            valid = (
                not ap["misconfig"]
                and len(ap["nospool"]) == 0
                and len(ap["notenough"]) == 0
            )
            return valid, ap
        else:
            return True, None

    def run_script_for_event(self, evt, msg=None, msgtype=None):
        interp, out, err = getInterpreter(self._symbols)
        automation = getAutomationForEvent(evt)
        gcode = genEventScript(automation, interp, self._logger)
        if len(interp.error) > 0:
            for err in interp.error:
                self._logger.error(err.get_error())
                self._msg(
                    f"CPQ {evt.displayName} Preprocessor:\n{err.get_error()}",
                    type="error",
                )
            gcode = "@pause"  # Exceptions mean we must wait for the user to act
        else:
            err.seek(0)
            err_output = err.read().strip()
            if len(err_output) > 0:
                self._logger.error(err_output)
            out.seek(0)
            interp_output = out.read().strip()
            if len(interp_output) > 0:
                self._msg(f"CPQ {evt.displayName} Preprocessor:\n{interp_output}")
            else:
                self._do_msg(evt, running=(gcode != ""))

        if evt == CustomEvents.PRINT_CANCEL:
            # Cancellation happens before custom scripts are run
            self._printer.cancel_print()

        result = self._execute_gcode(evt, gcode) if gcode != "" else None

        # Bed cooldown turn-off happens after custom scripts are run
        if evt == CustomEvents.COOLDOWN:
            self._printer.set_temperature("bed", 0)  # turn bed off

        self._fire_event(evt)
        return result

    def _output_gcode_path(self, item):
        # Avoid splitting suffixes so that we can more easily
        # match against the item when checking if the print is finished
        name = str(Path(item.path).name) + ".gcode"
        return str(Path(TEMP_FILE_DIR) / name)

    def _cancel_any_slicing(self, item):
        slicer = self._get_key(Keys.SLICER)
        profile = self._get_key(Keys.SLICER_PROFILE)
        if item.sd or slicer == "" or profile == "":
            return False

        self._slicing_manager.cancel_slicing(
            slicer,
            item.path,
            self._output_gcode_path(item),
        )

    def _start_slicing(self, item, cb):
        # Cannot slice SD files, as they cannot be read (only written)
        # Similarly we can't slice if slicing is disabled or there is no
        # default slicer.
        slicer = self._get_key(Keys.SLICER)
        profile = self._get_key(Keys.SLICER_PROFILE)
        if item.sd or slicer == "" or profile == "":
            msg = f"Cannot slice item {item.path}, because:"
            if item.sd:
                msg += "\n* print file is on SD card"
            if slicer == "":
                msg += "\n* slicer not configured in CPQ settings"
            if profile == "":
                msg += "\n* slicer profile not configured in CPQ settings"
            self._logger.error(msg)
            self._msg(msg, type="error")
            return False

        gcode_path = self._file_manager.path_on_disk(
            FileDestinations.LOCAL, self._output_gcode_path(item)
        )
        msg = f"Slicing {item.path} using slicer {slicer} and profile {profile}; output to {gcode_path}"
        self._logger.info(msg)
        self._msg(msg)

        def slicer_cb(*args, **kwargs):
            if kwargs.get("_error") is not None:
                cb(success=False, error=kwargs["_error"])
                self._msg(
                    f"Slicing failed with error: {kwargs['_error']}", type="error"
                )
            elif kwargs.get("_cancelled"):
                cb(success=False, error=Exception("Slicing cancelled"))
                self._msg("Slicing was cancelled")
            else:
                item.resolve(gcode_path)  # override the resolve value
                cb(success=True, error=None)

        # We use _slicing_manager here instead of _file_manager to prevent FileAdded events
        # from causing additional queue activity.
        # Also fully resolve source and dest path as required by slicing manager
        try:
            self._slicing_manager.slice(
                slicer,
                self._file_manager.path_on_disk(FileDestinations.LOCAL, item.path),
                gcode_path,
                profile,
                callback=slicer_cb,
            )
        except SlicingException as e:
            self._logger.error(e)
            self._msg(self)
            return False
        return None  # "none" indicates upstream to wait for cb()

    def start_print(self, item):
        current_file = self._printer.get_current_job().get("file", {}).get("name")
        # A limitation of `octoprint.printer`, the "current file" path passed to the driver is only
        # the file name, not the full path to the file.
        # See https://docs.octoprint.org/en/master/modules/printer.html#octoprint.printer.PrinterCallback.on_printer_send_current_data
        resolved = item.resolve()
        if resolved.split("/")[-1] != current_file:
            raise Exception(
                f"File loaded is {current_file}, but attempting to print {resolved}"
            )

        self._msg(f"{item.job.name}: printing {item.path}")
        if self._spool_manager is not None:
            # SpoolManager has additional actions that are normally run in JS
            # before a print starts.
            # We must run startPrintConfirmed before starting a new print, or else
            # temperature offsets aren't applied.
            # See https://github.com/smartin015/continuousprint/issues/191
            self._spool_manager.start_print_confirmed()

        self._fire_event(CustomEvents.PRINT_START)
        self._printer.start_print()
        self._refresh_ui_state()
