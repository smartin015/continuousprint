# Implements a Stern-Brocot ordering via rational fractions
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
