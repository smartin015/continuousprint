import unittest
from unittest.mock import MagicMock
from .lan import LANJobView, LANSetView


class LANViewTest(unittest.TestCase):
    def setUp(self):
        self.lq = MagicMock()
        self.j = LANJobView(
            dict(
                name="j",
                count=1,
                remaining=1,
                created=1234,
                hash_="hash",
                sets=[dict(path="a.gcode", count=1, remaining=1)],
            ),
            self.lq,
        )
        self.s = self.j.sets[0]

    def test_resolve_file(self):
        self.s.resolveFile()
