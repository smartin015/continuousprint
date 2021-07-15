import unittest
from print_queue import PrintQueue

class MockSettings:
    def __init__(self, k):
        self.k = k
        self.s = "[]"
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

test_items = [
        {"sd": "false", "name": "foo", "path": "/foo.gcode", "count": 1, "times_run": 0},
        {"sd": "true", "name": "bar", "path": "/bar.gcode", "count": 2, "times_run": 1},
        ]

test_bad_items = [
        {"sd": "false", "path": "", "count": 0},
        ]

class TestPrintQueue(unittest.TestCase):
    def setUp(self):
        self.s = MockSettings("q")
        self.q = PrintQueue(self.s, "q")

    def test_add_and_len(self):
        for item in test_items:
            self.q.add(item)
        self.assertEqual(len(self.q), len(test_items))

    def test_add_invalid(self):
        for item in test_bad_items:
            with self.assertRaises(ValueError):
                self.q.add(item)

    def test_array_access(self):
        for i in range(3):
            self.q.add(test_items[0])
        self.q[1] = test_items[1]
        self.assertEqual(self.q[1], test_items[1])

    def test_peek(self):
        for i in range(3):
            self.q.add(test_items[0])
        self.assertEqual(self.q.peek(), test_items[0])
        self.assertEqual(len(self.q), 3)

    def test_pop(self):
        for i in range(3):
            self.q.add(test_items[0])
        self.assertEqual(self.q.pop(), test_items[0])
        self.assertEqual(len(self.q), 2)

    def test_pop_empty(self):
        with self.assertRaises(IndexError):
            self.q.pop()

    def test_peek_empty(self):
        self.assertEqual(self.q.peek(), None)

    def test_remove(self):
        self.q.add(test_items[0])
        del self.q[0]
        self.assertEqual(len(self.q), 0)

    def test_move(self):
        for i in range(5):
            self.q.add(test_items[0])
        self.q[2] = test_items[1]
        self.q.move(2, 3)
        self.assertEqual(self.q[3], test_items[1])
        self.assertEqual(self.q[2], test_items[0])

    def test_change_count(self):
        self.q.add(test_items[0])
        self.q.setCount(0, 5)
        self.assertEqual(self.q[0]["count"], 5)

if __name__ == "__main__":
    unittest.main()
