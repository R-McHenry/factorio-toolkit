"""fkcore.frame: a module's frame as a tile set (PLAN-ORGANIC part H, H1).

A ``Frame`` is the set of tiles a module claims, stored run-length by row with its bounding box.
It comes from a box (``size WxH``: the fast path, every reader keeps its rectangle arithmetic),
a polygon (``shape (x,y) (x,y) ...`` on the module line: integer vertices in the module's own
frame, edges on tile boundaries, scanline rasterised by the even-odd rule over tile centres), a
run list (a territory, part T's output, ``[(y, x0, x1)]``) or a plain tile set (an achieved hull).

Coordinates are the module's own: the origin is the module's ``(0, 0)`` and a frame lives in the
quadrant from it, as a ``size`` box does. ``turn(rot)`` turns the tiles about the origin exactly
as ``compose.turn`` turns a point of the bounding box from the origin, so a turned polygon lands
where a turned box of its bounding box lands (origins, not edges: a frame turns about its origin).
Pure, stdlib only; a Frame is immutable.
"""
from __future__ import annotations

from bisect import bisect_right
from fractions import Fraction

__all__ = ["Frame", "ShapeError", "shape_problem", "SIDES"]

SIDES = ("n", "e", "s", "w")


class ShapeError(ValueError):
    """A polygon that is no frame: too few vertices, a repeated vertex, a self-crossing, no
    area, or a vertex behind the origin."""


def _merge(runs):
    """Sorted, non-overlapping, non-touching (x0, x1) runs from any list of them."""
    runs = sorted((int(a), int(b)) for a, b in runs if b > a)
    out = []
    for a, b in runs:
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return tuple(out)


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(p, a, b):
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _segments_touch(a, b, c, d):
    """True when segments a-b and c-d meet anywhere (a proper crossing, an end on the other, or a
    collinear overlap)."""
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return True
    if d1 == 0 and _on_segment(a, c, d):
        return True
    if d2 == 0 and _on_segment(b, c, d):
        return True
    if d3 == 0 and _on_segment(c, a, b):
        return True
    return d4 == 0 and _on_segment(d, a, b)


def shape_problem(verts):
    """Why ``verts`` is no frame polygon, or None. The polygon is closed (a last vertex equal to
    the first is allowed and dropped), simple (no two edges meet except adjacent ones at their
    shared vertex), of some area, with integer vertices in the quadrant from the origin."""
    pts = [(v[0], v[1]) for v in verts]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return f"{len(pts)} vertices: a shape needs three or more"
    for x, y in pts:
        if int(x) != x or int(y) != y:
            return f"vertex ({x}, {y}) is not on a tile corner: whole numbers only"
        if x < 0 or y < 0:
            return f"vertex ({x}, {y}) lies behind the origin: a frame starts at its module's (0, 0)"
    if len(set(pts)) != len(pts):
        dup = next(p for p in pts if pts.count(p) > 1)
        return f"vertex ({dup[0]}, {dup[1]}) is written twice"
    n = len(pts)
    if all(_cross(pts[0], pts[1], p) == 0 for p in pts[2:]):
        return "the shape has no area"          # every vertex on one line: no fold to name
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        a, b = edges[i]
        for j in range(i + 1, n):
            c, d = edges[j]
            adjacent = j == i + 1 or (i == 0 and j == n - 1)
            if adjacent:
                # they share one vertex; a fold back along the other is a crossing too
                shared = b if j == i + 1 else a
                other_a = a if shared == b else b
                other_c = d if shared == c else c
                if _cross(shared, other_a, other_c) == 0 and \
                        (other_a[0] - shared[0]) * (other_c[0] - shared[0]) + \
                        (other_a[1] - shared[1]) * (other_c[1] - shared[1]) > 0:
                    return f"the edges at ({shared[0]}, {shared[1]}) fold back on each other"
                continue
            if _segments_touch(a, b, c, d):
                return (f"edge ({a[0]}, {a[1]})-({b[0]}, {b[1]}) crosses edge "
                        f"({c[0]}, {c[1]})-({d[0]}, {d[1]})")
    area2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area2 == 0:
        return "the shape has no area"
    return None


