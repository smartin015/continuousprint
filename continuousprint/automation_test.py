import unittest
from .automation import getInterpreter, genEventScript


class TestInterpreter(unittest.TestCase):
    def testGetInterpreter(self):
        interp, _, _ = getInterpreter(dict(a=1))
        self.assertEqual(interp.symtable["a"], 1)


class TestGenEventScript(unittest.TestCase):
    def testEvalTrueFalseNone(self):
        a = [("gcode1", "p1")]
        self.assertEqual(genEventScript(a, lambda cond: True), "gcode1")
        self.assertEqual(genEventScript(a, lambda cond: False), "")
        self.assertEqual(genEventScript(a, lambda cond: None), "")

    def testPlaceholderNoPreprocessor(self):
        a = [("{foo} will never be formatted!", None)]
        with self.assertRaises(Exception):
            genEventScript(a, lambda cond: False)

    def testEvalMissedPlaceholder(self):
        a = [("{foo} will never be formatted!", "p1")]
        with self.assertRaises(Exception):
            genEventScript(a, lambda cond: dict(bar="baz"))

    def testEvalFormat(self):
        a = [("Hello {val}", "p1")]
        self.assertEqual(
            genEventScript(a, lambda cond: dict(val="World")), "Hello World"
        )

    def testEvalBadType(self):
        a = [("dontcare", "p1")]
        with self.assertRaises(Exception):
            genEventScript(a, lambda cond: 7)
