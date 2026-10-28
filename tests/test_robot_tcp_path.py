"""Taught TCP subdivision retains line geometry without motion side effects."""
import math
import unittest

from backend.robot_control.tcp_path import split_fixed_pose_tcp_segment as split


class TcpPathTests(unittest.TestCase):
    def test_diagonal_line_endpoint_and_step_bound(self):
        start = [12.3, -45.6, 20.5, 90, 0, 30]
        end = [22.3, -25.6, *start[2:]]
        original = start[:], end[:]
        points = split(start, end, 3)
        self.assertEqual(points[-1], tuple(end))
        self.assertNotEqual(points[0], tuple(start))
        for previous, point in zip([start] + list(points[:-1]), points):
            self.assertLessEqual(math.dist(previous[:2], point[:2]), 3)
            self.assertEqual(point[2:], tuple(start[2:]))
            cross = (point[0] - start[0]) * 20 - (point[1] - start[1]) * 10
            self.assertAlmostEqual(cross, 0, places=10)
        self.assertEqual((start, end), original)

    def test_long_segment_no_accumulated_drift(self):
        start, end = [0, 0, 7, 180, 0, 0], [99.9, 37.6, 7, 180, 0, 0]
        points = split(start, end, .13)
        for i, point in enumerate(points, 1):
            self.assertEqual(point[0], end[0] * i / len(points))
            self.assertEqual(point[1], end[1] * i / len(points))
        self.assertEqual(points[-1], tuple(end))

    def test_zero_length_and_single_target(self):
        start = [0, 0, 7, 180, 0, 0]
        self.assertEqual(split(start, start, 2), ())
        self.assertEqual(split(start, [1, 0, *start[2:]], 2), ((1., 0., 7., 180., 0., 0.),))

    def test_reject_changed_height_or_literal_angles(self):
        start = [0, 0, 7, 180, 0, 0]
        for index, value in ((2, 7.001), (3, -180), (4, .001), (5, 360)):
            end = start[:]
            end[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                split(start, end, 2)

    def test_invalid_values_and_budget(self):
        start = [0, 0, 7, 180, 0, 0]
        for step in (0, -1, 20.01, float('nan'), float('inf'), True):
            with self.subTest(step=step), self.assertRaises(ValueError):
                split(start, start, step)
        for value in (float('nan'), float('inf'), True, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                split([value, *start[1:]], start, 2)
        with self.assertRaises(ValueError):
            split(start, [20001, 0, *start[2:]], 20)
        with self.assertRaises(ValueError):
            split(start[:5], start, 2)

    def test_budget_boundary_and_unrepresentable_small_steps(self):
        start = [0, 0, 7, 180, 0, 0]
        points = split(start, [20000, 0, *start[2:]], 20)
        self.assertEqual(len(points), 1000)
        for previous, point in zip([start] + list(points[:-1]), points):
            self.assertLessEqual(math.dist(previous[:2], point[:2]), 20)
        with self.assertRaises(ValueError):
            split([1e16, 0, *start[2:]], [1e16 + 2, 0, *start[2:]], 1)


if __name__ == '__main__':
    unittest.main()
