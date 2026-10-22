"""fkcore.sense: what the agent learns when it looks at an area (CORE-V1 §4.6, §6.4, §6.5), pure.

``sense(surface, live, cat, area, policy)`` compares the composed layout (``compose.Surface``)
with a live scene (``scene.from_capture`` of the game link's ``snapshot(area)``) inside ``area``
only. That is fair play's attention: nothing outside the area is read or reported.

Every layout entity in the area gets one verdict, matched to the world by position + name:

- ``OK``: there, as designed;
- ``GHOST``: its ghost is there (pending);
- ``DRIFT``: there, but turned, the other underground end, or another recipe;
- ``WRONG``: another entity stands on its tiles;
- ``MISSING``: nothing there (never built, or destroyed: the next apply restores it).

A carrier that holds an item (or a fluid) its net doesn't expect is also ``WRONG_ITEM``; when the
toolkit's record (``own``) shows it was pasted under another net, the verdict says so
(``renet``): the next apply takes it up and lays it fresh (1.2). Where a ghost stands on an
entity ordered for deconstruction, the ghost is the design's (the entity is being replaced).
Every world entity in the area that no layout entity explains is one of:

- ``CLAIMED``: inside a claim;
- ``MARKED``: under a mark;
- a foreign change, handled by the surface's watch policy for its region (plots: ``keep``,
  sanctioned space: ``mark <duration>``, or ``revert`` / ``strict``). It is attributed to its
  ``last_user``. ``keep`` and ``mark`` write a mark (``<actor>@<tick>``, its tiles, no expiry for
  keep), so the next look says ``MARKED``, not ``NOBODY``. One actor's ``keep`` and ``mark`` in
  one look are two marks, so a name already taken (in this look or on the surface) gets a
  suffix, ``<actor>@<tick>.2``. ``revert`` leaves it ``NOBODY`` for the next apply to
  steamroll, and ``strict`` leaves it ``NOBODY``, loud.

The toolkit's own entities (``own``, the record of what the applies pasted, ``fkcore.own``) are
no foreign change: one the design has dropped is ``NOBODY`` (the next apply removes it) whatever
the policy says, unless a claim or a mark covers it or a player touched it (a ``last_user``).

Enemies and nature (neutral force) are separate and never judged. Each foreign change gets a
"changes here" line with who, what and a hint: built by a player; an unkeyed ghost; a carrier next
to net N, which looks like a fix to it (offer ``adopt``). Expired marks are listed for clearing.
With notify ``nearby`` (play) the lines are only this look's report. With ``all`` (lab) they are
also returned as ``push``, for chat and the owner's inbox. Stdlib only; nothing here talks to the
game.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import fkp as fkpmod

__all__ = ["Verdict", "SenseReport", "sense", "duration_ticks"]

TICKS_PER_S = 60
_CARRIERS = fkpmod.CARRIER_TYPES
_DIRECTIONAL = {"transport-belt", "underground-belt", "splitter", "inserter", "pipe-to-ground",
                "pump", "mining-drill", "offshore-pump", "boiler", "generator"}


@dataclass
class Verdict:
    verdict: str
    name: str
    x: float
    y: float
    key: str | None = None            # the layout key, or the claim/mark that explains it
    detail: str = ""
    actor: str | None = None
    action: str | None = None         # mark | keep | revert | strict | own, for a foreign change
    wrong_items: list = field(default_factory=list)
    renet: str | None = None          # the net the toolkit pasted this carrier under, if another
    ghost: bool = False               # NOBODY: an unbuilt ghost, not a built entity (2.0)

    def __str__(self):
        where = f"{_fmt(self.x)},{_fmt(self.y)}"
        who = f" by {self.actor}" if self.actor else ""
        text = f"{self.verdict:<8} {self.name} {where}" + (f" {self.key}" if self.key else "")
        if self.detail:
            text += f": {self.detail}"
        if self.wrong_items:
            text += f"; WRONG_ITEM {', '.join(self.wrong_items)}"
            if self.renet:
                text += (f" (laid under net {self.renet} before: the next apply takes it up and "
                         "lays it fresh)")
        return text + (who if self.verdict in ("MARKED", "NOBODY") and self.actor else "")


@dataclass
class SenseReport:
    area: list
    tick: int | None
    verdicts: list                    # [Verdict]
    marks: list                       # new fkp.Mark rows to write into the surface .fkp
    changes: list                     # "changes here" lines
    expired: list                     # names of marks past their expiry, inside the area
    push: list                        # lines to push (notify all), else []
    owners: dict                      # live thing index -> owner word (for the render)

    def counts(self):
        out = {}
        for v in self.verdicts:
            out[v.verdict] = out.get(v.verdict, 0) + 1
            if v.wrong_items:
                out["WRONG_ITEM"] = out.get("WRONG_ITEM", 0) + 1
        return out

    def lines(self):
        c = self.counts()
        head = (f"sense {_area_text(self.area)} tick {self.tick}: "
                + (", ".join(f"{k} {c[k]}" for k in sorted(c)) or "nothing here"))
        # a carrier with stale items is listed too, so a look says where they are (1.1)
        out = [head] + [f"  {v}" for v in self.verdicts if v.verdict != "OK" or v.wrong_items]
        if self.changes:
            out += ["changes here:"] + [f"  {l}" for l in self.changes]
        if self.marks:
            out += [f"new mark {m.name}: {len(m.tiles)} tiles"
                    + (f", until {m.until}" if m.until is not None else ", kept until decided")
                    for m in self.marks]
        out += [f"expired mark {name}: list it for clearing" for name in self.expired]
        return out


#: a ``mark`` with no duration (the surface file's default ``watch sanctioned: mark``) lasts 2h,
#: CORE-V1 §6.4's default; without it the mark expired at its own tick (worker sense, 2026-10-20)
DEFAULT_MARK = "2h"


def duration_ticks(text):
    """'2h', '30min', '90s' -> ticks (60 per second); None for no duration."""
    if not text:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(h|min|m|s)", text.strip())
    if not m:
        raise ValueError(f"a duration is like 2h, 30min or 90s, got {text!r}")
    per = {"h": 3600, "min": 60, "m": 60, "s": 1}[m.group(2)]
    return int(round(float(m.group(1)) * per * TICKS_PER_S))


def _fmt(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def _area_text(area):
    return "area " + ",".join(str(int(a)) for a in area) if area else "everywhere"


def _in_area(tiles, area):
    if area is None:
        return True
    return any(area[0] <= t[0] < area[2] and area[1] <= t[1] < area[3] for t in tiles)


def _policy(text):
    """'mark 2h' -> ('mark', '2h'); 'keep' -> ('keep', None)."""
    parts = (text or "").split()
    return (parts[0] if parts else "strict"), (parts[1] if len(parts) > 1 else None)


def sense(surface, live, cat, area, policy, tick=None, net_items=None, own=None) -> SenseReport:
    """``policy``: a ``surface.SurfaceFile`` (its watch and notify settings) or a dict
    {"plots": "keep", "sanctioned": "mark 2h", "notify": "nearby"}. ``net_items``: {net: items}
    for WRONG_ITEM, with surface net names (``<factory>/<net>``). ``own``: the toolkit's own
    entities ({``own.at``: ``own.Row``}, ``fkcore.own.load``), or None."""
    if hasattr(policy, "watch"):
        watch, notify = dict(policy.watch), policy.notify_mode
    else:
        watch = {"plots": policy.get("plots", "keep"),
                 "sanctioned": policy.get("sanctioned", "mark 2h")}
        notify = policy.get("notify", "nearby")
    tick = live.get("tick") if tick is None else tick
    things = [t for t in live["things"] if _in_area(t["tiles"], area)]
    owners = {}
    for i, t in enumerate(things):
        if t["force"] == "enemy":
            owners[i] = "enemy"
        elif t["force"] == "neutral":
            owners[i] = "nature"
    judged = [i for i in range(len(things)) if i not in owners]
    at_pos, at_tile = {}, {}
    for i in judged:
        t = things[i]
        at_pos.setdefault((t["name"], round(t["x"], 3), round(t["y"], 3)), []).append(i)
        for tile in t["tiles"]:
            at_tile.setdefault(tuple(tile), []).append(i)

    used, verdicts = set(), []
    layout = [e for k, e in sorted(surface.entities.items()) if _in_area(e.tiles, area)]
    for e in layout:
        cands = [i for i in at_pos.get((e.name, round(float(e.x), 3), round(float(e.y), 3)), ())
                 if i not in used]
        if cands:
            # an entity first, then a ghost; one ordered for deconstruction last: a ghost on it
            # is its replacement (a carrier laid fresh under another net, 1.2)
            i = min(cands, key=lambda c: (bool(things[c]["decon"]), bool(things[c]["ghost"])))
            used.add(i)
            t = things[i]
            owners[i] = e.key.rsplit("/", 1)[0]
            if t["ghost"]:
                verdicts.append(Verdict("GHOST", e.name, e.x, e.y, e.key, "pending"))
                continue
            drift = _drift(e, t, cat)
            v = Verdict("DRIFT" if drift else "OK", e.name, e.x, e.y, e.key, drift)
            net = _net(e)
            if net and net_items and net in net_items and cat.kind(e.name) in _CARRIERS:
                wrong = sorted(set(t["items"]) - set(net_items[net]))
                v.wrong_items = wrong
                row = own.get((e.name, round(float(e.x), 3), round(float(e.y), 3))) if own else None
                if row is not None and row.net and row.net != net:
                    v.renet = row.net
            verdicts.append(v)
            continue
        others = sorted({i for tile in e.tiles for i in at_tile.get(tuple(tile), ()) if i not in used})
        if others:
            names = ", ".join(sorted({things[i]["name"] for i in others}))
            verdicts.append(Verdict("WRONG", e.name, e.x, e.y, e.key, f"{names} stands there"))
            continue
        verdicts.append(Verdict("MISSING", e.name, e.x, e.y, e.key,
                                "not built or destroyed; the next apply restores it"))

    pending, changes = {}, []         # (actor, action) -> the mark it writes, named at the end
    carrier_tiles = {}
    for e in surface.entities.values():
        if e.attrs.get("net") and cat.kind(e.name) in _CARRIERS:
            for tile in e.tiles:
                carrier_tiles[tuple(tile)] = _net(e)
    for i in judged:
        if i in used:
            continue
        t = things[i]
        kind, detail = surface.whose(t["x"], t["y"])
        if kind == "claim":
            owners[i] = detail["key"]
            verdicts.append(Verdict("CLAIMED", t["name"], t["x"], t["y"], detail["key"]))
            continue
        if kind == "mark":
            owners[i] = detail["key"]
            verdicts.append(Verdict("MARKED", t["name"], t["x"], t["y"], detail["key"],
                                    actor=detail["key"].rsplit("/", 1)[1].split("@")[0]))
            continue
        cx, cy = math.floor(t["x"]), math.floor(t["y"])
        in_plot = any(p.x <= cx < p.x + p.w and p.y <= cy < p.y + p.h
                      for p in surface.plots.values())
        region = "plots" if in_plot else "sanctioned"      # shared infra stands in sanctioned space
        action, dur = _policy(watch.get(region))
        actor = t.get("last_user") or "unknown"
        hint = _hint(t, cat, carrier_tiles)
        what = f"{'a ghost of ' if t['ghost'] else ''}{t['name']} at {_fmt(t['x'])},{_fmt(t['y'])}"
        mine = own.get((t["name"], round(t["x"], 3), round(t["y"], 3))) if own else None
        if mine is not None and not t.get("last_user"):
            owners[i] = "NOBODY"
            why = ("ordered out: robots take it up" if t.get("decon") else
                   "dropped from the design: the next apply removes it")
            verdicts.append(Verdict("NOBODY", t["name"], t["x"], t["y"], mine.key,
                                    f"the toolkit's own, {why}", None, "own",
                                    ghost=bool(t["ghost"])))
            changes.append(f"{what}: the toolkit's own ({mine.key}), {why.split(':')[0]} "
                           f"({region}); {why.split(': ')[1]}")
            continue
        if action in ("mark", "keep"):
            p = pending.setdefault((actor, action), {
                "mark": fkpmod.Mark(None, [], None if action == "keep" else
                                    (None if tick is None else
                                     tick + duration_ticks(dur or DEFAULT_MARK))),
                "verdicts": [], "things": []})
            for tile in t["tiles"]:
                if (tile[0], tile[1]) not in p["mark"].tiles:
                    p["mark"].tiles.append((tile[0], tile[1]))
            v = Verdict("MARKED", t["name"], t["x"], t["y"], None,
                        "kept in the plot until its owner decides" if action == "keep"
                        else f"TEMP {actor}, marked for {dur or DEFAULT_MARK}", actor, action)
            p["verdicts"].append(v)
            p["things"].append(i)
            verdicts.append(v)
        else:
            owners[i] = "NOBODY"
            verdicts.append(Verdict("NOBODY", t["name"], t["x"], t["y"], None,
                                    "the next apply removes it" if action == "revert" else
                                    "unattributed (strict)", actor, action,
                                    ghost=bool(t["ghost"])))
        changes.append(f"{what}: {'built by ' + actor if actor != 'unknown' else 'no last_user'}"
                       f" ({region}, {action}){'; ' + hint if hint else ''}")
    marks, taken = [], set(surface.marks)
    for actor_action in sorted(pending):
        p = pending[actor_action]
        name, n = f"{actor_action[0]}@{tick}", 2
        while name in taken:
            name, n = f"{actor_action[0]}@{tick}.{n}", n + 1
        taken.add(name)
        p["mark"].name = name
        for v in p["verdicts"]:
            v.key = f"{surface.name}:mark/{name}"
        for i in p["things"]:
            owners[i] = f"{surface.name}:mark/{name}"
        marks.append(p["mark"])
    expired = sorted(m.name for m in surface.marks.values()
                     if m.until is not None and tick is not None and m.until < tick
                     and _in_area([(math.floor(x), math.floor(y)) for x, y in m.tiles], area))
    push = list(changes) if notify == "all" else []
    return SenseReport(list(area) if area else None, tick, verdicts, marks, changes, expired,
                       push, owners)


def _net(e):
    """A carrier's net as the surface names it: ``<factory>/<net>`` (nets never leave a factory)."""
    net = e.attrs.get("net")
    if not net:
        return None
    return f"{e.plot}/{net}" if getattr(e, "plot", None) else net