class Frame:
    """A tile set, run-length by row. ``rows`` is {y: ((x0, x1), ...)} with sorted, merged,
    half-open runs; ``box`` is (x0, y0, x1, y1), half-open, or None when empty."""

    __slots__ = ("rows", "box", "_area", "_hash", "_claim")

    def __init__(self, rows):
        clean = {}
        for y, runs in rows.items():
            m = _merge(runs)
            if m:
                clean[int(y)] = m
        self.rows = clean
        if clean:
            ys = sorted(clean)
            self.box = (min(r[0][0] for r in clean.values()), ys[0],
                        max(r[-1][1] for r in clean.values()), ys[-1] + 1)
        else:
            self.box = None
        self._area = sum(b - a for runs in clean.values() for a, b in runs)
        self._hash = None
        self._claim = None

    # -- construction -----------------------------------------------------------------------
    @classmethod
    def from_box(cls, x0, y0, x1=None, y1=None):
        """``Frame.from_box(w, h)`` (from the origin) or ``Frame.from_box(x0, y0, x1, y1)``."""
        if x1 is None:
            x0, y0, x1, y1 = 0, 0, x0, y0
        if x1 <= x0 or y1 <= y0:
            return cls({})
        f = cls.__new__(cls)
        run = ((int(x0), int(x1)),)
        f.rows = {y: run for y in range(int(y0), int(y1))}
        f.box = (int(x0), int(y0), int(x1), int(y1))
        f._area = (x1 - x0) * (y1 - y0)
        f._hash = None
        f._claim = None
        return f

    def boxed(self, box):
        """This frame with ``box`` (x0, y0, x1, y1, holding every tile) as its ``box``: a hull
        inside its claim (43-hull). Every reader that asks for the rectangle (the unit's frame
        in the store and the compile key, ``frame_of``, ``rows_text``) gets the claim; the
        tiles are the hull's. ``is_box`` is False unless the tiles fill it. ``moved`` keeps
        the claim; a transform that rebuilds the rows drops it."""
        box = tuple(int(v) for v in box)
        if self.box is not None and not (box[0] <= self.box[0] and box[1] <= self.box[1]
                                         and self.box[2] <= box[2] and self.box[3] <= box[3]):
            raise ValueError(f"box {box} does not hold the frame's {self.box}")
        f = Frame.__new__(Frame)
        f.rows, f._area, f._hash = self.rows, self._area, None
        f.box, f._claim = box, box
        return f

    @classmethod
    def from_runs(cls, runs):
        """From ``[(y, x0, x1)]`` (a territory as part T writes one)."""
        rows = {}
        for y, x0, x1 in runs:
            rows.setdefault(int(y), []).append((int(x0), int(x1)))
        return cls(rows)

    @classmethod
    def from_tiles(cls, tiles):
        """From any iterable of (x, y) tiles (an achieved hull)."""
        rows = {}
        for x, y in tiles:
            rows.setdefault(int(y), []).append((int(x), int(x) + 1))
        return cls(rows)

    @classmethod
    def from_polygon(cls, verts):
        """From a closed simple polygon with integer vertices: the tiles whose centres lie inside
        it (even-odd rule), scanline per row. Raises ``ShapeError`` when ``shape_problem`` finds
        one."""
        why = shape_problem(verts)
        if why is not None:
            raise ShapeError(why)
        pts = [(int(v[0]), int(v[1])) for v in verts]
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        n = len(pts)
        edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        rows = {}
        for y in range(y0, y1):
            yc = Fraction(2 * y + 1, 2)
            xs = []
            for (ax, ay), (bx, by) in edges:
                if ay == by:
                    continue
                lo, hi = (ay, by) if ay < by else (by, ay)
                if lo <= yc < hi:
                    xs.append(Fraction(ax) + (yc - ay) * Fraction(bx - ax, by - ay))
            xs.sort()
            runs = []
            for i in range(0, len(xs) - 1, 2):
                xa, xb = xs[i], xs[i + 1]
                # tile centres x + 1/2 strictly between the two crossings
                first = (xa - Fraction(1, 2)).__floor__() + 1
                last = (xb - Fraction(1, 2)).__ceil__() - 1
                if last >= first:
                    runs.append((first, last + 1))
            if runs:
                rows[y] = runs
        return cls(rows)

    # -- the fast path ----------------------------------------------------------------------
    @property
    def is_box(self):
        """True when the frame is exactly its bounding box (every reader's rectangle case)."""
        if self.box is None:
            return False
        x0, y0, x1, y1 = self.box
        return self._area == (x1 - x0) * (y1 - y0)

    @property
    def area(self):
        return self._area

    @property
    def size(self):
        """(w, h) of the bounding box, (0, 0) when empty."""
        if self.box is None:
            return (0, 0)
        return (self.box[2] - self.box[0], self.box[3] - self.box[1])

    def __len__(self):
        return self._area

    def __bool__(self):
        return self._area > 0

    def __iter__(self):
        for y in sorted(self.rows):
            for a, b in self.rows[y]:
                for x in range(a, b):
                    yield (x, y)

    def __contains__(self, tile):
        return self.contains(tile[0], tile[1])

    def __eq__(self, other):
        return isinstance(other, Frame) and self.rows == other.rows

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(tuple(sorted(self.rows.items())))
        return self._hash

    def __repr__(self):
        if self.box is None:
            return "Frame(empty)"
        kind = "box" if self.is_box else f"{self._area} tiles in"
        return f"Frame({kind} {self.box[0]},{self.box[1]}..{self.box[2] - 1},{self.box[3] - 1})"

    # -- queries ----------------------------------------------------------------------------
    def contains(self, x, y):
        runs = self.rows.get(int(y))
        if not runs:
            return False
        x = int(x)
        i = bisect_right(runs, (x, float("inf"))) - 1
        return i >= 0 and runs[i][0] <= x < runs[i][1]

    def tiles(self):
        """The tiles as a set."""
        return set(self)

    def runs(self):
        """``[(y, x0, x1)]``, sorted: the territory form."""
        return [(y, a, b) for y in sorted(self.rows) for a, b in self.rows[y]]

    def boundary(self, side):
        """The outermost tiles on ``side``: for ``n``/``s`` one per column the frame reaches, as
        [(x, y)] sorted by x; for ``e``/``w`` one per row, sorted by y."""
        if side in ("w", "e"):
            out = []
            for y in sorted(self.rows):
                runs = self.rows[y]
                out.append((runs[0][0], y) if side == "w" else (runs[-1][1] - 1, y))
            return out
        if side not in ("n", "s"):
            raise ValueError(f"side {side!r}: one of n, e, s, w")
        best = {}
        for y in sorted(self.rows):
            for a, b in self.rows[y]:
                for x in range(a, b):
                    if x not in best or (y < best[x] if side == "n" else y > best[x]):
                        best[x] = y
        return [(x, best[x]) for x in sorted(best)]

    def boundary_at(self, side, k):
        """The boundary tile of ``side`` at column (n/s) or row (e/w) ``k``, or None when the
        frame does not reach it."""
        for t in self.boundary(side):
            if (t[0] if side in ("n", "s") else t[1]) == k:
                return t
        return None

    def boundary_near(self, side, k):
        """The boundary tile of ``side`` at column (n/s) or row (e/w) ``k`` when the frame
        reaches it, else the boundary tile of that side nearest along it (the lower one on a
        tie): where ``@n12`` puts a port (H3). None for an empty frame."""
        tiles = self.boundary(side)
        if not tiles:
            return None
        i = 0 if side in ("n", "s") else 1
        return min(tiles, key=lambda t: (abs(t[i] - k), t[i]))

    def nearest_boundary(self, point, side=None):
        """The boundary tile nearest ``point`` (x, y, any position; tile centres are compared),
        on ``side`` when given, else over all four sides. None for an empty frame."""
        sides = (side,) if side else SIDES
        cands = {t for s in sides for t in self.boundary(s)}
        if not cands:
            return None
        px, py = float(point[0]), float(point[1])
        return min(cands, key=lambda t: ((t[0] + 0.5 - px) ** 2 + (t[1] + 0.5 - py) ** 2, t[1], t[0]))

    def overlap(self, other):
        """The tiles both frames hold, as a Frame."""
        rows = {}
        for y, mine in self.rows.items():
            theirs = other.rows.get(y)
            if not theirs:
                continue
            got = []
            for a, b in mine:
                for c, d in theirs:
                    lo, hi = max(a, c), min(b, d)
                    if lo < hi:
                        got.append((lo, hi))
            if got:
                rows[y] = got
        return Frame(rows)

    def overlaps_box(self, box):
        """True when any tile lies in ``box`` (x0, y0, x1, y1)."""
        if self.box is None:
            return False
        if self.box[0] >= box[2] or box[0] >= self.box[2] or self.box[1] >= box[3] \
                or box[1] >= self.box[3]:
            return False
        for y in range(max(self.box[1], box[1]), min(self.box[3], box[3])):
            for a, b in self.rows.get(y, ()):
                if a < box[2] and box[0] < b:
                    return True
        return False

    # -- transforms -------------------------------------------------------------------------
    def moved(self, dx, dy):
        dx, dy = int(dx), int(dy)
        if not dx and not dy:
            return self
        f = Frame({y + dy: tuple((a + dx, b + dx) for a, b in runs)
                   for y, runs in self.rows.items()})
        if self._claim is not None:
            c = self._claim
            f = f.boxed((c[0] + dx, c[1] + dy, c[2] + dx, c[3] + dy))
        return f

    def turn(self, rot, size=None):
        """The frame turned ``rot`` quarter turns clockwise about the origin, as ``compose.turn``
        turns a point of the box ``size`` = (w, h) from the origin (the turned box's top-left
        back at (0, 0)); ``size`` defaults to the frame's own box from the origin. A box stays a
        box; a polygon lands where turning its bounding box puts it."""
        rot = int(rot) % 4
        if not rot or self.box is None:
            return self
        w, h = size if size is not None else (self.box[2], self.box[3])
        if self.is_box and self.box[0] == 0 and self.box[1] == 0 and size is None:
            return Frame.from_box(h, w) if rot % 2 else self
        rows = {}
        for y, runs in self.rows.items():
            for a, b in runs:
                if rot == 2:
                    rows.setdefault(h - 1 - y, []).append((w - b, w - a))
                elif rot == 1:          # (x, y) -> (h - 1 - y, x): a run becomes a column
                    nx = h - 1 - y
                    for x in range(a, b):
                        rows.setdefault(x, []).append((nx, nx + 1))
                else:                   # rot 3: (x, y) -> (y, w - 1 - x)
                    for x in range(a, b):
                        rows.setdefault(w - 1 - x, []).append((y, y + 1))
        return Frame(rows)

    def unturn(self, rot, size):
        """The inverse of ``turn(rot, size)``: ``f.turn(r, s).unturn(r, s) == f`` for any tile set,
        tiles outside the box included (43-hull: an achieved hull read back into the module's
        own frame). ``size`` is the unturned frame's (w, h), as ``turn`` took it."""
        rot = int(rot) % 4
        if not rot or self.box is None:
            return self
        w, h = size
        return self.turn((4 - rot) % 4, (h, w) if rot % 2 else (w, h))

    def minus(self, other):
        """The tiles of this frame that ``other`` does not hold (what a module left free)."""
        rows = {}
        for y, mine in self.rows.items():
            theirs = other.rows.get(y)
            if not theirs:
                rows[y] = list(mine)
                continue
            got = []
            for a, b in mine:
                cur = a
                for c, d in theirs:
                    if d <= cur or c >= b:
                        continue
                    if c > cur:
                        got.append((cur, c))
                    cur = max(cur, d)
                if cur < b:
                    got.append((cur, b))
            if got:
                rows[y] = got
        return Frame(rows)

    def grow(self, n):
        """The frame grown by ``n`` tiles on every side (a square neighbourhood); ``n`` 0 is the
        frame itself."""
        n = int(n)
        if n <= 0 or self.box is None:
            return self
        rows = {}
        for y, runs in self.rows.items():
            wide = [(a - n, b + n) for a, b in runs]
            for yy in range(y - n, y + n + 1):
                rows.setdefault(yy, []).extend(wide)
        return Frame(rows)

    def clip(self, box):
        """The tiles inside ``box`` (x0, y0, x1, y1)."""
        return self.overlap(Frame.from_box(*box))

    # -- printing ---------------------------------------------------------------------------
    def rows_text(self, box=None):
        """Rows of ``#`` (a tile of the frame) and ``.`` over ``box`` (default the bounding
        box), top row first."""
        box = box or self.box
        if box is None:
            return []
        x0, y0, x1, y1 = box
        out = []
        for y in range(y0, y1):
            line = ["."] * (x1 - x0)
            for a, b in self.rows.get(y, ()):
                for x in range(max(a, x0), min(b, x1)):
                    line[x - x0] = "#"
            out.append("".join(line))
        return out

    def __str__(self):
        return "\n".join(self.rows_text())
