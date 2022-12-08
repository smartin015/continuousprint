import unittest
from pathlib import Path
from collections import namedtuple
from .analysis import CPQProfileAnalysisQueue
from .storage.queries import getJobsAndSets
from .storage.database import DEFAULT_QUEUE, ARCHIVE_QUEUE
from unittest.mock import MagicMock, patch, ANY, call
from octoprint.filemanager.analysis import QueueEntry
from .driver import Action as DA
from octoprint.events import Events
import logging
import tempfile
import json
from .data import Keys, TEMP_FILE_DIR
from .plugin import CPQPlugin

# logging.basicConfig(level=logging.DEBUG)


class MockSettings:
    def __init__(self):
        self.s = dict()

    def save(self):
        pass

    def get(self, k):
        return self.s.get(k[0])

    def global_get(self, gk):
        return self.get([":".join(gk)])

    def set(self, k, v):
        self.s[k[0]] = v

    def global_set(self, gk, v):
        return self.set([":".join(gk)], v)


def mockplugin():
    return CPQPlugin(
        printer=MagicMock(),
        settings=MockSettings(),
        file_manager=MagicMock(),
        slicing_manager=MagicMock(),
        plugin_manager=MagicMock(),
        fire_event=MagicMock(),
        queries=MagicMock(),
        data_folder=None,
        logger=logging.getLogger(),
        identifier=None,
        basefolder=None,
    )


class TestStartup(unittest.TestCase):
    def testThirdPartyMissing(self):
        p = mockplugin()
        p._plugin_manager.plugins.get.return_value = None

        p._setup_thirdparty_plugin_integration()

        self.assertEqual(p._get_key(Keys.MATERIAL_SELECTION), False)  # Spoolmanager
        self.assertEqual(p._get_key(Keys.RESTART_ON_PAUSE), False)  # Obico

    def testObicoFound(self):
        p = mockplugin()
        p._plugin_manager.plugins.get.return_value = None

        with patch(
            "octoprint.events.Events.PLUGIN_OBICO_COMMAND", "obico_command", create=True
        ):
            p._setup_thirdparty_plugin_integration()

        self.assertEqual(p._get_key(Keys.MATERIAL_SELECTION), False)  # Spoolmanager
        self.assertEqual(p._get_key(Keys.RESTART_ON_PAUSE), True)  # Obico

    def testSpoolManagerFound(self):
        p = mockplugin()
        p._plugin_manager.plugins.get.return_value = MagicMock()

        p._setup_thirdparty_plugin_integration()

        p._plugin_manager.plugins.get.assert_called_with("SpoolManager")
        self.assertEqual(p._get_key(Keys.MATERIAL_SELECTION), True)  # Spoolmanager
        self.assertEqual(p._get_key(Keys.RESTART_ON_PAUSE), False)  # Obico

    def testDBNew(self):
        p = mockplugin()
        with tempfile.TemporaryDirectory() as td:
            p._data_folder = td
            p._init_db()

    @patch("continuousprint.plugin.migrateScriptsFromSettings")
    def testDBMigrateScripts(self, msfs):
        p = mockplugin()
        p._set_key(Keys.CLEARING_SCRIPT_DEPRECATED, "s1")
        p._set_key(Keys.FINISHED_SCRIPT_DEPRECATED, "s2")
        p._set_key(Keys.BED_COOLDOWN_SCRIPT_DEPRECATED, "s3")
        with tempfile.TemporaryDirectory() as td:
            p._data_folder = td
            p._init_db()
            # Ensure we're calling with the script body, not just the event name
            msfs.assert_called_with("s1", "s2", "s3")

    def testDBWithLegacySettings(self):
        p = mockplugin()
        p._set_key(
            Keys.QUEUE_DEPRECATED,
            json.dumps(
                [
                    {
                        "name": "sample-cube-026.gcode",
                        "path": "sample-cube-026.gcode",
                        "sd": "false",
                        "job": "",
                        "materials": [],
                        "run": 0,
                        "start_ts": 1652377632,
                        "end_ts": 1652381175,
                        "result": "success",
                        "retries": 2,
                    }
                ]
            ),
        )
        with tempfile.TemporaryDirectory() as td:
            p._data_folder = td
            p._init_db()
            self.assertEqual(len(getJobsAndSets(DEFAULT_QUEUE)), 1)

    def testFileshare(self):
        p = mockplugin()
        fs = MagicMock()
        p.get_local_addr = lambda: ("111.111.111.111:0")
        p._file_manager.path_on_disk.return_value = "/testpath"

        p._init_fileshare(fs_cls=fs)

        fs.assert_called_with("111.111.111.111:0", "/testpath", logging.getLogger())

    def testFileshareAddrFailure(self):
        p = mockplugin()
        fs = MagicMock()
        p.get_local_addr = MagicMock(side_effect=[OSError("testing")])
        p._init_fileshare(fs_cls=fs)  # Does not raise exception
        self.assertEqual(p._fileshare, None)

    def testFileshareConnectFailure(self):
        p = mockplugin()
        fs = MagicMock()
        p.get_local_addr = lambda: "111.111.111.111:0"
        fs.connect.side_effect = OSError("testing")
        p._init_fileshare(fs_cls=fs)  # Does not raise exception
        self.assertEqual(p._fileshare, fs())

    def testQueues(self):
        p = mockplugin()
        QT = namedtuple("MockQueue", ["name", "addr"])
        p._queries.getQueues.return_value = [
            QT(name="LAN", addr="0.0.0.0:0"),
            QT(name=DEFAULT_QUEUE, addr=None),
            QT(name=ARCHIVE_QUEUE, addr=None),
        ]
        p._fileshare = None
        p._init_queues(lancls=MagicMock(), localcls=MagicMock())
        self.assertEqual(len(p.q.queues), 2)  # 2 queues created, archive skipped

    def testDriver(self):
        p = mockplugin()
        p.q = MagicMock()
        p._sync_state = MagicMock()
        p._printer_profile = None
        p._spool_manager = None

        p._init_driver(srcls=MagicMock(), dcls=MagicMock())
        self.assertNotEqual(p.d, None)


