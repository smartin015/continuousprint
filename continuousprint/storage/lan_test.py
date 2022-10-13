import unittest
from unittest.mock import MagicMock
from .lan import LANJobView, LANSetView, ResolveError
from requests.exceptions import HTTPError


class LANViewTest(unittest.TestCase):
    def setUp(self):
        self.lq = MagicMock()
        self.j = LANJobView(
            dict(
                id="<hash>",
                name="j",
                count=2,
                remaining=2,
                created=1234,
                sets=[dict(path="a.gcode", count=1, remaining=1)],
                peer_="asdf:6789",
            ),
            self.lq,
        )
        self.s = self.j.sets[0]

    def test_resolve_file(self):
        self.lq.resolve_set.return_value = "/path/to/set.gcode"
        self.assertEqual(self.s.resolve(), "/path/to/set.gcode")

    def test_resolve_http_error(self):
        self.lq.resolve_set.side_effect = HTTPError
        with self.assertRaises(ResolveError):
            self.s.resolve()

    def test_decrement_refreshes_sets_and_saves(self):
        self.s.remaining = 0
        self.s.completed = 5
        self.j.decrement()
        self.lq.set_job.assert_called()
        self.assertEqual(
            self.lq.set_job.call_args[0][1]["sets"][0]["remaining"], self.s.count
        )
        self.assertEqual(self.lq.set_job.call_args[0][1]["sets"][0]["completed"], 0)

    def test_save_persists_peer_and_hash(self):
        self.j.peer = "foo"
        self.j.hash = "bar"
        self.j.save()
        data = self.lq.set_job.call_args[0][1]
        self.assertEqual(data["peer_"], "foo")
        self.assertEqual(data["hash"], "bar")
