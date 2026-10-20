"""fkcore.apply: the only world write (CORE: the writer rule), and the diff that judges it.

``apply(r, s, cat, area, mode)`` pastes the composed layout ``s`` (a ``compose.Surface``) inside
``area`` as one named blueprint. Every entity is keyed (``tags.src``), pole wires are derived, and
it goes through ``link.paste`` (superforced: ghosts go over what stands in the way, and the game
marks that for deconstruction). Then, by mode:

- ``play``: ghosts only; robots build them. A world entity in the area that the design does not
  explain and the watch policy leaves to the apply (``NOBODY``) is ordered for deconstruction;
  ``MARKED`` and ``CLAIMED`` ones stay. The paste must land where designed: a shifted paste is
  reported (``MISPLACED``), never cleaned up.
- ``lab``: the area's chunks are generated and charted first (a new surface has none), each drill
  row's designed resource is seeded under it (lab ground has no ore), a shifted paste is measured
  and pasted again, and the ghosts are revived at once (lab rules: free materials).

What the paste refuses (the game won't place an offshore pump from a blueprint: the kickoff
found it on 2026-10-18, the V1 rehearsal again) is placed as single ghosts, still keyed and
still built by robots (``placed_alone``).

``diff(r, s, cat, area, policy)`` is a snapshot of the area judged by ``sense``: after robots finish
(or a lab revive) it is all ``OK``, which is 1:1. Nothing here registers anything; every game
call is one RCON command with the link's 5 s timeout.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from . import codec, link, scene, sense
from .fkp import natural_key

__all__ = ["ApplyReport", "apply", "diff", "scope_rows", "scope_area", "force_for"]


@dataclass
class ApplyReport:
    surface: str
    force: str
    mode: str
    area: tuple
    design: int = 0                    # entities in the scope
    pasted: int = 0                    # what build_blueprint placed (new ghosts)
    present: int = 0                   # design entities now there, as ghost or built
    corrected: tuple | None = None     # the shift a lab paste was corrected by
    misplaced: int = 0                 # ghosts that are not where the design says (play)
    placed_alone: int = 0              # refused by the paste, placed as single ghosts
    decon: int = 0                     # NOBODY entities ordered for deconstruction (play)
    chunks: int = 0
    seeded: int = 0
    revived: int = 0
    revive_failed: int = 0
    seconds: float = 0.0
    notes: list = field(default_factory=list)

    def lines(self):
        a = ",".join(str(int(v)) for v in self.area)
        head = (f"apply {self.surface} area {a} ({self.mode}, force {self.force}): {self.design} "
                f"entities designed, {self.pasted} ghosts placed, {self.present} where designed")
        out = [head]
        if self.mode == "lab":
            out.append(f"  lab: {self.chunks} chunks generated, {self.seeded} ore tiles seeded, "
                       f"{self.revived} revived, {self.revive_failed} not revivable"
                       + (f", paste corrected by {self.corrected}" if self.corrected else ""))
        else:
            out.append(f"  play: {self.decon} NOBODY entities ordered for deconstruction; robots "
                       "build the ghosts")
        if self.placed_alone:
            out.append(f"  {self.placed_alone} the paste refused, placed one by one as ghosts")
        if self.misplaced:
            out.append(f"  MISPLACED {self.misplaced} ghosts are not where the design says")
        out += [f"  {n}" for n in self.notes]
        out.append(f"  {self.seconds:.1f} s")
        return out


def force_for(mode):
    return "lab" if mode == "lab" else "player"


def scope_rows(s, area=None, keys=None):
    """The codec rows of ``s`` inside ``area`` (any tile in it) and under a key prefix in ``keys``."""
    out = []
    for e in sorted(s.entities.values(), key=lambda e: natural_key(e.key)):
        if area is not None and not _touches(e.tiles, area):
            continue
        if keys and not any(e.key.startswith(k) for k in keys):
            continue
        out.append({"src": e.key, "name": e.name, "x": e.x, "y": e.y, "direction": e.dir,
                    "attrs": dict(e.attrs)})
    return out


def _touches(tiles, area):
    return any(area[0] <= t[0] < area[2] and area[1] <= t[1] < area[3] for t in tiles)


def scope_area(rows, cat, margin=2):
    """The bounding box of ``rows``' tiles, plus ``margin``."""
    xs, ys = [], []
    for r in rows:
        for x, y in cat.tiles(r["name"], float(r["x"]), float(r["y"]), r["direction"] or 0):
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return (min(xs) - margin, min(ys) - margin, max(xs) + 1 + margin, max(ys) + 1 + margin)


def _anchor(rows, cat):
    """Where build_blueprint is called so every entity lands on its own position: the centre of
    the rows' tile box (the game centres a blueprint on the cursor; found exact on the lab bench)."""
    x0, y0, x1, y1 = scope_area(rows, cat, margin=0)
    return (x0 + x1) / 2, (y0 + y1) / 2