class TestEventHandling(unittest.TestCase):
    def setUp(self):
        self.p = mockplugin()
        self.p._spool_manager = None
        self.p._printer_profile = None
        self.p.d = MagicMock()
        self.p.q = MagicMock()
        self.p._sync_state = MagicMock()
        self.p._setup_thirdparty_plugin_integration()
        self.p._octoprint_version_exceeds = lambda a, b: False

    def testTick(self):
        self.p.tick()
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY, ANY, ANY)

    def testTickExceptionHandled(self):
        self.p.d.action.side_effect = Exception(
            "testing exception - ignore this, part of a unit test"
        )
        self.p.tick()  # does *not* raise exception
        self.p.d.action.assert_called()

    def testMetadataAnalysisFinishedNonePending(self):
        self.p._set_key(Keys.INFER_PROFILE, True)
        self.p.on_event(
            Events.METADATA_ANALYSIS_FINISHED,
            dict(result={CPQProfileAnalysisQueue.PROFILE_KEY: "asdf"}, path="a.gcode"),
        )
        self.p._get_queue(DEFAULT_QUEUE).add_set.assert_not_called()

    def testMetadataAnalysisFinishedWithPending(self):
        self.p._set_key(Keys.INFER_PROFILE, True)
        self.p._file_manager.get_additional_metadata.return_value = dict()
        self.p._add_set(path="a.gcode", sd=False)  # Gets queued, no metadata
        self.p._get_queue(DEFAULT_QUEUE).add_set.assert_not_called()
        self.p.on_event(
            CPQPlugin.CPQ_ANALYSIS_FINISHED,
            dict(result={CPQProfileAnalysisQueue.PROFILE_KEY: "asdf"}, path="a.gcode"),
        )
        self.p._get_queue(DEFAULT_QUEUE).add_set.assert_called_with(
            "",
            {
                "path": "a.gcode",
                "sd": "false",
                "count": 1,
                "jobDraft": True,
                "profiles": ["asdf"],
            },
        )

    def testAddSetWithPending(self):
        self.p._set_key(Keys.INFER_PROFILE, True)
        self.p._file_manager.get_additional_metadata.return_value = dict()
        self.p._add_set(path="a.gcode", sd=False)  # Gets queued, no metadata
        self.p._get_queue(DEFAULT_QUEUE).add_set.assert_not_called()
        self.p._add_set(path="a.gcode", sd=False)  # Second attempt passes through
        self.p._get_queue(DEFAULT_QUEUE).add_set.assert_called_with(
            "",
            {
                "path": "a.gcode",
                "sd": "false",
                "count": 1,
                "jobDraft": True,
                "profiles": [],
            },
        )

    def testUploadNoAction(self):
        self.p.on_event(Events.UPLOAD, dict(path="testpath.gcode"))
        self.p.d.action.assert_not_called()

    def testUploadAddPrintableInvalidFile(self):
        self.p._set_key(Keys.UPLOAD_ACTION, "add_printable")
        self.p._add_set = MagicMock()
        self.p.on_event(Events.UPLOAD, dict(path="testpath.xlsx", target="local"))
        self.p._add_set.assert_not_called()

    def testUploadAddPrintable(self):
        self.p._set_key(Keys.UPLOAD_ACTION, "add_printable")
        self.p._add_set = MagicMock()
        self.p.on_event(Events.UPLOAD, dict(path="testpath.gcode", target="local"))
        self.p._add_set.assert_called_with(draft=False, sd=False, path="testpath.gcode")

    def testUploadAddPrintableGJob(self):
        self.p._set_key(Keys.UPLOAD_ACTION, "add_printable")
        self.p._add_set = MagicMock()
        self.p.on_event(Events.UPLOAD, dict(path="testpath.gjob", target="local"))
        self.p._get_queue(DEFAULT_QUEUE).import_job.assert_called_with(
            "testpath.gjob", draft=False
        )

    def testUploadAddSTL(self):
        self.p._set_key(Keys.UPLOAD_ACTION, "add_printable")
        self.p._add_set = MagicMock()
        self.p.on_event(Events.UPLOAD, dict(path="testpath.stl", target="local"))
        self.p._add_set.assert_called_with(draft=False, sd=False, path="testpath.stl")

    def testFileAddedWithOperationPrintable(self):
        self.p._octoprint_version_exceeds = lambda a, b: True
        self.p._set_key(Keys.UPLOAD_ACTION, "add_printable")
        self.p._add_set = MagicMock()
        self.p.on_event(
            Events.FILE_ADDED,
            dict(path="testpath.gcode", storage="local", operation="add"),
        )
        self.p._add_set.assert_called_with(draft=False, sd=False, path="testpath.gcode")

    def testTempFileMovieDone(self):
        self.p._set_key(Keys.AUTOMATION_TIMELAPSE_ACTION, "auto_remove")
        self.p._delete_timelapse = MagicMock()
        self.p.on_event(
            Events.MOVIE_DONE,
            dict(gcode=TEMP_FILE_DIR + "/test.gcode", movie="test.mp4"),
        )
        self.p._delete_timelapse.assert_called_with("test.mp4")

    def testQueueRunMovieDone(self):
        self.p._sync_history = MagicMock()
        self.p.on_event(Events.MOVIE_DONE, dict(gcode="a.gcode", movie="a.mp4"))
        self.p._queries.annotateLastRun.assert_called_with("a.gcode", "a.mp4", ANY)

    def testPrintDone(self):
        self.p._cleanup_fileshare = lambda: 0
        self.p.on_event(Events.PRINT_DONE, dict())
        self.p.d.action.assert_called_with(DA.SUCCESS, ANY, ANY, ANY, ANY, ANY)

    def testPrintFailed(self):
        self.p.on_event(Events.PRINT_FAILED, dict())
        self.p.d.action.assert_called_with(DA.FAILURE, ANY, ANY, ANY, ANY, ANY)

    def testPrintCancelledByUser(self):
        self.p.on_event(Events.PRINT_CANCELLED, dict(user="admin"))
        self.p.d.action.assert_called_with(DA.DEACTIVATE, ANY, ANY, ANY, ANY, ANY)

    def testPrintCancelledBySystem(self):
        self.p.on_event(Events.PRINT_CANCELLED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY, ANY, ANY)

    def testObicoPauseCommand(self):
        self.p._printer.get_current_job.return_value = dict(
            file=dict(name="test.gcode")
        )
        self.p.d.current_path.return_value = "test.gcode"
        self.p.EVENT_OBICO_COMMAND = "obico_cmd"

        self.p.on_event("obico_cmd", dict(cmd="pause", initiator="system"))
        self.p.d.action.assert_called_with(DA.SPAGHETTI, ANY, ANY, ANY, ANY, ANY)

    def testObicoPauseByUser(self):
        # User pause events (e.g. through the Obico UI) should not trigger automation
        self.p._printer.get_current_job.return_value = dict(
            file=dict(name="test.gcode")
        )
        self.p.d.current_path.return_value = "test.gcode"
        self.p.EVENT_OBICO_COMMAND = "obico_cmd"

        self.p.on_event("obico_cmd", dict(cmd="pause", initiator="user"))
        self.p.d.action.assert_not_called()

    def testSpoolSelected(self):
        self.p.EVENT_SPOOL_SELECTED = "spool_selected"
        self.p.on_event("spool_selected", dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY, ANY, ANY)

    def testSpoolDeselected(self):
        self.p.EVENT_SPOOL_DESELECTED = "spool_desel"
        self.p.on_event("spool_desel", dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY, ANY, ANY)

    def testPrintPaused(self):
        self.p._printer.get_current_job.return_value = dict(
            file=dict(name="test.gcode")
        )
        self.p.d.current_path.return_value = "test.gcode"
        self.p.on_event(Events.PRINT_PAUSED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY, ANY, ANY)

    def testPrintResumed(self):
        self.p._printer.get_current_job.return_value = dict(
            file=dict(name="test.gcode")
        )
        self.p.d.current_path.return_value = "test.gcode"
        self.p.on_event(Events.PRINT_RESUMED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY, ANY, ANY)

    def testPrinterOperational(self):
        self.p._printer.get_state_id.return_value = "OPERATIONAL"
        self.p.on_event(Events.PRINTER_STATE_CHANGED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY, ANY, ANY)

    def testSettingsUpdated(self):
        self.p.on_event(Events.SETTINGS_UPDATED, dict())
        self.p.d.set_retry_on_pause.assert_called()

    def testFileAddedWithNoAnalysis(self):
        self.p._init_analysis_queue(cls=MagicMock(), async_backlog=False)
        self.p._file_manager.get_additional_metadata.return_value = (
            None  # No existing analysis
        )
        self.p.on_event(Events.FILE_ADDED, dict(path="a.gcode"))
        self.p._analysis_queue.enqueue.assert_called()


