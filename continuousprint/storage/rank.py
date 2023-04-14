# Implements a Stern-Brocot ordering
# https://begriffs.com/posts/2018-03-20-user-defined-order.html#approach-3-true-fractions


class Rational:
    def __init__(self, numerator, denominator):
        self.n = numerator
        self.d = denominator

    def mediant(self, other):
        # https://www.cut-the-knot.org/proofs/fords.shtml#mediant
        # mediant of n1/d1 and n2/d2 = (n1 + n2)/(d1 + d2)
        return Rational(self.n + other.n, self.d + other.d)

    def _norm_op(self, other, op):
        return op(self.n * other.d, other.n * self.d)

    def __lt__(self, other):
        return self._norm_op(other, int.__lt__)

    def __gt__(self, other):
        return self._norm_op(other, int.__gt__)

    def __eq__(self, other):
        return self._norm_op(other, int.__eq__)

    def __ne__(self, other):
        return self._norm_op(other, int.__ne__)

    def __le__(self, other):
        return self._norm_op(other, int.__le__)

    def __ge__(self, other):
        return self._norm_op(other, int.__ge__)

    def __repr__(self):
        return f"({self.n}/{self.d})"


def rational_intermediate(
    x: Rational, y: Rational, lo=Rational(0, 1), hi=Rational(1, 0)
) -> Rational:
    # Find the rational intermediate between rationals X and Y
    # via binary search
    assert x < y
    assert x >= lo
    assert y >= lo
    n = 0
    while True:
        med = lo.mediant(hi)
        if med <= x:  # (cmp(med, &x) < 1)
            lo = med
        elif med >= y:  # (cmp(med, &y) > -1)
            hi = med
        else:
            return med
        n += 1
        if n > 1000:
            raise RuntimeError("rational intermediate depth exceeded")


# Allow for infinite ordering via variable-length bytestring.
# bytes values always begin with a 1-bit to mark the total number of bits
# Note that python automatically uses bigints when size exceeds a certain
# amount.
# def midpoint_tag(r1: Rational, r2: Rational) -> Rational:
#     if before is None and after is None:
#         return Rational(1,1)
#
#     if before is None: # Far left of decision tree; add 0
#         if after.n == 1:
#             return Rational(after.n, after.d+1)
#         else:
#             return Rational(
#     if after is None: # Far right of decision tree
#         if before & 0x01 == 1:
#             return (before << 1) | 0x00
#         else:
#             return (before << 1) | 0x01
#         return add_bit(before, 1)
#
#     # Take whichever number's shorter and
#     # add a bit
#     if before.bit_length() < after.bit_length():
#         return add_bit(before, 1)
#     else: # before >= after
#         return add_bit(after, 0)
#
# # Return
# #   <0 if a < b
# #   >0 if a > b
# #   0 if a == b
# def compare(a: int, b: int) -> int:
#     # -1 to account for initial digit
#     la = a.bit_length() - 1
#     lb = b.bit_length() - 1
#     ia = 0
#     ib = 0
#     # Build ints in reverse order until we hit the same level
#     while la >= 0 and lb >= 0:
#         ia = (ia << 1) | ((a >> la) & 0x01)
#         ib = (ib << 1) | ((b >> lb) & 0x01)
#         la -= 1
#         lb -= 1
#     return ia - ib
