"""fkcore.power: what cover power is given, as one problem (PLAN-POWER P1 and P2, 2026-11-11).

PLAN-POWER's ``PowerProblem`` is the target shape: loads, roots, ground and kinds built once per
factory, one solver, one report. This module holds only what P1 and P2 need, and
``fkcore.cover``'s greedy stays as it is:

- **Kinds** (P2, Rory 11-11: "Pole types should be an input so its configurable what poles are
  allowed and if multiple are allowed they can always be mixed"). ``--pole`` takes a comma list in
  order of preference; ``any`` is :func:`fkcore.avail.choose`'s pick, then the other kinds of
  ``avail.FAMILIES["pole"]`` robots can build now. The cover lays the first kind; a load it has no
  free spot for, or a wire component it cannot join, goes to the next kinds in order.
- **Roots** (P1, Rory 11-11: "world power is a type of global parameter, we could indicate power
  network id from the pole, and then look at that grid as the global power stat"). The surface
  file names one standing pole (``power grid X,Y``); ``read-terrain --entities`` records its
  electric network: every pole of it and its statistics (:func:`lua_grid`, ``entities_read
  ["grid"]``). Cover power takes the poles near a plot as fixed wire roots it bridges to and never
  lays (:func:`grid_roots`); floorplan's ``NO_POWER`` judges against them, and ``power-short``
  weighs a design's draw against the grid's spare capacity (:func:`short`).

What the read cannot know offline is said where it is used: the statistics are the game's last
minute, its capacity is the generators' rated output (solar at noon), and the grid's demand already
holds whatever of the design stands. Stdlib only; the Lua is a one-shot read (CLAUDE.md: nothing is
registered over RCON).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import fkp
from .elaborate import Check

__all__ = ["PowerProblem", "Root", "parse_kinds", "kinds_text", "point_to_frame", "grid_roots",
           "grid_rows", "grid_text", "lua_grid", "read_grid", "normalise", "short", "FLOW_W",
           "TICK_W", "CLEARLY", "POLE_WORDS"]

#: what the game's electric statistics give per window, to watts. 1.1's ``get_flow_count`` on an
#: electric network gave joules per tick (x 60 = W); 2.0's API says "the per-time-frame value"
#: and this was not checked against a 2.0 game (offline build, 2026-11-11). One constant, so a
#: live check changes one number.
FLOW_W = 60.0
#: a prototype's ``get_max_energy_production`` is joules per tick (the catalog's learn uses the
#: same 60, ``fkcore.learn.W``)
TICK_W = 60.0
#: ``power-short`` only when the design's full-load draw is this many times the grid's spare: a
#: machine rarely runs at full load, and the grid's demand holds what of the design stands already
CLEARLY = 1.25
#: what ``--pole`` says it takes
POLE_WORDS = "small-electric-pole, medium-electric-pole, big-electric-pole, substation"


@dataclass(frozen=True)
class Root:
    """A standing pole of the world's grid, in a factory's frame: a wire root the cover bridges
    to, never laid or moved, never in the layout (it stands in the world)."""
    key: str                       # grid#<id>/p<i>: what a power-split line names
    name: str
    x: float
    y: float
    grid: object = None            # the network id: every root of one id is one wire component


@dataclass
class PowerProblem:
    """What one factory's cover is given (P1+P2's part of PLAN-POWER's ``PowerProblem``): the
    allowed pole kinds, in order of preference; the world grid's roots in the factory frame; the
    tiles no pole may use; the grid read the roots came from (for the report)."""
    kinds: tuple
    roots: tuple = ()
    keep_out: frozenset = frozenset()
    grid: dict | None = None

    @property
    def pole(self):
        """The kind the cover lays: the first allowed."""
        return self.kinds[0]

    @property
    def more(self):
        """The kinds that take what the first cannot: a load with no free spot of it, a
        component it cannot join."""
        return tuple(self.kinds[1:])


def parse_kinds(word, cat, need=1, flag="--pole"):
    """``--pole`` -> the allowed kinds, in order of preference (a tuple, no repeats). ``word``: one
    name, a comma list, or ``any`` (``auto``, ``whatever``, ``best``) anywhere in the list: the
    avail pick, then the other buildable kinds in ``avail.FAMILIES`` order. With nothing read
    (no ``out/avail.json``) no other kind is buildable, so ``any`` is one kind, as before 3.5.
    Raises ValueError on a name that is not an electric pole."""
    from . import avail
    words = [w.strip() for w in str(word).split(",") if w.strip()]
    if not words:
        raise ValueError(f"{flag}: name a pole kind ({POLE_WORDS}), or any")
    out = []
    for w in words:
        if avail.is_any(w):
            first, _note = avail.choose("pole", w, need=need)
            got = [first] + [k for k in avail.FAMILIES["pole"]
                             if k != first and avail.buildable(k)]
        else:
            got = [w]
        for k in got:
            if not cat.has_entity(k) or cat.kind(k) != "electric-pole":
                raise ValueError(f"{flag} {k}: not an electric pole ({POLE_WORDS}), or any")
            if k not in out:
                out.append(k)
    return tuple(out)


def kinds_text(names, order=()):
    """``12 medium-electric-pole, 2 small-electric-pole``: poles per kind, in ``order`` (the
    allowed kinds), then any other kind by name."""
    count = {}
    for n in names:
        count[n] = count.get(n, 0) + 1
    keys = [k for k in order if k in count] + sorted(k for k in count if k not in order)
    return ", ".join(f"{count[k]} {k}" for k in keys) or "0 poles"


# -- the world's grid (P1) ------------------------------------------------------------------------
def point_to_frame(x, y, plot, size):
    """A surface point -> the factory frame's (the inverse of ``compose.turn`` plus the plot's
    origin; ``size`` is the factory's W x H before the turn)."""
    u, v = float(x) - plot.x, float(y) - plot.y
    w, h = size
    r = plot.rot % 4
    if r == 0:
        return u, v
    if r == 1:
        return v, h - u
    if r == 2:
        return w - u, h - v
    return w - v, u