def _things(cap):
    want = {}
    for t in cap["things"]:
        want.setdefault((t["n"], float(t["x"]), float(t["y"])), []).append(bool(t["g"]))
    return want


def diff(r, s, cat, area, policy, net_items=None, tag="diff"):
    """Snapshot ``area`` and judge it against the design: a ``sense.SenseReport``."""
    live = scene.from_capture(link.snapshot(r, s.name, area, tag))
    return sense.sense(s, live, cat, list(area), policy, net_items=net_items)


def apply(r, s, cat, area=None, mode="play", force=None, label=None, policy=None, keys=None,
          net_items=None, tag="apply") -> ApplyReport:
    """Paste the design inside ``area`` (default: all of ``s``) as one named blueprint."""
    t0 = time.time()
    rows = scope_rows(s, area, keys)
    if area is None:
        area = scope_area(rows, cat) or (0, 0, 0, 0)
    force = force or force_for(mode)
    rep = ApplyReport(s.name, force, mode, tuple(area), design=len(rows))
    if not rows:
        rep.notes.append("nothing designed in this scope")
        return rep
    if mode == "lab":
        cx, cy = (area[0] + area[2]) / 2, (area[1] + area[3]) / 2
        radius = max(1, math.ceil(max(area[2] - area[0], area[3] - area[1]) / 64) + 1)
        rep.chunks = int(r.lua(link.lua_generate(s.name, force, (cx, cy), radius)).strip() or 0)
        ore = {}
        for e in s.entities.values():
            if e.attrs.get("resource") and cat.kind(e.name) == "mining-drill" \
                    and _touches(e.tiles, area):
                ore.setdefault(e.attrs["resource"], []).extend(e.tiles)
        if ore:
            rep.seeded = int(r.lua(link.lua_seed(s.name, ore)).strip() or 0)
    elif policy is not None:
        before = diff(r, s, cat, area, policy, net_items, tag=f"{tag}-before")
        nobody = [(v.name, v.x, v.y) for v in before.verdicts if v.verdict == "NOBODY"]
        if nobody:
            rep.decon = int(r.lua(link.lua_decon_list(s.name, force, nobody)).strip() or 0)
    desc = f"fk apply {s.name} area {','.join(str(int(v)) for v in area)} ({len(rows)} entities)"
    bp = codec.blueprint(rows, description=desc, label=label or f"apply {s.name}",
                         wires=codec.pole_wires(rows, cat))
    at = _anchor(rows, cat)
    rep.pasted = _int(link.paste(r, s.name, force, bp, at))
    want = {(row["name"], float(row["x"]), float(row["y"])) for row in rows}
    seen = _things(link.snapshot(r, s.name, area, f"{tag}-ghosts"))
    rep.present = len(want & set(seen))
    ghosts = {k for k, gs in seen.items() if any(gs)}
    stray = ghosts - want
    if stray and mode == "lab" and rep.present < len(want):
        shift = _shift(stray, want)
        if shift:
            r.lua(link.lua_destroy(s.name, area, names=["entity-ghost"]))
            link.paste(r, s.name, force, bp, (at[0] - shift[0], at[1] - shift[1]))
            rep.corrected = shift
            seen = _things(link.snapshot(r, s.name, area, f"{tag}-ghosts"))
            rep.present = len(want & set(seen))
            stray = {k for k, gs in seen.items() if any(gs)} - want
    if mode != "lab":
        rep.misplaced = len(stray)
    refused = [row for row in rows
               if (row["name"], float(row["x"]), float(row["y"])) not in seen]
    if refused and not rep.misplaced:
        rep.placed_alone = _int(r.lua(link.lua_ghosts(s.name, force, refused)))
        if rep.placed_alone:
            seen = _things(link.snapshot(r, s.name, area, f"{tag}-ghosts"))
            rep.present = len(want & set(seen))
    if mode == "lab":
        got = r.lua(link.lua_revive(s.name, area)).split()
        rep.revived = int(got[0]) if got else 0
        rep.revive_failed = int(got[1]) if len(got) > 1 else 0
    rep.seconds = time.time() - t0
    return rep


def _int(text):
    try:
        return int(str(text).strip())
    except ValueError:
        return 0


def _shift(stray, want):
    """The most common offset between stray ghosts and design entities of the same name."""
    shifts = {}
    for n, x, y in stray:
        for wn, wx, wy in want:
            if wn == n and abs(wx - x) <= 3 and abs(wy - y) <= 3 and (wx, wy) != (x, y):
                shifts[(x - wx, y - wy)] = shifts.get((x - wx, y - wy), 0) + 1
    return max(shifts, key=shifts.get) if shifts else None
