import unittest
from unittest.mock import MagicMock
import logging
from .spoolmanager import SpoolManagerIntegration, SpoolManagerException


class TestSpoolManagerIntegration(unittest.TestCase):
    def setUp(self):
        self.s = SpoolManagerIntegration(
            impl=MagicMock(),
            logger=logging.getLogger(),
        )

    def test_get_materials_ok(self):
        self.s._impl.api_getSelectedSpoolInformations.return_value = [
            dict(material="PLA", colorName="red", color="FF0000"),
            dict(material="ABS", colorName="blue", color="0000FF"),
        ]
        self.assertEqual(self.s.get_materials(), ["PLA_red_FF0000", "ABS_blue_0000FF"])

    def test_get_materials_exception(self):
        self.s._impl.api_getSelectedSpoolInformations.side_effect = Exception("testing")
        self.assertEqual(self.s.get_materials(), [])

    def test_allowed_to_print(self):
        self.s._impl.allowed_to_print.return_value = MagicMock(
            status_code=200, data="123"
        )
        self.assertEqual(self.s.allowed_to_print(), 123)

    def test_allowed_to_print_err(self):
        self.s._impl.allowed_to_print.return_value = MagicMock(
            status_code=500, data="testing error"
        )
        with self.assertRaises(SpoolManagerException):
            self.s.allowed_to_print()

    def test_start_print_confirmed(self):
        self.s._impl.start_print_confirmed.return_value = MagicMock(
            status_code=200, data="123"
        )
        self.assertEqual(self.s.start_print_confirmed(), 123)

    def test_start_print_confirmed_err(self):
        self.s._impl.start_print_confirmed.return_value = MagicMock(
            status_code=500, data="testing error"
        )
        with self.assertRaises(SpoolManagerException):
            self.s.allowed_to_print()