class TestGetters(unittest.TestCase):
    def setUp(self):
        self.p = mockplugin()
        self.p._spool_manager = None
        self.p._printer_profile = None
        self.p.d = MagicMock()
        self.p.q = MagicMock()
        self.p._sync_state = MagicMock()
        self.p._plugin_manager.plugins.get.return_value = None
        self.p._setup_thirdparty_plugin_integration()

    def testStateJSON(self):
        QT = namedtuple("MockQueue", ["name", "rank"])

        class TQ:
            def __init__(self, name):
                self.name = name

            def as_dict(self):
                return dict(name=self.name)

        self.p._queries.getQueues.return_value = [
            QT(name=ARCHIVE_QUEUE, rank=2),
            QT(name=DEFAULT_QUEUE, rank=1),
            QT(name="asdf", rank=5),
        ]
        self.p.q.queues = dict(
            [("asdf", TQ("asdf")), (DEFAULT_QUEUE, TQ(DEFAULT_QUEUE))]
        )
        self.p.d.status = "test"
        self.p.d.status_type.name = "testing"
        self.assertEqual(
            json.loads(self.p._state_json()),
            {
                "active": True,
                "profile": None,
                "queues": [{"name": "local", "rank": 1}, {"name": "asdf", "rank": 5}],
                "status": "test",
                "statusType": "testing",
            },
        )

    def testHistoryJSON(self):
        self.p._queries.getHistory.return_value = [dict(run_id=1), dict(run_id=2)]
        self.p.q.run = 2
        self.assertEqual(
            json.loads(self.p._history_json()),
            [{"run_id": 1}, {"run_id": 2, "active": True}],
        )


