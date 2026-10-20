"""fkcore.literal: entities from a blueprint or an entity list, as a Literal's pinned entities.

``Literal<file="plant-w3.json", box="x0,y0,x1,y1">`` (CORE-V1.md §5): every entity is written by
hand somewhere else, here a file in the game codebase. Two file shapes are read:

- the kickoff's entity list (``v4-hand/kickoff/plant-w3.json``): ``{"entities": [{name, wx, wy,
  d}, ...]}`` in world positions (``bx``/``by`` or ``x``/``y`` are accepted too);
- a blueprint string (a ``.txt`` holding one, or a JSON ``{"bp": "0e..."}`` without an entity
  list), read with ``fkcore.codec``.

``box`` keeps the entities whose position lies inside it (tile coordinates, x0 <= x < x1) and
makes its corner the Literal's frame origin, so a Literal placed at its plot's corner sits where
the file says. Without a box the frame starts at the entities' top-left tile.

Keys are ``<inst>/<prototype><k>`` in file order. Carriers get a net by connectivity, since a file
has no netlist: each group of touching pipes is ``<inst>/fluid<k>``, each group of touching belts
``<inst>/belt<k>``, each inserter ``<inst>/hand<k>`` (one inserter is a route). Rename them in source
when they matter. Pure, stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import math
import os

from . import fkp as fkpmod

__all__ = ["LiteralError", "read_entities", "import_entities", "signature"]

_DIRS = {0, 4, 8, 12}
_PIPES = ("pipe", "pipe-to-ground", "pump")
_BELTS = ("transport-belt", "underground-belt", "splitter", "loader", "loader-1x1")


class LiteralError(ValueError):
    pass


def read_entities(path):
    """[(name, x, y, dir)] from an entity-list JSON or a blueprint string file."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    rows = []
    data = None
    if path.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise LiteralError(f"{path}: not JSON ({exc})") from None
    if isinstance(data, dict) and isinstance(data.get("entities"), list):
        for e in data["entities"]:
            x = e.get("wx", e.get("bx", e.get("x")))
            y = e.get("wy", e.get("by", e.get("y")))
            if x is None and isinstance(e.get("position"), dict):
                x, y = e["position"]["x"], e["position"]["y"]
            d = e.get("d", e.get("direction"))
            rows.append((e["name"], float(x), float(y), None if d is None else int(d)))
        return rows
    from . import codec
    bp = data.get("bp") if isinstance(data, dict) else text.strip()
    try:
        got, _desc = codec.read_blueprint(bp)
    except codec.CodecError as exc:
        raise LiteralError(f"{path}: {exc}") from None
    return [(r["name"], float(r["x"]), float(r["y"]), r["direction"]) for r in got]


def _box(text):
    try:
        x0, y0, x1, y1 = (int(v) for v in str(text).split(","))
    except ValueError:
        raise LiteralError(f"box must be \"x0,y0,x1,y1\", got {text!r}") from None
    return x0, y0, x1, y1


def import_entities(path, inst, cat, box=None):
    """-> (entities in the Literal's own frame, frame size, frame origin in file coordinates)."""
    rows = read_entities(path)
    if box is not None:
        x0, y0, x1, y1 = _box(box)
        rows = [r for r in rows if x0 <= math.floor(r[1]) < x1 and y0 <= math.floor(r[2]) < y1]
    if not rows:
        raise LiteralError(f"{path}: no entities" + (f" inside box {box}" if box else ""))
    unknown = sorted({r[0] for r in rows if not cat.has_entity(r[0])})
    if unknown:
        raise LiteralError(f"{path}: prototypes the catalog lacks: {', '.join(unknown)}")
    tiles = [(r, cat.tiles(r[0], r[1], r[2], r[3] if r[3] is not None else 0)) for r in rows]
    if box is None:
        x0 = min(t[0] for _r, ts in tiles for t in ts)
        y0 = min(t[1] for _r, ts in tiles for t in ts)
        x1 = max(t[0] for _r, ts in tiles for t in ts) + 1
        y1 = max(t[1] for _r, ts in tiles for t in ts) + 1
    count, out = {}, []
    for (name, x, y, d), _ts in tiles:
        k = count.get(name, 0)
        count[name] = k + 1
        out.append(fkpmod.Entity(f"{inst}/{name}{k}", name, _clean(x - x0), _clean(y - y0),
                                 d if d in _DIRS or d is None else d, {}))
    _name_nets(out, inst, cat)
    return out, (x1 - x0, y1 - y0), (x0, y0)


def _name_nets(ents, inst, cat):
    """Give every carrier one net: touching pipes / belts group, each inserter alone."""
    by_tile = {}
    for e in ents:
        for t in fkpmod.tiles_of(cat, e):
            by_tile[t] = e
    groups = {"fluid": [], "belt": []}
    seen = set()
    for e in ents:
        kind = cat.kind(e.name)
        if kind == "inserter":
            e.attrs["net"] = f"{inst}/hand{sum(1 for x in ents[:ents.index(e)] if cat.kind(x.name) == 'inserter')}"
            continue
        family = "fluid" if e.name in _PIPES or kind in _PIPES else \
            "belt" if kind in _BELTS else None
        if family is None or e.key in seen:
            continue
        group, todo = [], [e]
        while todo:
            cur = todo.pop()
            if cur.key in seen:
                continue
            seen.add(cur.key)
            group.append(cur)
            for tx, ty in fkpmod.tiles_of(cat, cur):
                for nx, ny in ((tx + 1, ty), (tx - 1, ty), (tx, ty + 1), (tx, ty - 1)):
                    o = by_tile.get((nx, ny))
                    if o is None or o.key in seen:
                        continue
                    ok = cat.kind(o.name)
                    if (family == "fluid" and (o.name in _PIPES or ok in _PIPES)) or \
                            (family == "belt" and ok in _BELTS):
                        todo.append(o)
        net = f"{inst}/{family}{len(groups[family])}"
        groups[family].append(net)
        for g in group:
            g.attrs["net"] = net


def signature(ents, size):
    rows = sorted((e.key, e.name, float(e.x), float(e.y), e.dir) for e in ents)
    blob = json.dumps([rows, list(size)], separators=(",", ":"))
    return hashlib.sha1(blob.encode()).hexdigest()[:10]


def _clean(v):
    return int(v) if float(v).is_integer() else v


def resolve(fk_path, file):
    """A Literal's file, relative to the .fk that names it (inside the game codebase)."""
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(fk_path)), file))