def grid_roots(g, plot, size, cat, kinds):
    """The grid's poles that matter to one plot, as :class:`Root` in its factory frame: the ones
    within wire reach (of the longest allowed kind) or supply of the frame ``(0, 0)-(W, H)``.
    Rory 11-11: the grid is the world's power, so the cover bridges to it rather than laying a
    grid of its own; ``trimpoles.py`` found that wire path by hand (FRICTION 11-11). A pole of a
    kind the catalog does not know is left out (its reach is unknown)."""
    if not g or not isinstance(g.get("poles"), list):
        return ()
    reach = max(cat.pole_reach(k) for k in kinds)
    w, h = size
    out = []
    for i, row in enumerate(g["poles"]):
        if len(row) < 3:
            continue
        name = str(row[0])
        if not cat.has_entity(name) or cat.kind(name) != "electric-pole":
            continue
        fx, fy = point_to_frame(row[1], row[2], plot, size)
        lim = max(min(cat.pole_reach(name), reach), cat.pole_supply(name))
        dx = max(-fx, 0.0, fx - w)
        dy = max(-fy, 0.0, fy - h)
        if dx * dx + dy * dy <= lim * lim + 1e-9:
            out.append(Root(f"grid#{g.get('id')}/p{i}", name, fx, fy, g.get("id")))
    return tuple(out)


def grid_rows(g, cat):
    """The grid's poles as surface ``fkp.Entity`` rows (``grid#<id>/p<i>``), for floorplan's
    wire networks: never laid, never written."""
    out = []
    for i, row in enumerate((g or {}).get("poles") or ()):
        if len(row) < 3 or not cat.has_entity(str(row[0])) \
                or cat.kind(str(row[0])) != "electric-pole":
            continue
        out.append(fkp.Entity(f"grid#{g.get('id')}/p{i}", str(row[0]), float(row[1]),
                              float(row[2]), None, {}))
    return out


def _watts(w):
    w = float(w)
    if abs(w) >= 1e6:
        return f"{w / 1e6:.2f} MW"
    return f"{w / 1e3:.0f} kW"


def grid_text(g):
    """One phrase for the grid: its id, poles and stats (what a floorplan line names)."""
    st = g.get("stats") or {}
    parts = [f"{len(g.get('poles') or ())} poles"]
    made, used = st.get("made_w"), st.get("used_w")
    if isinstance(made, dict) and isinstance(used, dict):
        parts.append(f"made {_watts(sum(made.values()))}, used {_watts(sum(used.values()))} "
                     "over the last minute")
    cap = st.get("capacity_w")
    gens = sum((st.get("generators") or {}).values())
    if cap is not None:
        parts.append(f"capacity {_watts(cap)} from {gens} generator{'s' if gens != 1 else ''}")
    elif gens:
        parts.append(f"{gens} generators of unknown capacity")
    else:
        parts.append("no generator found on it")
    return f"the world grid #{g.get('id')} ({'; '.join(parts)}; read at tick {st.get('tick')})"


