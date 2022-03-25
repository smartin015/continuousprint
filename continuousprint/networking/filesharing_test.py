import unittest
import logging
from unittest.mock import MagicMock, ANY, mock_open, patch
from filesharing import FileShare

logging.basicConfig(level=logging.DEBUG)

TEST_DISK_PATH='/real/file/location.gcode'

class MockStorage:
  list_files = MagicMock(return_value={'a': {'b.gcode': None}, 'c.gcode': None, 'd.gcode': None})
  path_on_disk = MagicMock(return_value=TEST_DISK_PATH)

class MockQueries:
  getFiles = MagicMock(return_value={'definitely_an_md5_hash': 'd.gcode'})
  addFileWithHash = MagicMock()
  getPathWithHash = MagicMock(return_value="test.gcode")

class FileSharingTest(unittest.TestCase):

  def setUp(self):
    self._storage = MockStorage()
    self._queries = MockQueries()
    self.fs = FileShare(self._storage, self._queries, logging.getLogger())
    self.m = mock_open()

  @patch('builtins.open', mock_open(read_data=b'1'))
  def testAnalyzeAllNew(self):
    self.fs.analyzeAllNew()
    open.assert_called_with(TEST_DISK_PATH, 'rb')
    self._queries.addFileWithHash.assert_any_call('a/b.gcode', ANY)
    self._queries.addFileWithHash.assert_any_call('c.gcode', ANY)

  def testHashToPath(self):
    md5 = "123ABC"
    result = self.fs.hash_to_path(md5)
    self._queries.getPathWithHash.assert_called_with(md5)

  def testGetFilehashMap(self):
    result = self.fs.get_filehash_map()
    self.assertEqual(self._queries.getFiles(), result)

if __name__ == "__main__":
  unittest.main()
