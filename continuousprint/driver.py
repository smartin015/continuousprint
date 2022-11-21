import time
from multiprocessing import Lock
from enum import Enum, auto
from .data import CustomEvents


class Action(Enum):
    ACTIVATE = auto()
    DEACTIVATE = auto()
    SUCCESS = auto()
    FAILURE = auto()
    SPAGHETTI = auto()
    TICK = auto()


class Printer(Enum):
    IDLE = auto()
    PAUSED = auto()
    BUSY = auto()


class StatusType(Enum):
    NORMAL = auto()
    NEEDS_ACTION = auto()
    ERROR = auto()


# Inspired by answers at
# https://stackoverflow.com/questions/6108819/javascript-timestamp-to-relative-time
def timeAgo(elapsed):
    if elapsed < 60 * 60:
        return str(round(elapsed / (60))) + " minutes"
    elif elapsed < 60 * 60 * 24:
        return str(round(elapsed / (60 * 60))) + " hours"
    else:
        return str(round(elapsed / (60 * 60 * 24))) + " days"


class Driver:
    # If the printer is idle for this long while printing, break out of the printing state (consider it a failure)
    PRINTING_IDLE_BREAKOUT_SEC = 15.0

    def __init__(
        self,
        queue,
        script_runner,
        logger,
    ):
        self.mutex = Lock()
        self._logger = logger
        self.status = None
        self.status_type = StatusType.NORMAL
        self._set_status("Initializing")
        self.q = queue
        self.state = self._state_unknown
        self.last_printer_state = None
        self.printer_state_ts = 0
        self.printer_state_logs_suppressed = False
        self.retries = 0
        self.retry_on_pause = False
        self.max_retries = 0
        self.retry_threshold_seconds = 0
        self.max_startup_attempts = 3
        self.managed_cooldown = False
        self.cooldown_threshold = 0
        self.cooldown_timeout = 0
        self.first_print = True
        self._runner = script_runner
        self._update_ui = False
        self._cur_path = None
        self._cur_materials = []
        self._bed_temp = 0

    def action(
        self,
        a: Action,
        p: Printer,
        path: str = None,
        materials: list = [],
        bed_temp=None,
    ):
        # Given that some calls to action() come from a watchdog timer, we hold a mutex when performing the action
        # so the state is updated in a thread safe way.
        with self.mutex:
            now = time.time()
            if self.printer_state_ts + 15 > now or a != Action.TICK:
                self._logger.debug(
                    f"{a.name}, {p.name}, path={path}, materials={materials}, bed_temp={bed_temp}"
                )
            elif a == Action.TICK and not self.printer_state_logs_suppressed:
                self.printer_state_logs_suppressed = True
                self._logger.debug(
                    f"suppressing further debug logs for action=TICK, printer state={p.name}"
                )

            if p != self.last_printer_state:
                self.printer_state_ts = now
                self.last_printer_state = p
                self.printer_state_logs_suppressed = False

            if path is not None:
                self._cur_path = path
            if len(materials) > 0:
                self._cur_materials = materials
            if bed_temp is not None:
                self._bed_temp = bed_temp
            self._runner.set_current_symbols(
                dict(
                    path=self._cur_path,
                    materials=self._cur_materials,
                    bed_temp=self._bed_temp,
                )
            )

            # Deactivation must be allowed on all states, so we hande it here for
            # completeness.
            if a == Action.DEACTIVATE and self.state != self._state_inactive:
                nxt = self._enter_inactive()
            else:
                nxt = self.state(a, p)

            if nxt is not None:
                self._logger.info(f"{self.state.__name__} -> {nxt.__name__}")
                self.state = nxt
                self._update_ui = True

            if self._update_ui:
                self._update_ui = False
                return True
            return False

    def _state_unknown(self, a: Action, p: Printer):
        pass

    def _enter_inactive(self):
        self._runner.run_script_for_event(CustomEvents.DEACTIVATE)
        return self._state_inactive

    def _state_inactive(self, a: Action, p: Printer):
        self.q.release()
        self.retries = 0

        if a == Action.ACTIVATE:
            if self._runner.run_script_for_event(CustomEvents.ACTIVATE) is not None:
                return self._state_activating

            if p != Printer.IDLE:
                return self._state_printing
            else:
                return self._enter_start_print(a, p)

        if p == Printer.IDLE:
            self._set_status("Inactive (click Start Managing)")
        else:
            self._set_status(
                "Inactive (active print continues unmanaged)", StatusType.NEEDS_ACTION
            )

    def _state_activating(self, a: Action, p: Printer):
        self._set_status("Running startup script")
        if a == Action.SUCCESS or self._long_idle(p):
            return self._state_idle(a, p)

    def _state_idle(self, a: Action, p: Printer):
        self.q.release()

        item = self.q.get_set_or_acquire()
        if item is None:
            self._set_status("Idle (awaiting printable Job)")
        else:
            if p != Printer.IDLE:
                return self._state_printing
            else:
                return self._enter_start_print(a, p)

    def _state_preprint(self, a: Action, p: Printer):
        self._set_status("Running pre-print script")
        if a == Action.SUCCESS or self._long_idle(p):
            # Skip running the pre-print script this time
            return self._enter_start_print(a, p, run_pre_script=False)

    def _enter_start_print(self, a: Action, p: Printer, run_pre_script=True):
        if run_pre_script and self._runner.run_script_for_event(
            CustomEvents.PRINT_START
        ):
            return self._state_preprint

        # Pre-call start_print on entry to eliminate tick delay
        self.start_failures = 0
        nxt = self._state_start_print(a, p)
        return nxt if nxt is not None else self._state_start_print

    def _fmt_material_key(self, mk):
        try:
            s = mk.split("_")
            return f"{s[0]} ({s[1]})"
        except IndexError:
            return mk
        except AttributeError:
            return mk

    def _materials_match(self, item):
        for i, im in enumerate(item.materials()):
            if im is None:  # No constraint
                continue
            cur = self._cur_materials[i] if i < len(self._cur_materials) else None
            if im != cur:
                return False
        return True

    def _state_awaiting_material(self, a: Action, p: Printer):
        item = self.q.get_set_or_acquire()
        if item is None:
            self._set_status("No work to do; going idle")
            return self._state_idle

        if self._materials_match(item):
            return self._enter_start_print(a, p)
        else:
            self._set_status(
                f"Need {self._fmt_material_key(im)} in tool {i}, but {self._fmt_material_key(cur)} is loaded",
                StatusType.NEEDS_ACTION,
            )

    def _state_start_print(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        item = self.q.get_set_or_acquire()
        if item is None:
            self._set_status("No work to do; going idle")
            return self._state_idle

        if not self._materials_match(item):
            self._runner.run_script_for_event(CustomEvents.AWAITING_MATERIAL)
            return self._state_awaiting_material

        self.q.begin_run()
        if self._runner.start_print(item):
            return self._state_printing
        else:
            # TODO bail out of the job and mark it as bad rather than dropping into inactive state
            self.start_failures += 1
            if self.start_failures >= self.max_startup_attempts:
                self._set_status("Failed to start; too many attempts", StatusType.ERROR)
                return self._enter_inactive()
            else:
                self._set_status(
                    f"Start attempt failed ({self.start_failures}/{self.max_startup_attempts})",
                    StatusType.ERROR,
                )

    def _long_idle(self, p):
        # We wait until we're in idle state for a long-ish period before acting, as
        # IDLE can be returned as a state before another event-based action (e.g. SUCCESS)
        return (
            p == Printer.IDLE
            and time.time() - self.printer_state_ts > self.PRINTING_IDLE_BREAKOUT_SEC
        )

    def _state_printing(self, a: Action, p: Printer, elapsed=None):
        if a == Action.FAILURE:
            return self._state_failure
        elif a == Action.SPAGHETTI:
            run = self.q.get_run()
            elapsed = time.time() - run.start.timestamp()
            if self.retry_on_pause and elapsed < self.retry_threshold_seconds:
                return self._state_spaghetti_recovery
            else:
                self._set_status(
                    f"Paused after {timeAgo(elapsed)} (>{timeAgo(self.retry_threshold_seconds)}); awaiting user",
                    StatusType.NEEDS_ACTION,
                )
                return self._state_paused
        elif a == Action.SUCCESS or self._long_idle(p):
            # If idle state without event, assume we somehow missed the SUCCESS action.
            # We wait for a period of idleness to prevent idle-before-success events
            # from double-completing prints.
            item = self.q.get_set()

            # A limitation of `octoprint.printer`, the "current file" path passed to the driver is only
            # the file name, not the full path to the file.
            # See https://docs.octoprint.org/en/master/modules/printer.html#octoprint.printer.PrinterCallback.on_printer_send_current_data
            if item.path.split("/")[-1] == self._cur_path:
                return self._state_success
            else:
                self._logger.info(
                    f"Completed print {self._cur_path} not matching current queue item {item.path} - clearing it in prep to start queue item"
                )
                return self._state_start_clearing

        if p == Printer.BUSY:
            item = self.q.get_set()
            if item is not None:
                self._set_status("Printing")
            else:
                self._set_status("Waiting for printer to be ready")
        elif p == Printer.PAUSED:
            return self._state_paused

    def _state_paused(self, a: Action, p: Printer):
        self._set_status("Paused", StatusType.NEEDS_ACTION)
        if self._long_idle(p):
            # Here, IDLE implies the user cancelled the print.
            # Go inactive to prevent stomping on manual changes
            return self._enter_inactive()
        elif p == Printer.BUSY:
            return self._state_printing

    def _state_spaghetti_recovery(self, a: Action, p: Printer):
        self._set_status("Cancelling (spaghetti early in print)", StatusType.ERROR)
        if p == Printer.PAUSED:
            self._runner.run_script_for_event(CustomEvents.PRINT_CANCEL)
            return self._state_failure

    def _state_failure(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            return

        if self.retries + 1 < self.max_retries:
            self.retries += 1
            return self._state_start_clearing
        else:
            self.q.end_run("failure")
            self._set_status("Failure (max retries exceeded", StatusType.ERROR)
            return self._enter_inactive()

    def _state_success(self, a: Action, p: Printer):
        # Complete prior queue item if that's what we just finished.
        # Note that end_run fails silently if there's no active run
        # (e.g. if we start managing mid-print)
        self.q.end_run("success")
        self.retries = 0

        # Clear bed if we have a next queue item, otherwise run finishing script
        item = self.q.get_set_or_acquire()
        if item is not None:
            self._logger.debug(
                f'_state_success next item "{item.path}" (remaining={item.remaining}, job remaining={item.job.remaining}) --> _start_clearing'
            )
            return self._state_start_clearing
        else:
            self._logger.debug("_state_success no next item --> _start_finishing")
            return self._state_start_finishing

    def _state_start_clearing(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        if self.managed_cooldown:
            self._runner.run_script_for_event(CustomEvents.COOLDOWN)
            self.cooldown_start = time.time()
            self._logger.info(
                f"Cooldown initiated (threshold={self.cooldown_threshold}, timeout={self.cooldown_timeout})"
            )
            return self._state_cooldown
        else:
            self._runner.run_script_for_event(CustomEvents.PRINT_SUCCESS)
            return self._state_clearing

    def _state_cooldown(self, a: Action, p: Printer):
        clear = False
        if self._bed_temp < self.cooldown_threshold:
            self._logger.info(
                f"Cooldown threshold of {self.cooldown_threshold} has been met"
            )
            clear = True
        elif (time.time() - self.cooldown_start) > (60 * self.cooldown_timeout):
            self._logger.info(f"Timeout of {self.cooldown_timeout} minutes exceeded")
            clear = True
        else:
            self._set_status("Cooling down")

        if clear:
            self._runner.run_script_for_event(CustomEvents.PRINT_SUCCESS)
            return self._state_clearing

    def _state_clearing(self, a: Action, p: Printer):
        if a == Action.SUCCESS:
            return self._enter_start_print(a, p)
        elif a == Action.FAILURE:
            self._set_status("Error when clearing bed - aborting", StatusType.ERROR)
            return self._enter_inactive()  # Skip past failure state to inactive

        if self._long_idle(p):  # Idle state without event; assume success
            return self._enter_start_print(a, p)
        else:
            self._set_status("Clearing bed")

    def _state_start_finishing(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        self._runner.run_script_for_event(CustomEvents.FINISH)
        return self._state_finishing

    def _state_finishing(self, a: Action, p: Printer):
        if a == Action.FAILURE:
            return self._enter_inactive()

        # Idle state without event -> assume success and go idle
        if a == Action.SUCCESS or self._long_idle(p):
            return self._state_idle

        self._set_status("Finishing up")

    def _set_status(self, status, status_type=StatusType.NORMAL):
        if status != self.status:
            self._update_ui = True
            self.status = status
            self.status_type = status_type
            self._logger.info(status)

    def set_managed_cooldown(self, enabled, threshold, timeout):
        self.managed_cooldown = enabled
        self.cooldown_threshold = threshold
        self.cooldown_timeout = timeout
        self._logger.debug(
            f"Managed cooldown: {enabled} (threshold {threshold}C, timeout {timeout}min)"
        )

    def set_retry_on_pause(
        self, enabled, max_retries=3, retry_threshold_seconds=60 * 60
    ):
        self.retry_on_pause = enabled
        self.max_retries = max_retries
        self.retry_threshold_seconds = retry_threshold_seconds
        self._logger.debug(
            f"Retry on pause: {enabled} (max_retries {max_retries}, threshold {retry_threshold_seconds}s)"
        )

    def current_path(self):
        item = self.q.get_set()
        return None if item is None else item.path