_LUA_GRID = r"""
local function g(o, k) local ok, v = pcall(function() return o[k] end) if ok then return v end end
local s, f = game.get_surface(@SURF@), game.forces[@FORCE@]
local X, Y = @X@, @Y@
local out = {at = {X, Y}, tick = game.tick}
local function done(n)
  helpers.write_file('fk5/@TAG@.json', helpers.table_to_json(out), false)
  rcon.print(n)
end
if not s or not f then out.why = 'no surface or force ' .. @FORCE@ return done(0) end
local best, bd = nil, nil
for _, p in pairs(s.find_entities_filtered{type = 'electric-pole', force = f,
    area = {{X - 1.5, Y - 1.5}, {X + 1.5, Y + 1.5}}}) do
  local dx, dy = p.position.x - X, p.position.y - Y
  local d = dx * dx + dy * dy
  if d <= 2.25 + 1e-6 and (bd == nil or d < bd) then best, bd = p, d end
end
if not best then out.why = 'no electric pole of force ' .. f.name .. ' stands within 1.5 tiles' return done(0) end
out.pole = {best.name, best.position.x, best.position.y}
local id = g(best, 'electric_network_id')
if not id then out.why = 'the pole there is on no electric network' return done(0) end
out.id = id
local poles = {}
for _, p in pairs(s.find_entities_filtered{type = 'electric-pole', force = f}) do
  if g(p, 'electric_network_id') == id then poles[#poles + 1] = {p.name, p.position.x, p.position.y} end
end
out.poles = poles
local st = {window = 'one_minute', tick = game.tick}
local es = g(best, 'electric_network_statistics')
if es then
  local P = defines.flow_precision_index.one_minute
  local function flows(counts, cat)
    local t = {}
    for n in pairs(counts or {}) do
      local ok, v = pcall(function() return es.get_flow_count{name = n, category = cat, precision_index = P, count = false} end)
      if ok and type(v) == 'number' then t[n] = v end
    end
    return t
  end
  -- a network's output is what was made, its input what its machines used (runstats)
  st.made = flows(g(es, 'output_counts'), 'output')
  st.used = flows(g(es, 'input_counts'), 'input')
end
local cap, gens, unknown, accs = 0, {}, 0, 0
for _, e in pairs(s.find_entities_filtered{type = {'generator', 'solar-panel', 'burner-generator',
    'fusion-generator', 'electric-energy-interface', 'accumulator'}, force = f}) do
  if g(e, 'electric_network_id') == id then
    if e.type == 'accumulator' then accs = accs + 1 else
      gens[e.name] = (gens[e.name] or 0) + 1
      local ok, v = pcall(function() return e.prototype.get_max_energy_production(e.quality) end)
      if not ok then ok, v = pcall(function() return e.prototype.get_max_energy_production() end) end
      if ok and type(v) == 'number' then cap = cap + v else unknown = unknown + 1 end
    end
  end
end
st.max_production, st.generators, st.unknown, st.accumulators = cap, gens, unknown, accs
out.stats = st
done(#poles)
"""


def lua_grid(surface, force, at, tag):
    """Lua writing ``fk5/<tag>.json``: the electric network of the ``force`` pole nearest ``at``
    (within 1.5 tiles: a 2x2 pole's centre is a tile corner) on ``surface``, as {at, tick, pole,
    id, poles [[name, x, y]], stats {made, used (the game's per-name flow over the last minute),
    max_production (J/tick summed over its generators), generators {name: n}, unknown,
    accumulators}}, or {at, why}. A one-shot read: nothing registered, nothing changed."""
    def q(t):
        return "'" + str(t).replace("\\", "\\\\").replace("'", "\\'") + "'"
    x, y = (float(v) for v in at)
    return (_LUA_GRID.replace("@SURF@", q(surface)).replace("@FORCE@", q(force))
            .replace("@X@", repr(x)).replace("@Y@", repr(y)).replace("@TAG@", tag))


def _table(v):
    """A Lua table as JSON: an empty one comes back as [] (``table_to_json``)."""
    return dict(v) if isinstance(v, dict) else {}


