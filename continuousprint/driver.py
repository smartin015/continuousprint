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
        supervisor,
        script_runner,
        logger,
    ):
        self._logger = logger
        self.status = None
        self._set_status("Initializing")
        self.s = supervisor
        self.state = self._state_unknown
        self.retries = 0
        self.retry_on_pause = False
        self.max_retries = 0
        self.retry_threshold_seconds = 0
        self.first_print = True
        self._runner = script_runner
        self._intent = None  # Intended file path
        self._update_ui = False
        self._cur_path = None
        self._cur_materials = []

    def action(self, a: Action, p: Printer, path: str = None, materials: list = []):
        self._logger.debug(f"{a.name}, {p.name}, path={path}, materials={materials}")
        if path is not None:
            self._cur_path = path
        if len(materials) > 0:
            self._cur_materials = materials
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
        if a == Action.DEACTIVATE:
            return self._state_inactive

    def _state_inactive(self, a: Action, p: Printer):
        self.retries = 0

        if a == Action.ACTIVATE:
            if p != Printer.IDLE:
                return self._state_printing
            else:
                # TODO "clear bed on startup" setting
                return self._state_start_print

        if p == Printer.IDLE:
            self._set_status("Inactive (click Start Managing)")
        else:
            self._set_status("Inactive (active print continues unmanaged)")

    def _state_start_print(self, a: Action, p: Printer):
        if a == Action.DEACTIVATE:
            return self._state_inactive

        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        item = self.s.get_assignment()
        if item is None:
            return self._state_inactive

        # Block until we have the right materials loaded (if required)
        for i, im in enumerate(item.materials):
            if im is None:  # No constraint
                continue
            cur = self._cur_materials[i] if i < len(self._cur_materials) else None
            if im != cur:
                self._set_status(
                    f"Waiting for spool {im} in tool {i} (currently: {cur})"
                )
                return

        path = self.s.begin_assignment()
        self._runner.start_print(p)
        return self._state_printing

    def _state_printing(self, a: Action, p: Printer, elapsed=None):
        if a == Action.DEACTIVATE:
            return self._state_inactive
        elif a == Action.FAILURE:
            return self._state_failure
        elif a == Action.SPAGHETTI:
            elapsed = self.s.elapsed()
            if self.retry_on_pause and elapsed < self.retry_threshold_seconds:
                return self._state_spaghetti_recovery
            else:
                self._set_status(
                    f"Print paused {timeAgo(elapsed)} into print (over auto-restart threshold of {timeAgo(self.retry_threshold_seconds)}); awaiting user input"
                )
                return self._state_paused
        elif a == Action.SUCCESS:
            return self._state_success

        if p == Printer.BUSY:
            item = self.s.get_assignment()
            if item is not None:
                self._set_status(f"Printing {item.path}")
        elif p == Printer.PAUSED:
            return self._state_paused
        elif p == Printer.IDLE:  # Idle state without event; assume success
            return self._state_success

    def _state_paused(self, a: Action, p: Printer):
        self._set_status("Queue paused")
        if a == Action.DEACTIVATE or p == Printer.IDLE:
            return self._state_inactive
        elif p == Printer.BUSY:
            return self._state_printing

    def _state_spaghetti_recovery(self, a: Action, p: Printer):
        self._set_status("Cancelling print (spaghetti seen early in print)")
        if p == Printer.PAUSED:
            self._runner.cancel_print()
            self._intent = None
            return self._state_failure

    def _state_failure(self, a: Action, p: Printer):
        if p != Printer.IDLE:
            return

        if self.retries + 1 < self.max_retries:
            self.retries += 1
            return self._state_start_clearing
        else:
            self.s.end_assignment("failure")
            return self._state_inactive

    def _state_success(self, a: Action, p: Printer):
        item = self.s.get_assignment()

        # Complete prior queue item if that's what we just finished
        if item is not None:
            if self._intent == item.path and self._cur_path == item.path:
                self.s.end_assignment("success")
            else:
                self._logger.info(
                    f"Current queue item {path} not matching intent {self._intent}, current path {self._cur_path} - no completion"
                )
        self.retries = 0

        # Clear bed if we have a next queue item, otherwise run finishing script
        item = self.s.get_assignment()
        if item is not None:
            return self._state_start_clearing
        else:
            return self._state_start_finishing

    def _state_start_clearing(self, a: Action, p: Printer):
        if a == Action.DEACTIVATE:
            return self._state_inactive
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        self._intent = self._runner.clear_bed()
        return self._state_clearing

    def _state_clearing(self, a: Action, p: Printer):
        if a == Action.DEACTIVATE:
            return self._state_inactive
        if p != Printer.IDLE:
            return

        self._set_status("Clearing bed")
        return self._state_start_print

    def _state_start_finishing(self, a: Action, p: Printer):
        if a == Action.DEACTIVATE:
            return self._state_inactive
        if p != Printer.IDLE:
            self._set_status("Waiting for printer to be ready")
            return

        self._intent = self._runner.run_finish_script()
        return self._state_finishing

    def _state_finishing(self, a: Action, p: Printer):
        if a == Action.DEACTIVATE:
            return self._state_inactive
        if p != Printer.IDLE:
            return

        self._set_status("Finising up")

        return self._state_inactive

    def _set_status(self, status):
        if status != self.status:
            self._update_ui = True
            self.status = status
            self._logger.info(status)

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
        item = self.s.get_assignment()
        return None if item is None else item.path