def _drift(e, t, cat):
    out = []
    kind = cat.kind(e.name)
    want_dir = e.dir or 0
    if (kind in _DIRECTIONAL or e.dir is not None) and int(t["direction"]) != int(want_dir):
        out.append(f"faces {int(t['direction'])}, designed {int(want_dir)}")
    want_ug = {"in": "input", "out": "output"}.get(e.attrs.get("ug"))
    if want_ug and t["ug"] and t["ug"] != want_ug:
        out.append(f"underground {t['ug']}, designed {want_ug}")
    want_recipe = e.attrs.get("recipe")
    # a furnace picks its recipe from what it is fed: the game reports none while it is idle, and
    # there is no setting to compare (found by the first in-game diff, 2026-10-20: 22 false DRIFTs)
    if want_recipe and kind != "furnace" and t["recipe"] != want_recipe:
        out.append(f"recipe {t['recipe']}, designed {want_recipe}")
    return "; ".join(out)


def _hint(t, cat, carrier_tiles):
    if t["ghost"]:
        return "an unkeyed ghost: robots will build it"
    if cat.has_entity(t["name"]) and cat.kind(t["name"]) in _CARRIERS:
        near = set()
        for x, y in t["tiles"]:
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in carrier_tiles:
                    near.add(carrier_tiles[(nx, ny)])
        if near:
            return (f"next to net {', '.join(sorted(near))}: looks like a fix to it (adopt "
                    "it into the source, or revert it)")
    return ""
