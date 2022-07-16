import time
from enum import Enum, auto


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
    def __init__(
        self,
        queue,
        script_runner,
        logger,
    ):
        self._logger = logger
        self.status = None
        self.status_type = StatusType.NORMAL
        self._set_status("Initializing")
        self.q = queue
        self.state = self._state_unknown
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

    def action(
        self,
        a: Action,
        p: Printer,
        path: str = None,
        materials: list = [],
        bed_temp=None,
    ):
        self._logger.debug(f"{a.name}, {p.name}, path={path}, materials={materials}")
        if path is not None:
            self._cur_path = path
        if len(materials) > 0:
            self._cur_materials = materials
        if bed_temp is not None:
            self._bed_temp = bed_temp

        # Deactivation must be allowed on all states, so we hande it here for
        # completeness.
        if a == Action.DEACTIVATE and self.state != self._state_inactive:
            nxt = self._state_inactive
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

    def _state_inactive(self, a: Action, p: Printer):
        self.q.release()
        self.retries = 0

        if a == Action.ACTIVATE:
            if p != Printer.IDLE:
                return self._state_printing
            else:
                return self._enter_start_print(a, p)

        if p == Printer.IDLE:
            self._set_status("Inactive (click Start Managing)")
        else:
            self._set_status("Inactive (active print continues unmanaged)")

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

    def _enter_start_print(self, a: Action, p: Printer):
        # TODO "clear bed on startup" setting

        # Pre-call start_print on entry to eliminate tick delay
        self.start_failures = 0
        nxt = self._state_start_print(a, p)
        return nxt if nxt is not None else self._state_start_print

    def _state_start_print(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        item = self.q.get_set_or_acquire()
        if item is None:
            self._set_status("No work to do; going idle")
            return self._state_idle

        # Block until we have the right materials loaded (if required)
        for i, im in enumerate(item.materials()):
            if im is None:  # No constraint
                continue
            cur = self._cur_materials[i] if i < len(self._cur_materials) else None
            if im != cur:
                self._set_status(
                    f"Waiting for spool {im} in tool {i} (currently: {cur})",
                    StatusType.NEEDS_ACTION,
                )
                return

        self.q.begin_run()
        if self._runner.start_print(item):
            return self._state_printing
        else:
            # TODO bail out of the job and mark it as bad rather than dropping into inactive state
            self.start_failures += 1
            if self.start_failures >= self.max_startup_attempts:
                self._set_status("Failed to start; too many attempts", StatusType.ERROR)
                return self._state_inactive
            else:
                self._set_status(
                    f"Start attempt failed ({self.start_failures}/{self.max_startup_attempts})",
                    StatusType.ERROR,
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
        elif a == Action.SUCCESS:
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
        elif p == Printer.IDLE:  # Idle state without event; assume success
            return self._state_success

    def _state_paused(self, a: Action, p: Printer):
        self._set_status("Paused", StatusType.NEEDS_ACTION)
        if p == Printer.IDLE:
            # Here, IDLE implies the user cancelled the print.
            # Go inactive to prevent stomping on manual changes
            return self._state_inactive
        elif p == Printer.BUSY:
            return self._state_printing

    def _state_spaghetti_recovery(self, a: Action, p: Printer):
        self._set_status("Cancelling (spaghetti early in print)", StatusType.ERROR)
        if p == Printer.PAUSED:
            self._runner.cancel_print()
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
            return self._state_inactive

    def _state_success(self, a: Action, p: Printer):
        # Complete prior queue item if that's what we just finished.
        # Note that end_run fails silently if there's no active run
        # (e.g. if we start managing mid-print)
        self.q.end_run("success")
        self.retries = 0

        # Clear bed if we have a next queue item, otherwise run finishing script
        item = self.q.get_set_or_acquire()
        if item is not None:
            return self._state_start_clearing
        else:
            return self._state_start_finishing

    def _state_start_clearing(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        if self.managed_cooldown:
            self._runner.start_cooldown()
            self.cooldown_start = time.time()
            self._logger.info(
                f"Cooldown initiated (threshold={self.cooldown_threshold}, timeout={self.cooldown_timeout})"
            )
            return self._state_cooldown
        else:
            self._runner.clear_bed()
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
            self._runner.clear_bed()
            return self._state_clearing

    def _state_clearing(self, a: Action, p: Printer):
        if a == Action.SUCCESS:
            return self._enter_start_print(a, p)
        elif a == Action.FAILURE:
            self._set_status("Error when clearing bed - aborting", StatusType.ERROR)
            return self._state_inactive  # Skip past failure state to inactive

        if p == Printer.IDLE:  # Idle state without event; assume success
            return self._enter_start_print(a, p)
        else:
            self._set_status("Clearing bed")

    def _state_start_finishing(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        self._runner.run_finish_script()
        return self._state_finishing

    def _state_finishing(self, a: Action, p: Printer):
        if a == Action.FAILURE:
            return self._state_inactive

        # Idle state without event -> assume success and go idle
        if a == Action.SUCCESS or p == Printer.IDLE:
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
