"""fkcore.own: the toolkit's own entities, the record of what the applies pasted (1.2).

The world can't say which entities are the toolkit's: robots build a pasted ghost with no
last_user, as they built the kit. ``out/own/<surface>.json`` remembers them: every composed entity
an apply pasted (its key, name, position, direction and, for a carrier, its surface net
``<factory>/<net>``). With it:

- an entity of the toolkit's that the design has dropped (a row replaced, a plot moved, shrunk or
  emptied, a place line removed) is ``NOBODY`` in a diff or a look, whatever the watch policy
  says, and the next apply orders it out, an unbuilt ghost included (``fkcore.sense``). A player
  who touched it (a ``last_user``) makes it a foreign change again, under the policy. The 0534 run
  (2026-10-20) kept its own dropped rows under ``watch plots: keep``, left 166 entities standing
  outside every plot after a plot move, and 28 ghosts after a factory was emptied;
- a carrier laid again under another net is known by the net it was pasted under (``nets``).

The record is seeded once, when there is none, from the .fkp files last written (``seed``: the
flow's write_layout does it before writing the new ones, so a run upgraded from 1.1 starts from
what it built, and drops nothing it dropped before). Each play apply updates it (``update``):
inside the apply's scope it becomes the design that was pasted, plus the toolkit's dropped
entities that still stood (ordered out; robots take them up); outside the scope it stays. Pure
but for ``load`` and ``save``; stdlib only.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import compose
from . import fkp as fkpmod

__all__ = ["Row", "at", "path", "load", "save", "rows_of", "seed", "dropped", "in_scope",
           "update", "nets"]


@dataclass(frozen=True)
class Row:
    key: str                          # the composed key it was pasted under
    name: str
    x: float
    y: float
    dir: int | None = None
    net: str | None = None            # a carrier's surface net, "<factory>/<net>"


def at(name, x, y):
    """The record's index: name and position, as a diff matches the world."""
    return (name, round(float(x), 3), round(float(y), 3))


def path(game, surface):
    return os.path.join(game, "out", "own", f"{surface}.json")


def load(game, surface):
    """The record {at: Row}, or None when there is none yet."""
    p = path(game, surface)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    out = {}
    for key, name, x, y, d, net in data.get("rows") or ():
        row = Row(key, name, x, y, d, net)
        out[at(name, x, y)] = row
    return out


def save(game, surface, record):
    p = path(game, surface)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    rows = sorted(record.values(), key=lambda r: (fkpmod.natural_key(r.key), r.x, r.y))
    head = json.dumps({"surface": surface,
                       "about": "the toolkit's own entities: what the applies pasted (fkcore.own)"})
    body = ",\n".join(json.dumps([r.key, r.name, r.x, r.y, r.dir, r.net]) for r in rows)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head[:-1] + ', "rows": [\n' + body + ("\n" if body else "") + "]}\n")


def _net(e):
    net = e.attrs.get("net")
    if not net:
        return None
    return f"{e.plot}/{net}" if e.plot else net


def rows_of(s):
    """{at: Row} of every entity of a composed surface (``compose.Surface``)."""
    out = {}
    for key in sorted(s.entities, key=fkpmod.natural_key):
        e = s.entities[key]
        out[at(e.name, e.x, e.y)] = Row(key, e.name, e.x, e.y, e.dir, _net(e))
    return out


def seed(game, surface, cat):
    """The record as the .fkp files on disk (the last written) compose: the surface .fkp's plots
    and shared infrastructure, each plot's module .fkp. {} when nothing is written yet."""
    sp = os.path.join(game, f"{surface}.fkp")
    if not os.path.exists(sp):
        return {}
    slay = fkpmod.load(sp)
    factories = {}
    for name, p in slay.plots.items():
        fp = os.path.join(game, f"{p.params.get('module', name)}.fkp")
        if os.path.exists(fp):
            lay = fkpmod.load(fp)
            lay.name = name
            factories[name] = lay
    return rows_of(compose.compose(slay, factories, cat))


def dropped(record, s):
    """The record's rows that the composed design ``s`` no longer holds (by name and position)."""
    design = {at(e.name, e.x, e.y) for e in s.entities.values()}
    return [row for k, row in sorted((record or {}).items(), key=lambda kv: kv[1].key)
            if k not in design]


def in_scope(row, cat, area=None, keys=None):
    """True when ``row`` is inside an apply's scope: a tile in ``area`` and a key prefix in
    ``keys`` (None = everywhere)."""
    if keys and not any(row.key.startswith(k) for k in keys):
        return False
    if area is None:
        return True
    try:
        tiles = cat.tiles(row.name, float(row.x), float(row.y), row.dir or 0)
    except (KeyError, ValueError):
        tiles = [(int(float(row.x) // 1), int(float(row.y) // 1))]
    return any(area[0] <= t[0] < area[2] and area[1] <= t[1] < area[3] for t in tiles)


def update(record, s, cat, area=None, keys=None, standing=()):
    """The record after an apply of ``s`` in this scope: outside it, as it was; inside it, the
    design that was pasted, plus the rows in ``standing`` (the toolkit's dropped entities that
    still stood, now ordered out: an index ``at``)."""
    record = record or {}
    out = {k: row for k, row in record.items() if not in_scope(row, cat, area, keys)}
    for k, row in rows_of(s).items():
        if in_scope(row, cat, area, keys):
            out[k] = row
    for k in standing:
        if k in record and k not in out:
            out[k] = record[k]
    return out


def nets(record):
    """{at: surface net} of the record's carriers."""
    return {k: row.net for k, row in (record or {}).items() if row.net}
