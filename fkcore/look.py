"""fkcore.look: the live look (CORE-V1 §4.6, §6.4, §6.5), an area of the composed layout vs the game.

``python -m fkcore look GAME --source world --area X0,Y0,X1,Y1`` composes the game codebase's
layout (``composed``), snapshots the area through the link (``link.snapshot``), judges it with
``sense.sense`` under the surface file's watch and notify settings, and prints the verdict
summary, every verdict that is not OK, the "changes here" list, and the live render next to the
design render (``compose.render_scene`` of ``scene.from_capture`` and of ``scene.design_scene``;
after a finished apply both render the same text: look parity). A built underground belt with no
partner (or with an end of the same kind, so no tunnel forms) also gets a warning line,
``UNPAIRED``, with its position: a report line, never a gate. ``--write-marks`` writes the new
marks into the surface ``.fkp``, as the offline ``sense`` command does, so the next look says
``MARKED`` for them.

Notify (the surface file's ``notify``, or ``--notify``):

- ``nearby`` (play default): the lines are only this look's report;
- ``all`` (lab default): they are also pushed, one game chat line per change, and appended to
  ``<game>/out/inbox.txt`` (``fkcore.notify``);
- ``off``: report only, nothing pushed.

Fair play: a look reads only its area. In play mode the area must be given; a lab look without
one covers everything designed (the lab's global diff). ``--watch`` overrides the watch policy for
one look (``strict``, or ``plots=keep,sanctioned=strict``). ``report`` is pure (the tests feed it
fixture captures); ``run`` uses the game link, which is on only with ``FK_LINK=on``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import compose, fkp, link, scene, sense
from . import notify as notifymod
from . import own as ownmod
from . import surface as surfacemod

__all__ = ["LookError", "Look", "composed", "net_items", "policy", "default_area", "report",
           "side_by_side", "unpaired", "run"]

_LAYOUT_VERDICTS = ("OK", "GHOST", "DRIFT", "WRONG", "MISSING")
_ACTIONS = ("keep", "revert", "strict", "mark")
#: Two renders side by side up to this many columns, else one above the other.
MAX_WIDTH = 160


class LookError(ValueError):
    pass


@dataclass
class Look:
    surface: str
    area: tuple
    policy: dict
    rep: sense.SenseReport
    design: str                      # the design render of the area
    live: str                        # the live render of the area
    pushed: list = field(default_factory=list)
    wrote: int = 0                   # marks written into the surface .fkp
    notes: list = field(default_factory=list)
    unpaired: list = field(default_factory=list)   # built underground ends with no partner

    @property
    def designed(self):
        """Layout entities in the area (each has one layout verdict; GHOST SHORT is a GHOST)."""
        return sum(1 for v in self.rep.verdicts if v.verdict.split()[0] in _LAYOUT_VERDICTS)

    @property
    def ok(self):
        return sum(1 for v in self.rep.verdicts if v.verdict == "OK")

    def lines(self):
        p = self.policy
        a = ",".join(str(int(v)) for v in self.area)
        out = [f"look {self.surface} --source world, area {a}, tick {self.rep.tick}: OK "
               f"{self.ok}/{self.designed} designed entities (notify {p['notify']}; watch plots "
               f"{p['plots']}, sanctioned {p['sanctioned']})"]
        out += self.rep.lines()
        out += [f"  UNPAIRED {u['name']} {scene.num(u['x'])},{scene.num(u['y'])} "
                f"({u['ug']}; {u['why']})" for u in self.unpaired]
        stale = sum(1 for v in self.rep.verdicts if v.wrong_items)
        relay = sum(1 for v in self.rep.verdicts if v.wrong_items and v.renet)
        if stale > relay:
            out.append(f"{stale - relay} belts or pipes here carry items their net doesn't "
                       f"(WRONG_ITEM): fk fresh {a} takes them up, and the next fk build lays "
                       "them fresh")
        if relay:
            out.append(f"{relay} belts or pipes here hold what the net they were laid under before "
                       "carried (WRONG_ITEM): the next fk build takes them up and lays them fresh "
                       "by itself")
        out += side_by_side(self.design, self.live, self.area)[0]
        if p["notify"] == "all":
            out.append(f"notify all: pushed {len(self.pushed)} line(s) to game chat and "
                       "out/inbox.txt")
        else:
            out.append(f"notify {p['notify']}: nothing pushed (the lines are this look's "
                       "report only)")
        if self.wrote:
            out.append(f"wrote {self.wrote} mark(s) into the surface .fkp")
        out += [f"note: {n}" for n in self.notes]
        return out


def composed(game, cat):
    """(surface file, surface .fkp, its path, the composed Surface) of a game codebase."""
    sf = surfacemod.load_game(game)
    lay_path = os.path.join(game, f"{sf.name}.fkp")
    surface_lay = fkp.load(lay_path) if os.path.exists(lay_path) else surfacemod.floorplan(sf)
    factories = {}
    for p in sf.places.values():
        path = os.path.join(game, f"{p.module}.fkp")
        if os.path.exists(path):
            lay = fkp.load(path)
            lay.name = p.factory
            factories[p.factory] = lay
    return sf, surface_lay, lay_path, compose.compose(surface_lay, factories, cat)


def net_items(game, sf, cat):
    """({<factory>/<net>: items}, notes) from each placed factory's source, for WRONG_ITEM."""
    from .elaborate import ElabError, elaborate_file
    from .lang import FkSyntaxError
    items, notes = {}, []
    for p in sf.places.values():
        src = os.path.join(game, f"{p.module}.fk")
        if p.lifecycle == "retired" or not os.path.exists(src):
            continue
        lay_path = os.path.join(game, f"{p.module}.fkp")
        try:
            lay = fkp.load(lay_path) if os.path.exists(lay_path) else None
            flat = elaborate_file(src, cat, name=p.module, layout=lay)
        except (FkSyntaxError, ElabError, OSError, fkp.FkpError) as exc:
            notes.append(f"{p.factory}: no netlist ({exc}); WRONG_ITEM is not checked there")
            continue
        for n, net in flat.nets.items():
            items[f"{p.factory}/{n}"] = list(net.items)
    return items, notes


