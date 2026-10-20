"""fkcore.fkp: the layout record (.fkp v1) for a factory or a surface. Format: CORE.md "`.fkp` v1".

    fkp 1 factory <name> | fkp 1 surface <name>        the first line
    size <W>x<H>                                        a factory's frame: tiles 0..W-1, 0..H-1
    inst <path> <Kind> [k=v ...] at <x>,<y> rot <r> sig <sig>
    cover <name> <kind> [k=v ...]                       a coverage object (power, robots)
    plot <factory> at <x>,<y> rot <r> size <W>x<H> [k=v ...]
    claim <name> box <x0>,<y0> <x1>,<y1> [until <tick>] ["reason"]
    mark <actor@tick> tiles <x>,<y> ... [until <tick>]
    e <key> <prototype> <x>,<y> [<DIR>] [k=v ...]       one entity; DIR is N, NNE, NE ... NNW

A key is ``<owner>/<local>``; the owner is an inst path, ``~<net>`` or a cover name. The
canonical form (what :func:`dumps` writes) is the header, ``size``, then the records by kind and
name, then the ``e`` lines in natural key order; comments are dropped, because the .fkp is
tool-written. ``loads(dumps(x)) == x`` and ``dumps(loads(t)) == t`` for canonical ``t``.

:func:`invariants` lists what makes a layout malformed: two entities on a tile, an entity outside
the factory's size, an owner that does not resolve, a carrier with no net or two nets. The writer
(:func:`dumps` with ``cat``) refuses a layout that has any. Pure, stdlib only.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

__all__ = ["FkpError", "InvariantError", "Entity", "Inst", "Cover", "Plot", "Claim", "Mark",
           "Layout", "loads", "dumps", "load", "save", "invariants", "tiles_of", "DIRS",
           "CARRIER_TYPES", "natural_key", "fmt"]

DIRS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
_DIR = {d: i for i, d in enumerate(DIRS)}

#: Entity types that move a net's items: each must carry exactly one net (CORE.md invariants).
CARRIER_TYPES = frozenset({"transport-belt", "underground-belt", "splitter", "inserter", "pipe",
                           "pipe-to-ground", "pump", "loader", "loader-1x1", "linked-belt"})


class FkpError(ValueError):
    def __init__(self, where, msg):
        super().__init__(f"{where}: {msg}")
        self.where, self.msg = where, msg


class InvariantError(ValueError):
    def __init__(self, problems):
        super().__init__("refusing to write a malformed layout:\n  " + "\n  ".join(problems))
        self.problems = problems


@dataclass
class Entity:
    key: str
    name: str
    x: float
    y: float
    dir: int | None = None
    attrs: dict = field(default_factory=dict)       # recipe, net, ug, ... -> str

    @property
    def owner(self):
        return self.key.rsplit("/", 1)[0] if "/" in self.key else ""

    @property
    def net(self):
        return self.attrs.get("net")


@dataclass
class Inst:
    path: str
    kind: str
    params: dict
    x: float
    y: float
    rot: int
    sig: str


@dataclass
class Cover:
    name: str
    kind: str
    params: dict


@dataclass
class Plot:
    factory: str
    x: int
    y: int
    rot: int
    w: int
    h: int
    params: dict = field(default_factory=dict)

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass
class Claim:
    name: str
    x0: int
    y0: int
    x1: int
    y1: int
    until: int | None = None
    reason: str = ""


@dataclass
class Mark:
    name: str                                     # actor@tick
    tiles: list                                   # [(x, y)]
    until: int | None = None


@dataclass
class Layout:
    level: str                                    # "factory" | "surface"
    name: str
    size: tuple | None = None                     # (W, H), factories only
    insts: dict = field(default_factory=dict)
    covers: dict = field(default_factory=dict)
    plots: dict = field(default_factory=dict)
    claims: dict = field(default_factory=dict)
    marks: dict = field(default_factory=dict)
    entities: dict = field(default_factory=dict)  # key -> Entity

    def add(self, e: Entity):
        if e.key in self.entities:
            raise FkpError(e.key, "duplicate key")
        self.entities[e.key] = e
        return e


# -- formatting -----------------------------------------------------------------------------------
def fmt(v):
    v = float(v)
    if v == int(v):
        return str(int(v))
    return repr(v)


def _num(s, where):
    try:
        v = float(s)
    except ValueError:
        raise FkpError(where, f"not a number: {s!r}") from None
    return int(v) if v == int(v) and "." not in s else v


def _pair(s, where):
    parts = s.split(",")
    if len(parts) != 2:
        raise FkpError(where, f"expected x,y, got {s!r}")
    return _num(parts[0], where), _num(parts[1], where)


def _int(s, where):
    v = _num(s, where)
    if not isinstance(v, int):
        raise FkpError(where, f"expected a whole number, got {s!r}")
    return v


def _size(s, where):
    m = re.fullmatch(r"(\d+)x(\d+)", s)
    if not m:
        raise FkpError(where, f"expected WxH, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def _kv(tokens, where):
    out = {}
    for t in tokens:
        if "=" not in t or t.startswith("="):
            raise FkpError(where, f"expected key=value, got {t!r}")
        k, v = t.split("=", 1)
        if k in out:
            raise FkpError(where, f"{k} given twice")
        out[k] = v
    return out


def _kv_text(d, first=()):
    keys = [k for k in first if k in d] + sorted(k for k in d if k not in first)
    return [f"{k}={d[k]}" for k in keys]


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


# -- parse ----------------------------------------------------------------------------------------
def loads(text, path="<fkp>") -> Layout:
    lay = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip() if '"' not in raw else _strip_comment(raw)
        if not line:
            continue
        where = f"{path}:{n}"
        try:
            t = shlex.split(line, posix=True)
        except ValueError as exc:
            raise FkpError(where, str(exc)) from None
        if lay is None:
            if len(t) != 4 or t[0] != "fkp" or t[1] != "1" or t[2] not in ("factory", "surface"):
                raise FkpError(where, "the first line must be: fkp 1 factory|surface <name>")
            lay = Layout(t[2], t[3])
            continue
        head = t[0]
        try:
            if head == "size":
                if lay.level != "factory" or len(t) != 2:
                    raise FkpError(where, "size <W>x<H> belongs to a factory")
                lay.size = _size(t[1], where)
            elif head == "inst":
                i = t.index("at")
                if t[i + 2] != "rot" or t[i + 4] != "sig" or len(t) != i + 6:
                    raise FkpError(where, "inst <path> <Kind> [k=v ...] at x,y rot r sig s")
                x, y = _pair(t[i + 1], where)
                rec = Inst(t[1], t[2], _kv(t[3:i], where), x, y, _int(t[i + 3], where), t[i + 5])
                _put(lay.insts, rec.path, rec, where)
            elif head == "cover":
                _put(lay.covers, t[1], Cover(t[1], t[2], _kv(t[3:], where)), where)
            elif head == "plot":
                if lay.level != "surface" or t[2] != "at" or t[4] != "rot" or t[6] != "size":
                    raise FkpError(where, "plot <factory> at x,y rot r size WxH (surfaces only)")
                x, y = _pair(t[3], where)
                w, h = _size(t[7], where)
                _put(lay.plots, t[1], Plot(t[1], x, y, _int(t[5], where), w, h,
                                           _kv(t[8:], where)), where)
            elif head == "claim":
                if t[2] != "box":
                    raise FkpError(where, "claim <name> box x0,y0 x1,y1 [until t] [\"reason\"]")
                x0, y0 = _pair(t[3], where)
                x1, y1 = _pair(t[4], where)
                rest, until, reason = t[5:], None, ""
                if rest[:1] == ["until"]:
                    until, rest = _int(rest[1], where), rest[2:]
                if rest:
                    reason = rest[0]
                    if len(rest) > 1:
                        raise FkpError(where, "a claim takes one quoted reason")
                _put(lay.claims, t[1], Claim(t[1], x0, y0, x1, y1, until, reason), where)
            elif head == "mark":
                if t[2] != "tiles":
                    raise FkpError(where, "mark <actor@tick> tiles x,y ... [until t]")
                rest, until = t[3:], None
                if "until" in rest:
                    i = rest.index("until")
                    until, rest = _int(rest[i + 1], where), rest[:i]
                tiles = [_pair(p, where) for p in rest]
                _put(lay.marks, t[1], Mark(t[1], tiles, until), where)
            elif head == "e":
                x, y = _pair(t[3], where)
                rest, d = t[4:], None
                if rest and rest[0] in _DIR:
                    d, rest = _DIR[rest[0]], rest[1:]
                e = Entity(t[1], t[2], x, y, d, _kv(rest, where))
                if e.key in lay.entities:
                    raise FkpError(where, f"duplicate key {e.key}")
                lay.entities[e.key] = e
            else:
                raise FkpError(where, f"unknown line {head!r}")
        except IndexError:
            raise FkpError(where, f"incomplete {head} line") from None
    if lay is None:
        raise FkpError(path, "empty file: the first line must be: fkp 1 factory|surface <name>")
    return lay


def _strip_comment(raw):
    out, quoted = [], False
    for ch in raw:
        if ch == '"':
            quoted = not quoted
        elif ch == "#" and not quoted:
            break
        out.append(ch)
    return "".join(out).strip()


def _put(table, key, rec, where):
    if key in table:
        raise FkpError(where, f"{key} given twice")
    table[key] = rec


# -- write ----------------------------------------------------------------------------------------
def record_lines(lay: Layout) -> list:
    """Every line except the entities, in canonical order."""
    out = [f"fkp 1 {lay.level} {lay.name}"]
    if lay.size is not None:
        out.append(f"size {lay.size[0]}x{lay.size[1]}")
    for path in sorted(lay.insts, key=natural_key):
        r = lay.insts[path]
        out.append(" ".join(["inst", r.path, r.kind] + _kv_text(r.params)
                            + ["at", f"{fmt(r.x)},{fmt(r.y)}", "rot", str(r.rot), "sig", r.sig]))
    for name in sorted(lay.covers, key=natural_key):
        r = lay.covers[name]
        out.append(" ".join(["cover", r.name, r.kind] + _kv_text(r.params)))
    for name in sorted(lay.plots, key=natural_key):
        p = lay.plots[name]
        out.append(" ".join(["plot", p.factory, "at", f"{p.x},{p.y}", "rot", str(p.rot), "size",
                             f"{p.w}x{p.h}"] + _kv_text(p.params)))
    for name in sorted(lay.claims, key=natural_key):
        c = lay.claims[name]
        parts = ["claim", c.name, "box", f"{fmt(c.x0)},{fmt(c.y0)}", f"{fmt(c.x1)},{fmt(c.y1)}"]
        if c.until is not None:
            parts += ["until", str(c.until)]
        if c.reason:
            parts.append('"' + c.reason.replace('"', "'") + '"')
        out.append(" ".join(parts))
    for name in sorted(lay.marks, key=natural_key):
        m = lay.marks[name]
        parts = ["mark", m.name, "tiles"] + [f"{fmt(x)},{fmt(y)}" for x, y in m.tiles]
        if m.until is not None:
            parts += ["until", str(m.until)]
        out.append(" ".join(parts))
    return out


def entity_line(e: Entity) -> str:
    parts = ["e", e.key, e.name, f"{fmt(e.x)},{fmt(e.y)}"]
    if e.dir is not None:
        parts.append(DIRS[e.dir % 16])
    return " ".join(parts + _kv_text(e.attrs, first=("recipe", "net", "ug")))


def dumps(lay: Layout, cat=None) -> str:
    """The canonical text. With ``cat``, refuses a layout that breaks an invariant."""
    if cat is not None:
        problems = invariants(lay, cat)
        if problems:
            raise InvariantError(problems)
    lines = record_lines(lay)
    for key in sorted(lay.entities, key=natural_key):
        lines.append(entity_line(lay.entities[key]))
    return "\n".join(lines) + "\n"


def load(path) -> Layout:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read(), path)


def save(lay: Layout, path, cat):
    text = dumps(lay, cat)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# -- invariants -----------------------------------------------------------------------------------
def tiles_of(cat, e: Entity):
    return cat.tiles(e.name, float(e.x), float(e.y), e.dir if e.dir is not None else 0)


def invariants(lay: Layout, cat, nets=None) -> list:
    """Every invariant the layout breaks, as text lines (empty = well-formed).

    ``nets`` (the factory's net names, from its source) makes ``~net`` owners strict; without it a
    ``~net`` owner resolves when some carrier in the file carries that net.
    """
    problems = []
    carried = {e.net for e in lay.entities.values() if e.net}
    known_nets = set(nets) if nets is not None else carried
    owners = set(lay.insts) | set(lay.covers)
    taken = {}
    for key in sorted(lay.entities, key=natural_key):
        e = lay.entities[key]
        if not cat.has_entity(e.name):
            problems.append(f"{key}: unknown prototype {e.name}")
            continue
        owner = e.owner
        if not owner:
            problems.append(f"{key}: a key is <owner>/<local>")
        elif owner.startswith("~"):
            if owner[1:] not in known_nets:
                problems.append(f"{key}: owner {owner} is not a net of this factory")
        elif owner not in owners and not any(owner.startswith(p + "/") for p in lay.insts):
            problems.append(f"{key}: owner {owner} is not an inst or cover line")
        if cat.kind(e.name) in CARRIER_TYPES:
            net = e.net
            if not net:
                problems.append(f"{key}: a {e.name} carries no net")
            elif "," in net or "|" in net:
                problems.append(f"{key}: a {e.name} carries two nets ({net})")
        try:
            tiles = tiles_of(cat, e)
        except ValueError as exc:
            problems.append(f"{key}: {exc}")
            continue
        for t in sorted(tiles):
            if t in taken:
                problems.append(f"{key}: tile {t[0]},{t[1]} is already {taken[t]}")
            else:
                taken[t] = key
            if lay.size is not None and not (0 <= t[0] < lay.size[0] and 0 <= t[1] < lay.size[1]):
                problems.append(f"{key}: tile {t[0]},{t[1]} is outside the factory's "
                                f"{lay.size[0]}x{lay.size[1]} frame")
    return problems
