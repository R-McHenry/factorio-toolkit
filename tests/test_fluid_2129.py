"""2.1.29: fluid_route's distance map is a BFS of the goals' box, exact for Manhattan distance."""
import random
import unittest
from collections import deque

from fkcore import fluid_route as fr


def _whole_box(box, goals):
    """The 2.1.28 map: a BFS of the whole box."""
    x0, y0, x1, y1 = box
    dist = {t: 0 for t in goals}
    todo = deque(sorted(goals))
    while todo:
        t = todo.popleft()
        for n in fr._nbrs(t):
            if n not in dist and x0 - 1 <= n[0] <= x1 and y0 - 1 <= n[1] <= y1:
                dist[n] = dist[t] + 1
                todo.append(n)
    return dist


class DistanceMap(unittest.TestCase):
    def test_same_as_the_whole_box_bfs(self):
        rnd = random.Random(7)
        for _ in range(60):
            x0, y0 = rnd.randint(-5, 5), rnd.randint(-5, 5)
            box = (x0, y0, x0 + rnd.randint(1, 20), y0 + rnd.randint(1, 20))
            goals = {(rnd.randint(box[0] - 1, box[2]), rnd.randint(box[1] - 1, box[3]))
                     for _ in range(rnd.randint(1, 6))}
            old, new = _whole_box(box, goals), fr._L1(box, goals)
            for x in range(box[0] - 3, box[2] + 3):
                for y in range(box[1] - 3, box[3] + 3):
                    self.assertEqual(old.get((x, y), 0), new.get((x, y), 0), (box, goals, x, y))

    def test_no_goals(self):
        self.assertEqual(fr._L1((0, 0, 5, 5), set()).get((2, 2), 0), 0)


if __name__ == "__main__":
    unittest.main()
