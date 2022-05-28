import unittest
import logging
from unittest.mock import MagicMock
from .abstract import Strategy
from .lan import LANQueue

# logging.basicConfig(level=logging.DEBUG)


class TestLANQueueNoConnection(unittest.TestCase):
    def setUp(self):
        self.ucb = MagicMock()
        self.q = LANQueue(
            "ns",
            "localhost:1234",
            "basedir",
            logging.getLogger(),
            Strategy.IN_ORDER,
            self.ucb,
            dict(name="profile"),
        )

    def test_update_peer_state(self):
        self.q.update_peer_state("HI", {}, {})  # No explosions? Good


class TestLANQueueConnected(unittest.TestCase):
    def setUp(self):
        self.ucb = MagicMock()
        self.q = LANQueue(
            "ns",
            "localhost:1234",
            "basedir",
            logging.getLogger(),
            Strategy.IN_ORDER,
            self.ucb,
            dict(name="profile"),
        )
        self.q.lan = MagicMock()
        self.q.lan.q = MagicMock()
