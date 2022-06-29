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
from .data import Keys
from .plugin import CPQPlugin

logging.basicConfig(level=logging.DEBUG)


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

    def testTick(self):
        self.p.tick()
        self.p.d.action.assert_called_with(DA.TICK, ANY, ANY, ANY)

    def testTickExceptionHandled(self):
        self.p.d.action.side_effect = Exception("whoops")
        self.p.tick()  # does *not* raise exception
        self.p.d.action.assert_called()

    def testUploadNoAction(self):
        self.p.on_event(Events.UPLOAD, dict())
        self.p.d.action.assert_not_called()

    def testUploadAddPrintable(self):
        pass

    def testTempFileMovieDone(self):
        pass

    def testQueueRunMovieDone(self):
        pass

    def testPrintDone(self):
        pass

    def testPrintFailed(self):
        pass

    def testPrintCancelledByUser(self):
        pass

    def testPrintCancelledBySystem(self):
        pass

    def testObicoPauseCommand(self):
        pass

    def testSpoolSelected(self):
        pass

    def testSpoolDeselected(self):
        pass

    def testPrintPaused(self):
        pass

    def testPrintResumed(self):
        pass

    def testPrinterOperational(self):
        pass

    def testSettingsUpdated(self):
        pass


class TestGetters(unittest.TestCase):
    def testStateJSON(self):
        pass

    def testHistoryJSON(self):
        pass