def policy(sf, notify=None, watch=None):
    """The sense policy of one look: the surface file's, with ``notify`` / ``watch`` overrides."""
    w = dict(sf.watch)
    for part in (watch or "").split(","):
        if not part.strip():
            continue
        region, _, action = part.rpartition("=")
        action = action.strip()
        if not action or action.split()[0] not in _ACTIONS:
            raise LookError(f"a watch action is keep, revert, strict or mark [<duration>], "
                            f"got {action!r}")
        regions = [region.strip()] if region.strip() else ["plots", "sanctioned"]
        for r in regions:
            if r not in ("plots", "sanctioned"):
                raise LookError(f"a watch region is plots or sanctioned, got {r!r}")
            w[r] = action
    mode = notify or sf.notify_mode
    if mode not in ("nearby", "all", "off"):
        raise LookError(f"notify is nearby, all or off, got {mode!r}")
    return {"plots": w["plots"], "sanctioned": w["sanctioned"], "notify": mode}


def default_area(s, cat):
    """The tile box of everything designed on the surface, plus a 2-tile margin."""
    from .apply import scope_area
    return scope_area(s.rows(), cat)


def _ug_step(direction):
    """The unit step of a cardinal direction, or None (scene.DIRS; 0 N, 4 E, 8 S, 12 W)."""
    d = scene.DIRS.get(int(direction))
    return d[1] if d else None


def _ug_walk(t, index):
    """The first underground end ahead of ``t`` on its line (behind it for an output), same name
    and direction, within the tier's reach; the game's rule (CORE-V1 flow, and Factorio 2.0:
    both ends of a pair face the flow, so an input looks ahead and an output behind)."""
    step = _ug_step(t["direction"])
    if step is None:
        return None
    dx, dy = step
    if t["ug"] == "output":
        dx, dy = -dx, -dy
    x, y = float(t["x"]), float(t["y"])
    for k in range(1, int(scene.UG_MAX.get(t["name"], 5)) + 1):
        for other in index.get((round(x + k * dx, 2), round(y + k * dy, 2)), ()):
            if other is not t and other["name"] == t["name"] \
                    and int(other["direction"]) == int(t["direction"]):
                return other
    return None


def unpaired(live):
    """The built underground belts of a live scene with no partner: one dict each, with name,
    position, its end kind and why. The game's ``pair`` is trusted when the capture has it; on a
    capture without it the walk pairs an input ahead with an output (and an output behind with an
    input). A ghost is never judged: a ghost pair is not built, and a ghost is no partner. This is
    a warning in the look's report, never a gate."""
    index = {}
    for t in live["things"]:
        if t["type"] == "underground-belt" and not t["ghost"] \
                and t.get("ug") in ("input", "output"):
            key = (round(float(t["x"]), 2), round(float(t["y"]), 2))
            index.setdefault(key, []).append(t)
    out = []
    for t in live["things"]:
        if t["type"] != "underground-belt" or t["ghost"] \
                or t.get("ug") not in ("input", "output") or t.get("pair") is not None:
            continue
        other = _ug_walk(t, index)
        if other is None:
            why = f"no partner within {int(scene.UG_MAX.get(t['name'], 5))} tiles"
        elif other["ug"] == t["ug"]:
            why = (f"partner at {scene.num(other['x'])},{scene.num(other['y'])} is another "
                   f"{other['ug']}, so it points the same way")
        else:
            continue                      # a capture without `pair`: the walk found the partner
        out.append({"name": t["name"], "x": t["x"], "y": t["y"], "ug": t["ug"], "why": why})
    return out


