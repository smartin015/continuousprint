import unittest
from print_queue import PrintQueue, QueueItem
from mock_settings import MockSettings

test_items = [
    QueueItem("foo", "/foo.gcode", False, end_ts=123),
    QueueItem("bar", "/bar.gco", True, end_ts=456),
    QueueItem("baz", "/baz.gco", True),
    QueueItem("boz", "/boz.gco", True),
    QueueItem("foz", "/foz.gco", True),
]

class TestPrintQueue(unittest.TestCase):
    def setUp(self):
        self.s = MockSettings("q")
        self.q = PrintQueue(self.s, "q")

    def test_add_and_len(self):
        self.q.add(test_items)
        self.assertEqual(len(self.q), len(test_items))

    def test_add_idx(self):
        self.q.add(test_items)
        self.q.add([test_items[0]], 2)
        self.assertEqual(self.q[2], test_items[0])
        # No index implies append
        self.q.add([test_items[1]])
        self.assertEqual(self.q[-1], test_items[1])

    def test_array_access(self):
        self.q.add([test_items[0] for i in range(3)])
        self.q[1] = test_items[1]
        self.assertEqual(self.q[1], test_items[1])

    def test_peek(self):
        self.q.add([test_items[0] for i in range(3)])
        self.assertEqual(self.q.peek(), test_items[0])
        self.assertEqual(len(self.q), 3)

    def test_pop(self):
        self.q.add([test_items[0] for i in range(3)])
        self.assertEqual(self.q.pop(), test_items[0])
        self.assertEqual(len(self.q), 2)

    def test_pop_empty(self):
        with self.assertRaises(IndexError):
            self.q.pop()

    def test_peek_empty(self):
        self.assertEqual(self.q.peek(), None)

    def test_remove(self):
        self.q.add([test_items[0]])
        del self.q[0]
        self.assertEqual(len(self.q), 0)

    def test_move(self):
        self.q.add(test_items)
        expected = [test_items[i] for i in [0,3,4,1,2]]
        self.q.move(1, 2, 2) # [0,1,2,3,4] --> [0,3,4,1,2]
        for i in range(5):
            self.assertEqual(self.q[i], expected[i], "mismatch at idx %d; want %s got %s" % (i, [v.name for v in expected], [v.name for v in self.q]))

    def test_move_head(self):
        self.q.add(test_items)
        expected = [test_items[i] for i in [1,0,2,3,4]]
        self.q.move(0,1,1)
        for i in range(5):
            self.assertEqual(self.q[i], expected[i], "mismatch at idx %d; want %s got %s" % (i, [v.name for v in expected], [v.name for v in self.q]))

    def test_move_back(self):
        self.q.add(test_items)
        expected = [test_items[i] for i in [0,2,1,3,4]]
        self.q.move(2,1,-1)
        for i in range(5):
            self.assertEqual(self.q[i], expected[i], "mismatch at idx %d; want %s got %s" % (i, [v.name for v in expected], [v.name for v in self.q]))

    def test_available(self):
        self.q.add(test_items)
        self.assertEqual(len(self.q.available()), len(test_items)-2)

    def test_complete(self):
        self.q.add(test_items)
        self.q.complete("/baz.gco", "done")
        self.assertTrue(self.q[2].end_ts is not None)


if __name__ == "__main__":
    unittest.main()
