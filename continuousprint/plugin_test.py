import unittest
from unittest.mock import MagicMock, patch
from octoprint.events import Events
import logging
from .data import Keys
from .plugin import CPQPlugin

logging.basicConfig(level=logging.DEBUG)


class MockSettings:
    def __init__(self):
        self.s = dict()

    def save(self):
        pass

    def get(self, k):
        return self.s[k[0]]

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

    def testDB(self):
        pass

    def testDBWithLegacySettings(self):
        pass

    def testFileshare(self):
        pass

    def testQueues(self):
        pass

    def testLANQueues(self):
        pass

    def testDriver(self):
        pass


class TestEventHandling(unittest.TestCase):
    def setUp(self):
        pass

    def testTick(self):
        pass

    def testTickExceptionHandled(self):
        pass

    def testUploadNoAction(self):
        pass

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
