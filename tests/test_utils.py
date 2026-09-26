import unittest
from src.utils import get_limited_rows


class TestUtils(unittest.TestCase):
    def test_get_limited_rows(self):
        all_test_limits = [1, 3, 5]
        rows = [f"row{i}" for i in range(10)]

        for limit in all_test_limits:
            with self.subTest(msg=f"Testing {limit=}"):
                for r in rows:
                    res = get_limited_rows(r, rows_limit=limit)
                self.assertEqual(len(res.split('\n')), limit)


if __name__ == '__main__':
    unittest.main()
