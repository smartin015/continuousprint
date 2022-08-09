from octoprint.filemanager.analysis import AbstractAnalysisQueue, AnalysisAborted
from octoprint.util.platform import CLOSE_FDS
from octoprint.util import dict_merge


class CPQProfileAnalysisQueue(AbstractAnalysisQueue):
    """This queue attempts to resolve the profiles for which a gcode has been created."""

    META_KEY = "continuousprint"
    PROFILE_KEY = "profile"

    def __init__(self, finished_callback):
        AbstractAnalysisQueue.__init__(self, finished_callback)

        self._aborted = False
        self._reenqueue = False

    def _do_analysis(self, high_priority=False):
        import sys
        import sarge

        if self._current.analysis and self._current.analysis.get(self.PROFILE_KEY):
            return self._current.analysis

        try:
            command = [
                sys.executable,
                "-m",
                "continuousprint.scripts.extract_profile",
            ]
            command.append(self._current.absolute_path)
            self._logger.info("Invoking analysis command: {}".format(" ".join(command)))
            self._aborted = False
            p = sarge.run(
                command, close_fds=CLOSE_FDS, async_=True, stdout=sarge.Capture()
            )

            while len(p.commands) == 0:
                time.sleep(0.01)
            p.commands[0].process_ready.wait()

            if not p.commands[0].process:
                raise RuntimeError(
                    "Error while trying to run command {}".format(" ".join(command))
                )

            try:
                while p.returncode is None:
                    if self._aborted:
                        p.commands[0].terminate()
                        raise AnalysisAborted(reenqueue=self._reenqueue)
                    p.commands[0].poll()
            finally:
                p.close()

            output = p.stdout.text
            self._logger.info(f"Got output: {output!r}")

            result = {}
            result["profile"] = output.strip()

            if self._current.analysis and isinstance(self._current.analysis, dict):
                return dict_merge(result, self._current.analysis)
            else:
                return result
        finally:
            self._gcode = None

    def _do_abort(self, reenqueue=True):
        self._aborted = True
        self._reenqueue = reenqueue
