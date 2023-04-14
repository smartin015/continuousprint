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


# class TestMidpointTag(unittest.TestCase):
#
#     def test_nones(self):
#         self.assertEqual(midpoint_tag(None, None), 1)
#
#     def test_singularity(self):
#         self.assertEqual(midpoint_tag(1, 1), 0b10)
#
#     def test_uses_shorter(self):
#         self.assertEqual(midpoint_tag(0b100, 0b1010), 0b1001)
#         self.assertEqual(midpoint_tag(0b1001, 0b101), 0b1010)
#
#     def test_equal_bit_length(self):
#         self.assertEqual(midpoint_tag(0b1110, 0b1111), 0b11110)
#
# class TestCompare(unittest.TestCase):
#
#     def test_eq_short(self):
#         self.assertEqual(compare(0b1, 0b1), 0)
#
#     def test_eq_long(self):
#         self.assertEqual(compare(0b10101010, 0b10101010), 0)
#
#     def test_long_a_lt_short_b(self):
#         self.assertLess(compare(0b1010, 0b11), 0)
#
#     def test_long_a_gt_short_b(self):
#         self.assertGreater(compare(0b110, 0b10), 0)
#
#     def test_long_a_lt_long_b(self):
#         self.assertLess(compare(0b1010, 0b1011), 0)
#
#     def test_long_a_gt_long_b(self):
#         self.assertGreater(compare(0b11110, 0b11100), 0)
#
#     def test_very_long_a_lt_b(self):
#         self.assertLess(compare(
#             0b1110111010010100101111101110000101111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111,
#             0b111011101011010010111110111000010
#         ), 0)
