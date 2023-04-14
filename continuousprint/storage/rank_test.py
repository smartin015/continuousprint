import unittest
from .rank import Rational as R, rational_intermediate


class TestRational(unittest.TestCase):
    def test_lt(self):
        self.assertFalse(R(1, 2) < R(1, 4))
        self.assertTrue(R(1, 2) < R(2, 1))

    def test_gt(self):
        self.assertFalse(R(4, 7) > R(7, 3))
        self.assertTrue(R(4, 7) > R(3, 7))

    def test_eq(self):
        self.assertFalse(R(4, 5) == R(9, 10))
        self.assertTrue(R(4, 5) == R(8, 10))

    def test_ne(self):
        self.assertFalse(R(4, 5) != R(8, 10))
        self.assertTrue(R(4, 5) != R(9, 10))

    def test_ge(self):
        self.assertFalse(R(7, 5) >= R(7, 4))
        self.assertTrue(R(7, 5) >= R(14, 10))
        self.assertTrue(R(7, 5) >= R(13, 10))

    def test_le(self):
        self.assertFalse(R(7, 5) <= R(7, 6))
        self.assertTrue(R(7, 5) <= R(14, 10))
        self.assertTrue(R(7, 5) <= R(7, 4))

    def test_mediant(self):
        self.assertEqual(R(1, 2).mediant(R(1, 1)), R(2, 3))

    def test_intermediate(self):
        # Picking values from https://begriffs.com/posts/2018-03-20-user-defined-order.html#approach-3-true-fractions
        for args, want in [
            ((R(0, 1), R(1, 0)), R(1, 1)),  # Push on empty
            ((R(1, 2), R(1, 1)), R(2, 3)),  # Push mid of 2 element list
            ((R(1, 2), R(3, 5)), R(4, 7)),  # Push early in list
            ((R(3, 1), R(4, 1)), R(7, 2)),  # Push onto penultimate spot
            ((R(4, 1), R(1, 0)), R(5, 1)),  # Push onto end
            ((R(0, 1), R(1, 4)), R(1, 5)),  # Push onto front
        ]:
            with self.subTest(f"x={args[0]}, y={args[1]}"):
                self.assertEqual(rational_intermediate(*args), want)