def report(s, live, cat, area, pol, net_items=None, own=None) -> Look:
    """The look at ``area`` of the composed ``s`` against the ``live`` scene. Pure. ``own``: the
    toolkit's own entities (``fkcore.own``): those the design dropped read NOBODY."""
    area = tuple(int(v) for v in area)
    rep = sense.sense(s, live, cat, list(area), pol, net_items=net_items, own=own)
    design = compose.render_scene(scene.design_scene(s, cat, list(area)), cat, area)
    return Look(s.name, area, dict(pol), rep, design, compose.render_scene(live, cat, area),
                unpaired=unpaired(live))


def _rows(text, w, h):
    rows = text.split("\n") if text else []
    rows += [""] * (h - len(rows))
    return [r.ljust(w, ".") for r in rows[:h]]


def side_by_side(design, live, area, max_width=MAX_WIDTH):
    """-> (lines, tiles that differ): the two renders next to each other, each row labelled with
    its y; one above the other when two would not fit in ``max_width`` columns."""
    x0, y0, x1, y1 = (int(v) for v in area)
    w, h = x1 - x0, y1 - y0
    d, l = _rows(design, w, h), _rows(live, w, h)
    differ = sum(1 for dr, lr in zip(d, l) for a, b in zip(dr, lr) if a != b)
    out = [f"render: design | live, x {x0}..{x1 - 1}, y {y0}..{y1 - 1} (. a free tile): "
           f"{differ} tiles differ"]
    if 2 * w + 9 <= max_width:
        out += [f"{y0 + i:>5} {dr} | {lr}" for i, (dr, lr) in enumerate(zip(d, l))]
    else:
        out += ["design:"] + [f"{y0 + i:>5} {r}" for i, r in enumerate(d)]
        out += ["live:"] + [f"{y0 + i:>5} {r}" for i, r in enumerate(l)]
    return out, differ


def run(r, game, cat, area=None, notify=None, watch=None, write_marks=False, tag="look") -> Look:
    """Look at ``area`` of the game codebase ``game`` in the game: snapshot, sense, render; write
    the marks (``write_marks``) and push (notify all)."""
    sf, surface_lay, lay_path, s = composed(game, cat)
    if area is None:
        if sf.mode != "lab":
            raise LookError("fair play: a look in play mode needs --area X0,Y0,X1,Y1 (the agent "
                            "looks at an area)")
        area = default_area(s, cat)
        if area is None:
            raise LookError("nothing is designed on this surface")
    items, notes = net_items(game, sf, cat)
    pol = policy(sf, notify, watch)
    live = scene.from_capture(link.snapshot(r, sf.name, area, tag, keep=False))
    lk = report(s, live, cat, area, pol, items, ownmod.load(game, sf.name))
    ghosts = sorted({v.name for v in lk.rep.verdicts if v.verdict == "GHOST"})
    if ghosts:
        # a ghost that stays is a blocked build: say why (SHORT: the network holds none of the
        # item; LOCKED: its recipe is not researched), from the free supply read
        from . import supply
        from .apply import force_for
        try:
            sup = supply.read(r, getattr(sf, "force", None) or force_for(sf.mode), sf.name, ghosts)
            supply.mark_ghosts(lk.rep.verdicts, sup)
        except (OSError, link.LinkError) as exc:
            lk.notes.append(f"ghosts not judged against the network ({type(exc).__name__}: {exc})")
    lk.notes += notes + [f"composed surface: {p}" for p in s.problems]
    # 2.0.4: the verdicts judge against the .fkp files; say when the source moved on from them
    from .flow import layout_source_changes
    lk.notes += layout_source_changes(game)
    if write_marks and lk.rep.marks:
        for m in lk.rep.marks:
            surface_lay.marks[m.name] = m
        fkp.save(surface_lay, lay_path, cat)
        lk.wrote = len(lk.rep.marks)
    if lk.rep.push:
        lk.pushed = notifymod.push(r, game, sf.name, lk.rep.push, lk.rep.tick, "look")
    return lk
