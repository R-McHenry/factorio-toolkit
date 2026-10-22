"""fkcore.apply: the only world write (CORE: the writer rule), and the diff that judges it.

``apply(r, s, cat, area, mode)`` pastes the composed layout ``s`` (a ``compose.Surface``) inside
``area`` as one named blueprint. Every entity is keyed (``tags.src``), pole wires are derived, and
it goes through ``link.paste`` (superforced: ghosts go over what stands in the way, and the game
marks that for deconstruction). Then, by mode:

- ``play``: ghosts only; robots build them. A world entity in the area that the design does not
  explain and the watch policy leaves to the apply (``NOBODY``) is ordered for deconstruction, an
  unbuilt ghost too (the game removes a ghost ordered out at once); ``MARKED`` and ``CLAIMED``
  ones stay. The paste must land where designed: a shifted paste is reported (``MISPLACED``),
  never cleaned up. Scaffolding (1.7, :func:`scaffold`): a ``NOBODY`` pole or roboport on no
  tile of the design stays up while the design's own poles (or roboports) in the area are not
  all built, so a rebuild doesn't cut power or the robot network; the first apply after they
  stand takes it up.
- ``own`` (1.2, ``fkcore.own``): the record of what the applies pasted. The toolkit's own
  entities that the design dropped are ``NOBODY`` whatever the watch policy says, so a moved,
  shrunk or emptied plot, or a replaced row, leaves nothing behind; with no ``area`` the scope
  reaches them wherever they stand. A carrier the record shows under another net that holds
  what its new net doesn't carry (``renet`` with ``WRONG_ITEM``: the old net's items on a belt,
  its fluid in a pipe) is ordered out before the paste, and the paste lays a fresh ghost on it:
  robots take the old one up with what it holds and build the new one (``relaid``; the game
  keeps both, checked on a laptop test server, 2.0.77). ``ApplyReport.own`` is the record after
  the paste, for the caller to save.
- ``lab``: the chunks under the area (and no others) are generated and charted first (a new
  surface has none), each drill row's designed resource is seeded under it (lab ground has no
  ore; ``seed=False`` when the surface has a real terrain, whose ore is already there), a
  shifted paste is measured and pasted again, and the ghosts are revived at once (lab rules:
  free materials).

What the paste refuses (the game won't place an offshore pump from a blueprint: the kickoff
found it on 2026-10-18, the V1 rehearsal again) is placed as single ghosts, still keyed and
still built by robots (``placed_alone``).

``diff(r, s, cat, area, policy)`` is a snapshot of the area judged by ``sense``: after robots finish
(or a lab revive) it is all ``OK``, which is 1:1. Nothing here registers anything; every game
call is one RCON command with the link's 5 s timeout.

The rip estimate (1.1, Rory 2026-10-20): what the next apply takes up (``rip_points`` of a diff:
NOBODY is ordered out, WRONG is pasted over), read with ``link.lua_rip_load``, and
``rip_report``: how many structures, the items they hold, and about how long the network's
construction robots need to carry it all to storage. A big one is a ``RIP`` check, with the way to
make it faster (stop the input and let the factory drain first) and, when the taken-up things come
back as new ghosts of the same names, the hint that a factory moved (``fk merge`` joins
factories where they stand).
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field

from . import codec, link, scene, sense
from . import own as ownmod
from .fkp import natural_key

__all__ = ["ApplyReport", "apply", "diff", "scope_rows", "scope_area", "default_area",
           "force_for", "scaffold", "rip_points", "rip_load", "rip_minutes", "moved",
           "rip_report"]

#: a rip worth a RIP check: this many minutes of robot time, or this many structures
RIP_WARN_MIN, RIP_WARN_N = 3.0, 100
#: what the next apply takes up: NOBODY is ordered for deconstruction, WRONG is pasted over
RIP_VERDICTS = ("NOBODY", "WRONG")
#: taken-up structures coming back as new ghosts of the same names: a factory moved
MOVED_N = 30
#: kinds an apply leaves standing until the design's own of that kind stand (1.7, scaffolding)
SCAFFOLD_KINDS = ("electric-pole", "roboport")


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
    dropped: int = 0                   # of them, the toolkit's own that the design dropped
    held: int = 0                      # NOBODY poles and roboports left up as scaffolding (1.7)
    hand: list = field(default_factory=list)   # placed by hand, replaced or removed (2.0)
    relaid: list = field(default_factory=list)   # carriers laid fresh under another net
    own: dict | None = None            # the record of what the applies pasted, after this one
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
            out.append(f"  play: {self.decon} NOBODY entities ordered for deconstruction"
                       + (f" ({self.dropped} of them the toolkit's own, dropped from the design)"
                          if self.dropped else "") + "; robots build the ghosts")
            if self.held:
                out.append(f"  scaffold: {self.held} old poles and roboports stay up until the "
                           "design's own stand here, so power and robots keep running; the "
                           "first apply after that takes them up")
            if self.hand:
                out.append(f"  HAND: {len(self.hand)} placed by hand, replaced or removed by "
                           "this build (adopt into the design, leave out, or come back to it):")
                out += [f"    {line}" for line in self.hand]
        if self.relaid:
            items = sorted({i for v in self.relaid for i in v.wrong_items})
            out.append(f"  {len(self.relaid)} carriers laid under another net held "
                       f"{', '.join(items)}: ordered up, and the paste lays them fresh")
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


def default_area(s, cat, keys=None, own=None):
    """An apply's area when none is given: the design in scope plus the toolkit's own entities
    it dropped (``own``), wherever they stand (a moved plot's old ground). None: nothing."""
    rows = scope_rows(s, None, keys)
    for row in ownmod.dropped(own, s):
        if ownmod.in_scope(row, cat, None, keys):
            rows.append({"src": row.key, "name": row.name, "x": row.x, "y": row.y,
                         "direction": row.dir, "attrs": {}})
    return scope_area(rows, cat)


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


def diff(r, s, cat, area, policy, net_items=None, tag="diff", own=None):
    """Snapshot ``area`` and judge it against the design: a ``sense.SenseReport``."""
    live = scene.from_capture(link.snapshot(r, s.name, area, tag))
    return sense.sense(s, live, cat, list(area), policy, net_items=net_items, own=own)


def apply(r, s, cat, area=None, mode="play", force=None, label=None, policy=None, keys=None,
          net_items=None, tag="apply", seed=True, own=None) -> ApplyReport:
    """Paste the design inside ``area`` (default: all of ``s``, and the toolkit's own entities it
    dropped) as one named blueprint. ``own``: the record of what the applies pasted."""
    t0 = time.time()
    given = area
    rows = scope_rows(s, area, keys)
    if area is None:
        area = default_area(s, cat, keys, own)
    force = force or force_for(mode)
    rep = ApplyReport(s.name, force, mode, tuple(area or (0, 0, 0, 0)), design=len(rows))
    if area is None:
        rep.notes.append("nothing designed in this scope")
        return rep
    standing = []
    if mode != "lab" and policy is not None:
        before = diff(r, s, cat, area, policy, net_items, tag=f"{tag}-before", own=own)
        held = scaffold(before, s, cat, area)
        rep.hand = sense.hand_edits(before, held)
        gone = [v for v in before.verdicts
                if v.verdict == "NOBODY" and (v.name, v.x, v.y) not in held]
        # the toolkit's own that still stand stay in the record: ordered out, or held up
        standing = [ownmod.at(v.name, v.x, v.y) for v in before.verdicts
                    if v.verdict == "NOBODY" and v.action == "own"]
        rep.dropped = sum(1 for v in gone if v.action == "own")
        rep.held = len(held)
        rep.decon = _decon(r, s.name, force, [(v.name, v.x, v.y) for v in gone])
        # ordered out before the paste, so the paste lays a fresh one on each (a paste over the
        # same entity not ordered out places nothing, and the old items stay)
        rep.relaid = [v for v in before.verdicts if v.renet and v.wrong_items
                      and v.verdict in ("OK", "DRIFT")]
        _decon(r, s.name, force, [(v.name, v.x, v.y) for v in rep.relaid])
        rep.own = ownmod.update(own, s, cat, None if given is None else area, keys, standing)
    if not rows:
        rep.notes.append("nothing designed in this scope")
        rep.seconds = time.time() - t0
        return rep
    if mode == "lab":
        rep.chunks = int(r.lua(link.lua_generate_area(s.name, force, area)).strip() or 0)
        ore = {}
        for e in s.entities.values():
            if e.attrs.get("resource") and cat.kind(e.name) == "mining-drill" \
                    and _touches(e.tiles, area):
                ore.setdefault(e.attrs["resource"], []).extend(e.tiles)
        if ore and seed:
            rep.seeded = int(r.lua(link.lua_seed(s.name, ore)).strip() or 0)
        elif ore:
            rep.notes.append("no ore seeded: the drills stand on the terrain's ore")
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


def scaffold(before, s, cat, area):
    """What an apply leaves standing for now (1.7, Rory 2026-10-21: old poles and roboports stay
    up until the new grid stands, so a rebuild doesn't cut power or the robot network; both
    overnight players lost power to a re-laid grid): the built ``NOBODY`` poles and roboports on
    no tile of the design, while a pole (or roboport) the design has in ``area`` is not built
    yet (a ghost, missing, or under something else). One under a design tile goes as before (the
    paste needs its ground). ``before``: the diff before the paste. -> {(name, x, y)}."""
    def kind(name):
        try:
            return cat.kind(name)
        except KeyError:
            return None

    waiting = {kind(v.name) for v in before.verdicts
               if v.verdict in ("GHOST", "MISSING", "WRONG") and kind(v.name) in SCAFFOLD_KINDS}
    if not waiting:
        return set()
    taken = set()
    for e in s.entities.values():
        if _touches(e.tiles, area):
            taken |= {tuple(t) for t in e.tiles}
    out = set()
    for v in before.verdicts:
        if v.verdict != "NOBODY" or v.ghost or kind(v.name) not in waiting:
            continue
        tiles = {tuple(t) for t in cat.tiles(v.name, float(v.x), float(v.y), 0)}
        if not tiles & taken:
            out.add((v.name, v.x, v.y))
    return out


#: entities per decon order (one RCON command each; pastes go in 3000-character chunks)
DECON_BATCH = 60


def _decon(r, surface, force, things):
    """Order ``things`` [(name, x, y)] out in batches; -> how many the game took."""
    n = 0
    for i in range(0, len(things), DECON_BATCH):
        n += _int(r.lua(link.lua_decon_list(surface, force, things[i:i + DECON_BATCH])))
    return n


def rip_points(rep):
    """The positions of what the next apply takes up, from a diff (a ``sense.SenseReport``):
    NOBODY and WRONG, and the carriers it lays fresh under another net (1.2)."""
    return [(v.x, v.y) for v in rep.verdicts if v.verdict.split()[0] in RIP_VERDICTS
            or (v.renet and v.wrong_items)]


def rip_load(r, surface, force, points, batch=80):
    """``link.lua_rip_load`` over ``points`` in batches that fit one RCON command (pastes go in
    3000-character chunks for the same reason): the counts summed, the network's numbers from
    the first batch that has them."""
    total = {"n": 0, "items": 0}
    for i in range(0, len(points), batch):
        got = json.loads(r.lua(link.lua_rip_load(surface, force, points[i:i + batch])).strip()
                         or "{}")
        total["n"] += int(got.get("n") or 0)
        total["items"] += int(got.get("items") or 0)
        for k in ("robots", "idle", "dist", "speed", "cargo"):
            if got.get(k) is not None and k not in total:
                total[k] = got[k]
    return total


def rip_minutes(load):
    """Robot time to take up a load read by ``link.lua_rip_load``: each structure, and each cargo
    of the items it holds, is a trip to the nearest storage and back, shared by the network's
    construction robots. An estimate: robots also build, charge and queue."""
    n, items = int(load.get("n") or 0), int(load.get("items") or 0)
    if not n:
        return 0.0
    trips = n + math.ceil(items / max(1, int(load.get("cargo") or 1)))
    trip = 2 * max(5.0, float(load.get("dist") or 50.0)) / max(0.5, float(load.get("speed") or 3.6))
    return trips * (trip + 2) / max(1, int(load.get("robots") or 1)) / 60


def moved(rep):
    """How many taken-up structures come back as new ones of the same name (MISSING or GHOST)
    in the same diff: the sign of a factory that moved."""
    gone, new = {}, {}
    for v in rep.verdicts:
        head = v.verdict.split()[0]
        if head in RIP_VERDICTS:
            gone[v.name] = gone.get(v.name, 0) + 1
        elif head in ("MISSING", "GHOST"):
            new[v.name] = new.get(v.name, 0) + 1
    return sum(min(c, new.get(name, 0)) for name, c in gone.items())


def rip_report(load, moved_n=0):
    """-> (the report line, the RIP check text or None) for a load from ``link.lua_rip_load``."""
    n, items = int(load.get("n") or 0), int(load.get("items") or 0)
    minutes = rip_minutes(load)
    dist = load.get("dist")
    where = f"storage {dist:.0f} tiles away" if dist is not None else "no storage chest in reach"
    line = (f"rip: the apply takes up {n} structures holding {items} items: about {minutes:.0f} "
            f"min for {int(load.get('robots') or 0)} construction robots ({where}, "
            f"{int(load.get('cargo') or 1)} items a trip)")
    if minutes < RIP_WARN_MIN and n < RIP_WARN_N and moved_n < MOVED_N:
        return line, None
    text = (f"{n} structures holding {items} items come down: about {minutes:.0f} min of robot "
            "time, and builds wait for robots meanwhile. To make it faster, stop what feeds it "
            "first and let it run a few minutes to drain its belts and chests, then build")
    if moved_n >= MOVED_N:
        text += (f". {moved_n} of them come back as new ones of the same name: it looks like a "
                 "factory moved. To join factories, fk merge A,B --into C keeps both where they "
                 "stand")
    return line, text


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
