import time

class ContinuousPrintDriver:

    def __init__(self, queue, bed_clear_script_fn, finish_script_fn, start_print_fn, cancel_print_fn, logger):
        self.q = queue
        self.active = False
        self.cur_idx = None
        self.retries = 0
        self._logger = logger

        # TODO make configurable
        self.MAX_RETRIES = 3
        self.RETRY_THRESHOLD_SECONDS = 60*60

        self.bed_clear_script_fn = bed_clear_script_fn
        self.finish_script_fn = finish_script_fn
        self.start_print_fn = start_print_fn
        self.cancel_print_fn = cancel_print_fn
        self._set_status("Initialized")

    def _set_status(self, status):
        self.status = status
        self._logger.info(status)

    def set_active(self, active=True, printer_ready=True):
        if active and not self.active:
            self.active = True
            if not printer_ready:
                self._set_status("Waiting for printer to be ready")
            else:
                self._begin_next_available_print()
        elif self.active and not active:
            self.active = False
            if not printer_ready:
                self._set_status("Inactive (waiting for printer to be ready)")
            else:
                self._set_status("Inactive (ready)")

    def _next_available_idx(self):
        for (i, item) in enumerate(self.q):
            if item.end_ts is None:
                return i
        return None


    def _begin_next_available_print(self):
        self.bed_clear_script_fn()
        # The next print may not be the *immediately* next print
        # e.g. if we skip over a print or start mid-print 
        nxt = self._next_available_idx()
        if nxt is not None: 
            self.cur_idx = nxt

            p = self.q[self.cur_idx]
            p.start_ts = int(time.time())
            self.q[self.cur_idx] = p

            self.start_print_fn(p)
            if self.retries > 0:
                self._set_status(f"Printing {p.name} (attempt {self.retries+1}/{self.MAX_RETRIES})")
            else: 
                self._set_status(f"Printing {p.name}")
        else:
            self.active = False
            self._set_status("Inactive (no new work available)")
            self.finish_script_fn()


    def _complete_cur_item(self, result):
        item = self.q[self.cur_idx]    
        item.end_ts = int(time.time())
        item.result = result
        self.q[self.cur_idx] = item # TODO necessary?

    def on_print_success(self):
        if not self.active:
            return

        if self.cur_idx is not None:
            self._complete_cur_item("success")

        self.retries = 0
        self._begin_next_available_print()


    def on_print_failed(self):
        if not self.active:
            return
        self._complete_cur_item("failure")
        self.active = False
        self._set_status("Inactive (print failed)")

    def on_print_cancelled(self):
        if not self.active:
            return
        item = self.q[self.cur_idx]    
        if self.retries < self.MAX_RETRIES:
            self.retries += 1
            self._begin_next_available_print() # same print, not finished
        else:
            self._complete_cur_item("aborted (max retries)")
            self.active = False
            self._set_status("Inactive (print cancelled with too many retries)")

    def on_print_paused(self, elapsed = None):
        if not self.active:
            return

        elapsed = elapsed or (time.time() - self.q[self.cur_idx].start_ts)
        if elapsed < self.RETRY_THRESHOLD_SECONDS:
            self._set_status("Cancelling print (paused early, likely adhesion failure)")
            self.cancel_print_fn()
        else:
            # TODO humanize
            self._set_status("Print paused {elapsed}s into print (over auto-restart threshold of {self.RETRY_THRESHOLD_SECONDS}s); awaiting user input")

    def on_print_resumed(self):
        pass # TODO this could happen after pause & manual resume