def normalise(raw, at):
    """The Lua's answer -> ``entities_read["grid"]``: {"at", "id", "pole", "poles", "stats":
    {"tick", "window", "made_w", "used_w", "capacity_w", "generators", "accumulators"}}, or
    {"at", "why"} (a read that found nothing says why rather than raising)."""
    at = [float(v) for v in at]
    if not isinstance(raw, dict):
        return {"at": at, "why": f"the read gave {type(raw).__name__}, not a grid"}
    if raw.get("why") or raw.get("id") is None:
        out = {"at": at, "why": str(raw.get("why") or "the read named no network")}
        if raw.get("pole"):
            out["pole"] = list(raw["pole"])
        return out
    st = _table(raw.get("stats"))
    gens = {str(k): int(v) for k, v in _table(st.get("generators")).items()}
    unknown = int(st.get("unknown") or 0)
    cap = st.get("max_production")
    stats = {"tick": st.get("tick", raw.get("tick")), "window": "1min",
             "made_w": {str(k): float(v) * FLOW_W for k, v in _table(st.get("made")).items()},
             "used_w": {str(k): float(v) * FLOW_W for k, v in _table(st.get("used")).items()},
             # rated output (solar at noon); None when no generator was found or one's is unknown
             "capacity_w": (float(cap) * TICK_W if gens and not unknown
                            and isinstance(cap, (int, float)) else None),
             "generators": dict(sorted(gens.items())),
             "accumulators": int(st.get("accumulators") or 0)}
    if unknown:
        stats["unknown"] = unknown
    poles = [[str(p[0]), float(p[1]), float(p[2])] for p in raw.get("poles") or () if len(p) >= 3]
    poles.sort(key=lambda p: (p[2], p[1], p[0]))
    return {"at": at, "id": raw["id"], "pole": list(raw.get("pole") or ()), "poles": poles,
            "stats": stats}


def read_grid(rcon, surface, force, at, tag="terrain-grid"):
    """The grid read (:func:`lua_grid`) -> ``entities_read["grid"]``; a failed read records why."""
    from . import link
    try:
        raw = link.read_output(rcon, lua_grid(surface, force, at, tag), tag, "power grid",
                               keep=False)
    except (link.LinkError, OSError, ValueError) as exc:
        return {"at": [float(v) for v in at], "why": f"the read failed: {exc}"[:300]}
    return normalise(raw, at)


def short(layouts, cat, g, where):
    """``power-short`` against the world grid (P1): per factory, its nominal draw at full load
    (the catalog's energy use of its non-DNP electric entities, ``domains._supply``, less what
    its own generators make) against the grid's spare (rated capacity less what it used over the
    last minute). -> (lines, checks). A check only when the draw is :data:`CLEARLY` past the
    spare; the line says what it cannot know."""
    from .domains import _supply
    st = (g or {}).get("stats") or {}
    cap = st.get("capacity_w")
    used = sum((st.get("used_w") or {}).values()) if isinstance(st.get("used_w"), dict) else None
    lines, checks, total = [], [], 0.0
    spare = None if cap is None or used is None else cap - used
    for name in sorted(layouts):
        lay = layouts[name]
        made, want, _gens = _supply(lay, cat, set(lay.entities))
        draw = max(0.0, want - (made or 0.0))
        total += draw
        own = f" less {_watts(made)} its own generators make" if made else ""
        if spare is None:
            lines.append(f"  {name}: draws {_watts(draw)} at full load{own}; the grid's "
                         "capacity is unknown, so it is not weighed")
            continue
        lines.append(f"  {name}: draws {_watts(draw)} at full load{own}, against "
                     f"{_watts(spare)} spare on the world grid #{g.get('id')}")
        if draw > CLEARLY * max(spare, 0.0) + 1e-6:
            checks.append(Check("power-short", f"{where} {name}",
                                f"at full load it draws {_watts(draw)}, and the world grid "
                                f"#{g.get('id')} has {_watts(spare)} spare ({_watts(cap)} rated "
                                f"less {_watts(used)} used over the last minute): build "
                                "generation first, or build it in parts"))
    head = ("power-short (offline, nominal): full-load draw against the world grid's spare; "
            "machines rarely run at full load, the grid's demand already holds what of the "
            "design stands, and its capacity is the generators' rated output (solar at noon)")
    if len(layouts) > 1:
        lines.append(f"  all plots: draw {_watts(total)} at full load"
                     + ("" if spare is None else f", against {_watts(spare)} spare"))
        if spare is not None and total > CLEARLY * max(spare, 0.0) + 1e-6 \
                and not any(c.code == "power-short" for c in checks):
            checks.append(Check("power-short", f"{where} all plots",
                                f"together they draw {_watts(total)} at full load, and the world "
                                f"grid #{g.get('id')} has {_watts(spare)} spare"))
    return [head] + lines, checks
