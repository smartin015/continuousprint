import unittest
from collections import namedtuple
from .storage.queries import getJobsAndSets
from .storage.database import DEFAULT_QUEUE, ARCHIVE_QUEUE
from unittest.mock import MagicMock, patch, ANY
from .driver import Action as DA
from octoprint.events import Events
import logging
import tempfile
import json
from .data import Keys, TEMP_FILES
from .plugin import CPQPlugin

# logging.basicConfig(level=logging.DEBUG)


class MockSettings:
    def __init__(self):
        self.s = dict()

    def save(self):
        pass

    def get(self, k):
        return self.s.get(k[0])

    def set(self, k, v):
        self.s[k[0]] = v


def mockplugin():
    return CPQPlugin(
        printer=MagicMock(),
        settings=MockSettings(),
        file_manager=MagicMock(),
        plugin_manager=MagicMock(),
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

    def testDBWithLegacySettings(self):
        p = mockplugin()
        p._set_key(
            Keys.QUEUE,
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
        p.get_local_ip = MagicMock(return_value="111.111.111.111")
        p._file_manager.path_on_disk.return_value = "/testpath"

        p._init_fileshare(fs_cls=fs)

        fs.assert_called_with("111.111.111.111:0", "/testpath", logging.getLogger())

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

    def testTick(self):
        self.p.tick()
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testTickExceptionHandled(self):
        self.p.d.action.side_effect = Exception("testing exception")
        self.p.tick()  # does *not* raise exception
        self.p.d.action.assert_called()

    def testUploadNoAction(self):
        self.p.on_event(Events.UPLOAD, dict())
        self.p.d.action.assert_not_called()

    def testUploadAddPrintable(self):
        self.p._set_key(Keys.UPLOAD_ACTION, "add_printable")
        self.p._add_set = MagicMock()
        self.p.on_event(Events.UPLOAD, dict(path="testpath", target="local"))
        self.p._add_set.assert_called_with(draft=False, sd=False, path="testpath")

    def testTempFileMovieDone(self):
        self.p._set_key(Keys.AUTOMATION_TIMELAPSE_ACTION, "auto_remove")
        self.p._delete_timelapse = MagicMock()
        self.p.on_event(
            Events.MOVIE_DONE,
            dict(gcode=list(TEMP_FILES.values())[0].split("/")[-1], movie="test.mp4"),
        )
        self.p._delete_timelapse.assert_called_with("test.mp4")

    def testQueueRunMovieDone(self):
        self.p._sync_history = MagicMock()
        self.p.on_event(Events.MOVIE_DONE, dict(gcode="a.gcode", movie="a.mp4"))
        self.p._queries.annotateLastRun.assert_called_with("a.gcode", "a.mp4", ANY)

    def testPrintDone(self):
        self.p.on_event(Events.PRINT_DONE, dict())
        self.p.d.action.assert_called_with(DA.SUCCESS, ANY, ANY, ANY)

    def testPrintFailed(self):
        self.p.on_event(Events.PRINT_FAILED, dict())
        self.p.d.action.assert_called_with(DA.FAILURE, ANY, ANY, ANY)

    def testPrintCancelledByUser(self):
        self.p.on_event(Events.PRINT_CANCELLED, dict(user="admin"))
        self.p.d.action.assert_called_with(DA.DEACTIVATE, ANY, ANY, ANY)

    def testPrintCancelledBySystem(self):
        self.p.on_event(Events.PRINT_CANCELLED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testObicoPauseCommand(self):
        self.p._printer.get_current_job.return_value = dict(
            file=dict(name="test.gcode")
        )
        self.p.d.current_path.return_value = "test.gcode"
        self.p.EVENT_OBICO_COMMAND = "obico_cmd"

        self.p.on_event("obico_cmd", dict(cmd="pause", initiator="system"))
        self.p.d.action.assert_called_with(DA.SPAGHETTI, ANY, ANY, ANY)

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
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testSpoolDeselected(self):
        self.p.EVENT_SPOOL_DESELECTED = "spool_desel"
        self.p.on_event("spool_desel", dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testPrintPaused(self):
        self.p._printer.get_current_job.return_value = dict(
            file=dict(name="test.gcode")
        )
        self.p.d.current_path.return_value = "test.gcode"
        self.p.on_event(Events.PRINT_PAUSED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testPrintResumed(self):
        self.p._printer.get_current_job.return_value = dict(
            file=dict(name="test.gcode")
        )
        self.p.d.current_path.return_value = "test.gcode"
        self.p.on_event(Events.PRINT_RESUMED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testPrinterOperational(self):
        self.p._printer.get_state_id.return_value = "OPERATIONAL"
        self.p.on_event(Events.PRINTER_STATE_CHANGED, dict())
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testSettingsUpdated(self):
        self.p.on_event(Events.SETTINGS_UPDATED, dict())
        self.p.d.set_retry_on_pause.assert_called()


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