class TestAutoReconnect(unittest.TestCase):
    def setUp(self):
        self.p = mockplugin()

    def testOfflineAutoReconnectDisabledByDefault(self):
        # No need to _set_key here, since it should be off by default (prevent unexpected
        # gantry action on startup)
        self.p._handle_printer_state_reconnect("CLOSED")
        self.p._printer.connect.assert_not_called()

    def testReconnect(self):
        self.p._set_key(Keys.AUTO_RECONNECT, True)
        self.p._handle_printer_state_reconnect("CLOSED")
        self.p._printer.connect.assert_called()
        self.p._printer.reset_mock()

        # Reconnect success shouldn't cause connect() to be called again
        self.p._handle_printer_state_reconnect("OPERATIONAL")
        self.p._printer.connect.assert_not_called()

    def testBackoff(self):
        # Ensure we wait at least CPQPlugin.RECONNECT_WINDOW_SIZE before trying to
        # reconnect after a prior attempt
        NOW = 5
        self.p._set_key(Keys.AUTO_RECONNECT, True)
        self.p._handle_printer_state_reconnect("CLOSED", now=NOW)
        self.p._printer.reset_mock()

        # Wait time is at least the reconnect window size - early calls
        # should do nothing
        self.p._handle_printer_state_reconnect(
            "CLOSED", now=NOW + CPQPlugin.RECONNECT_WINDOW_SIZE * 0.9
        )
        self.p._printer.connect.assert_not_called()

        # Wait time is at most X + 2*X, where X is reconnect size
        after_wait = NOW + 3.1 * CPQPlugin.RECONNECT_WINDOW_SIZE
        self.p._handle_printer_state_reconnect("CLOSED", now=after_wait)
        self.p._printer.connect.assert_called()

    def testWaitsForTerminalState(self):
        # Ensure we wait until the printer has finished trying to connect before attempting another reconnect
        self.p._set_key(Keys.AUTO_RECONNECT, True)
        NOW = 5
        self.p._handle_printer_state_reconnect("CLOSED", now=NOW)
        self.p._printer.reset_mock()

        after_wait = NOW + 3.1 * CPQPlugin.RECONNECT_WINDOW_SIZE
        self.p._handle_printer_state_reconnect("CONNECTING", now=after_wait)
        self.p._printer.connect.assert_not_called()


