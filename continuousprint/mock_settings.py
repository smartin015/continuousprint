class MockSettings:
    def __init__(self, k, s="[]"):
        self.k = k
        self.s = s

    def save(self):
        pass

    def get(self, a):
        if a[0] != self.k:
            raise Exception(f"Unexpected settings key {a[0]}")
        return self.s

    def set(self, ak, v):
        if ak[0] != self.k:
            raise Exception(f"Unexpected settings key {ak[0]}")
        self.s = v
