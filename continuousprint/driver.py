import time


# Inspired by answers at
# https://stackoverflow.com/questions/6108819/javascript-timestamp-to-relative-time
def timeAgo(elapsed):
    if elapsed < 60 * 60:
        return str(round(elapsed / (60))) + " minutes"
    elif elapsed < 60 * 60 * 24:
        return str(round(elapsed / (60 * 60))) + " hours"
    else:
        return str(round(elapsed / (60 * 60 * 24))) + " days"


class ContinuousPrintDriver:
    def __init__(
        self,
        queue,
        finish_script_fn,
        clear_bed_fn,
        start_print_fn,
        cancel_print_fn,
        logger,
    ):
        self.q = queue
        self.active = False
        self.retries = 0
        self._logger = logger
        self.retry_on_pause = False
        self.max_retries = 0
        self.retry_threshold_seconds = 0
        self.first_print = True
        self.actions = []

        self.finish_script_fn = finish_script_fn
        self.clear_bed_fn = clear_bed_fn
        self.start_print_fn = start_print_fn
        self.cancel_print_fn = cancel_print_fn
        self._set_status("Initialized (click Start Managing to run the queue)")

    def _set_status(self, status):
        self.status = status
        self._logger.info(status)

    def set_retry_on_pause(
        self, enabled, max_retries=3, retry_threshold_seconds=60 * 60
    ):
        self.retry_on_pause = enabled
        self.max_retries = max_retries
        self.retry_threshold_seconds = retry_threshold_seconds
        self._logger.info(
            f"Retry on pause: {enabled} (max_retries {max_retries}, threshold {retry_threshold_seconds}s)"
        )

    def set_active(self, active=True, printer_ready=True):
        if active and not self.active:
            self.active = True
            self.first_print = True
            self.retries = 0
            if not printer_ready:
                self._set_status("Waiting for printer to be ready")
            else:
                self._begin_next_available_print()
                self.on_printer_ready()
        elif self.active and not active:
            self.active = False
            if not printer_ready:
                self._set_status("Inactive (active prints continue unmanaged)")
            else:
                self._set_status("Inactive (ready - click Start Managing)")

    def _cur_idx(self):
        for (i, item) in enumerate(self.q):
            if item.start_ts is not None and item.end_ts is None:
                return i
        return None

    def current_path(self):
        idx = self._cur_idx()
        return None if idx is None else self.q[idx].name

    def _next_available_idx(self):
        for (i, item) in enumerate(self.q):
            if item.end_ts is None:
                return i
        return None

    def _begin_next_available_print(self):
        # The next print may not be the *immediately* next print
        # e.g. if we skip over a print or start mid-print
        idx = self._next_available_idx()
        if idx is not None:
            p = self.q[idx]
            p.start_ts = int(time.time())
            p.end_ts = None
            p.retries = self.retries
            self.q[idx] = p
            if not self.first_print:
                self.actions.append(self._clear_bed)
            self.actions.append(lambda: self._start_print(p))
            self.first_print = False
        else:
            self.actions.append(self._finish)

    def _finish(self):
        self._set_status("Running finish script")
        self.finish_script_fn()

    def _clear_bed(self):
        self._set_status("Running bed clearing script")
        self.clear_bed_fn()

    def _start_print(self, p):
        if self.retries > 0:
            self._set_status(
                f"Printing {p.name} (attempt {self.retries+1}/{self.max_retries})"
            )
        else:
            self._set_status(f"Printing {p.name}")
        self.start_print_fn(p)

    def _complete_item(self, idx, result):
        item = self.q[idx]
        item.end_ts = int(time.time())
        item.result = result
        self.q[idx] = item  # TODO necessary?

    def pending_actions(self):
        return len(self.actions)

    def on_printer_ready(self):
        if len(self.actions) > 0:
            a = self.actions.pop(0)
            self._logger.info("Printer ready; performing next action %s" % a.__repr__())
            a()
            return True
        else:
            return False

    def on_print_success(self, is_finish_script=False):
        if not self.active:
            return

        idx = self._cur_idx()
        if idx is not None:
            self._complete_item(idx, "success")

        self.retries = 0

        if is_finish_script:
            self.set_active(False)
        else:
            self.actions.append(self._begin_next_available_print)

    def on_print_failed(self):
        if not self.active:
            return
        self._complete_item(self._cur_idx(), "failure")
        self.active = False
        self._set_status("Inactive (print failed)")
        self.first_print = True

    def on_print_cancelled(self):
        self.first_print = True
        if not self.active:
            return
        idx = self._cur_idx()
        if self.retries + 1 < self.max_retries:
            self.retries += 1
            self.actions.append(
                self._begin_next_available_print
            )  # same print, not finished
        else:
            self._complete_item(idx, "failure (max retries)")
            self.active = False
            self._set_status("Inactive (print cancelled with too many retries)")

    def on_print_paused(self, elapsed=None, is_temp_file=False, is_spaghetti=False):
        if (
            not self.active
            or not self.retry_on_pause
            or is_temp_file
            or not is_spaghetti
        ):
            self._set_status("Print paused")
            return

        elapsed = elapsed or (time.time() - self.q[self._cur_idx()].start_ts)
        if elapsed < self.retry_threshold_seconds:
            self._set_status(
                "Cancelling print (spaghetti detected {timeAgo(elapsed)} into print)"
            )
            self.cancel_print_fn()
            # self.actions.append(self.cancel_print_fn)
        else:
            self._set_status(
                f"Print paused {timeAgo(elapsed)} into print (over auto-restart threshold of {timeAgo(self.retry_threshold_seconds)}); awaiting user input"
            )

    def on_print_resumed(self):
        # This happens after pause & manual resume
        idx = self._cur_idx()
        if idx is not None:
            self._set_status(f"Printing {self.q[idx].name}")