class TestAnalysis(unittest.TestCase):
    def setUp(self):
        self.p = mockplugin()

    def testInitAnalysisNoFiles(self):
        self.p._file_manager.list_files.return_value = dict(local=dict())
        self.p._init_analysis_queue(cls=MagicMock(), async_backlog=False)
        self.p._analysis_queue.register_finish_callback.assert_called()
        self.p._analysis_queue.enqueue.assert_not_called()

    def testInitAnalysisNoBacklog(self):
        self.p._file_manager.list_files.return_value = dict(
            local=dict(
                file1=dict(
                    type="machinecode",
                    path="a.gcode",
                    continuousprint=dict(profile="TestProfile"),
                )
            )
        )
        self.p._init_analysis_queue(cls=MagicMock(), async_backlog=False)
        self.p._analysis_queue.register_finish_callback.assert_called()
        self.p._analysis_queue.enqueue.assert_not_called()

    def testInitAnalysisWithBacklog(self):
        self.p._file_manager.list_files.return_value = dict(
            local=dict(
                file1=dict(
                    type="machinecode",
                    path="a.gcode",
                ),
                folder1=dict(
                    type="folder",
                    children=dict(
                        file2=dict(
                            type="machinecode",
                            path="b.gcode",
                        )
                    ),
                ),
            )
        )
        self.p._init_analysis_queue(cls=MagicMock(), async_backlog=False)
        self.p._analysis_queue.register_finish_callback.assert_called()
        # Note that python injects some __bool__() calls which is apparently due to threading checks
        # https://gist.github.com/adamf/aaeb8971b8304a24fe034d5ac4710f09
        self.p._analysis_queue.enqueue.assert_has_calls(
            [
                call(
                    QueueEntry(
                        name="a.gcode",
                        path=ANY,
                        type="gcode",
                        location="local",
                        absolute_path=ANY,
                        printer_profile=ANY,
                        analysis=ANY,
                    ),
                    high_priority=False,
                ),
                call(
                    QueueEntry(
                        name="b.gcode",
                        path=ANY,
                        type="gcode",
                        location="local",
                        absolute_path=ANY,
                        printer_profile=ANY,
                        analysis=ANY,
                    ),
                    high_priority=False,
                ),
            ],
            any_order=True,
        )

    def testAnalysisCompleted(self):
        entry = MagicMock()
        entry.path = "a.gcode"
        self.p._on_analysis_finished(entry, dict(profile="TestProfile"))
        self.p._file_manager.set_additional_metadata.assert_called_with(
            ANY, "a.gcode", ANY, ANY, overwrite=True
        )


class TestCleanupFileshare(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        q = MagicMock()
        q.as_dict.return_value = dict(
            jobs=[
                {"hash": "a", "peer_": q.addr, "acquired_by_": None},
                {"hash": "b", "peer_": "peer2", "acquired_by_": q.addr},
                {"hash": "c", "peer_": "peer2", "acquired_by_": None},
                {"hash": "d", "peer_": "peer2", "acquired_by_": None},
            ]
        )
        self.p = mockplugin()
        self.p.fileshare_dir = self.td.name
        self.p.q = MagicMock()
        self.p.q.queues.items.return_value = [("q", q)]

    def tearDown(self):
        self.td.cleanup()

    def testCleanupNoFiles(self):
        self.assertEqual(self.p._cleanup_fileshare(), 0)

    def testCleanupWithFiles(self):
        p = Path(self.p.fileshare_dir)
        (p / "d").mkdir()
        for n in ("a", "b", "c"):
            (p / f"{n}.gcode").touch()
        self.assertEqual(self.p._cleanup_fileshare(), 2)

        for n in ("a", "b"):
            self.assertTrue((p / f"{n}.gcode").exists())
        self.assertFalse((p / "c.gcode").exists())
        self.assertFalse((p / "d").exists())


class TestLocalAddressResolution(unittest.TestCase):
    def setUp(self):
        self.p = mockplugin()

    @patch("continuousprint.plugin.socket")
    def testResolutionViaCheckAddrOK(self, msock):
        self.p._settings.global_set(["server", "onlineCheck", "host"], "checkhost")
        self.p._settings.global_set(["server", "onlineCheck", "port"], 5678)
        s = msock.socket()
        s.getsockname.return_value = ("1.2.3.4", "1234")
        self.assertEqual(self.p.get_local_addr(), "1.2.3.4:1234")
        s.connect.assert_called_with(("checkhost", 5678))

    @patch("continuousprint.plugin.socket")
    def testResolutionFailoverToMDNS(self, msock):
        self.p._can_bind_addr = lambda a: False
        msock.gethostbyname.return_value = "1.2.3.4"
        s = msock.socket()
        s.getsockname.return_value = ("ignored", "1234")
        self.assertEqual(self.p.get_local_addr(), "1.2.3.4:1234")
