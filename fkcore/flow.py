"""fkcore.flow: the build script (``<surface>.build.fkb``), run as a Vivado-style flow (CORE-V1 §7).

One contained tool per line, straight-line, no control flow. Every step reads the state the steps
before it left and writes a report, ``out/<step>.txt``. A step that changes a layout also writes a
checkpoint, ``out/<step>/<factory>.fkp`` (and ``<surface>.fkp`` once there is a floorplan).
``stop_on <check ...>`` lines (anywhere in the script) name the check codes that stop the run;
``invariant`` is always among them, because malformed data can't be written. Everything else is a
report line, never a gate.

``run(script, frm=None, to=None)`` runs the whole script or the lines from ``frm`` to ``to``.
Steps before ``frm`` that only read source (``read_surface``, ``read_terrain``, ``run_models``,
``elaborate``, ``size``) are re-run quietly: source is cheap and pure. Layouts come from the
checkpoint of the last layout step before ``frm``, and a ``floorplan`` before ``frm`` is replayed
on them (it is pure too), so ``--from diff`` on the game host applies what a laptop build laid out.
A checkpoint says what source it was laid from (``out/<step>/source.json``: the source files and
the script's lines up to its step). When that is not the source as it is now (2.0.4: a recipe
changed, and the paste laid the old one), the layout steps before ``frm`` run again instead.

Steps: read_surface, read_terrain, run_models, elaborate, size, report_rates, place, route, tier,
cover power, cover robots, floorplan, report_checks, report_bom, write_layout, diff, apply,
stop_on.

``size`` (1.6, ``fkcore.size``) gives every ``n=auto`` row its count: the fewest machines that
meet the surface's targets, the factories' asserts and what each row's consumers ask, all the
factories together, before anything is placed. Its report says what each count serves; ``FIT``
says when a row grown that way runs past its plot or into another instance (rows grow, the
player arranges them), and report_rates after route says (``SIZE``) when a net of a sized row
asks more of its belts than they carry.

The terrain (``read_terrain <name>``: ``<name>.terrain.json``, ``fkcore.terrain``) is the bare
world every layout step designs against: ``place`` puts each ``@patch`` MinerRow on its ore inside
its plot, ``route`` and ``cover power`` keep their carriers and poles off its blocked tiles
(water, cliffs), each factory's in its own frame, and ``floorplan`` reports ``ON_TERRAIN`` for a
composed entity on blocked ground and ``OFF_ORE`` for a drill with no ore of its resource in
reach. They are checks, never gates. With a terrain, a lab ``apply`` seeds no ore: the ore is
the terrain's.

``diff`` and ``apply`` use the game link (``fkcore.link``: RCON, 5 s per call; the
surface file's name is the game surface, its mode picks the force and the rules, see
``fkcore.apply``). The link is used only when ``FK_LINK=on`` is set (so a paper game run on the
game host never pastes by accident); without it, or with no RCON password file or nothing
listening, they report that they were skipped. Apart from those two steps it is pure: it reads
the game codebase and writes ``out/`` and, in write_layout, the ``.fkp`` files.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from dataclasses import dataclass, field

from . import avail as availmod
from . import compose, connect, expand, fkp, placer, rates, route
from . import own as ownmod
from . import surface as surfacemod
from . import terrain as terrainmod
from .catalog import Catalog
from .elaborate import Check, ElabError, elaborate_file
from .lang import FkSyntaxError

__all__ = ["FlowError", "Ctx", "Line", "parse", "run", "STEPS", "layout_source_changes"]


class FlowError(ValueError):
    pass


@dataclass
class Line:
    n: int
    cmd: str                 # the step name: "route", "cover_power", ...
    args: list
    text: str


@dataclass
class Ctx:
    root: str
    script: str
    cat: Catalog
    out: str
    surface: surfacemod.SurfaceFile | None = None
    flats: dict = field(default_factory=dict)        # factory -> Flat
    layouts: dict = field(default_factory=dict)      # factory -> factory Layout (current)
    previous: dict = field(default_factory=dict)     # factory -> the committed .fkp, if any
    surface_lay: fkp.Layout | None = None
    composed: compose.Surface | None = None
    terrain: set = field(default_factory=set)        # blocked ground tiles (none on paper)
    ground: object = None                            # the terrain.Terrain, when one is read
    stop_on: set = field(default_factory=lambda: {"INVARIANT"})
    log: list = field(default_factory=list)          # one summary line per step run
    checks: list = field(default_factory=list)       # [(step, Check)] of every step run so far
    link: object = None                              # the game link (fkcore.link.Rcon), on use
    link_error: str | None = None
    link_lent: bool = False                          # the caller's link: not closed here
    last_diff: object = None                         # the last diff's SenseReport this run
    hands: tuple | None = None                       # the force's (hand, bulk hand, note), read once
    rates_runs: int = 0                              # report_rates steps run so far
    sized: object = None                             # the size step's fkcore.size.Sizing
    steps: list = field(default_factory=list)        # the script's step names, in order
    source: dict = field(default_factory=dict)       # {source file: sha1} as the run began


def parse(text, path="<fkb>") -> list:
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        t = shlex.split(line)
        cmd, args = t[0], t[1:]
        if cmd == "cover":
            if not args or args[0] not in ("power", "robots"):
                raise FlowError(f"{path}:{n}: cover power|robots")
            cmd, args = f"cover_{args[0]}", args[1:]
        if cmd not in STEPS:
            raise FlowError(f"{path}:{n}: unknown step {t[0]!r} (steps: "
                            + ", ".join(sorted(s.replace('_power', ' power')
                                               .replace('_robots', ' robots') for s in STEPS)) + ")")
        out.append(Line(n, cmd, args, line))
    return out


def _opts(args, **defaults):
    """--key value / --flag options -> dict (values stay strings)."""
    out, i = dict(defaults), 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                out[key] = args[i + 1]
                i += 2
            else:
                out[key] = True
                i += 1
        else:
            out.setdefault("_", []).append(a)
            i += 1
    return out


def _count(o, key, lo=0):
    """An option that must be a whole number (``--red 20``) -> int, None when not given."""
    v = o.get(key)
    if v is None:
        return None
    flag = "--" + key.replace("_", "-")
    if v is True:
        raise FlowError(f"{flag} needs a number")
    try:
        n = int(v)
    except ValueError:
        raise FlowError(f"{flag} needs a whole number, got {v!r}") from None
    if n < lo:
        raise FlowError(f"{flag} is at least {lo}, got {n}")
    return n


def _hands(ctx, o):
    """(hand, bulk hand, note) for ``--hand N|auto`` and ``--bulk-hand N|auto``: a number as given;
    ``auto`` (the default) the force's, 1 + its inserter capacity bonuses: read over the game link
    once a build, else as the last ``diff`` saved them (``out/force.json``: the agent kit designs
    on the laptop, where there is no link, and diffs on the game host), else 1 (the note says
    which)."""
    want = {}
    for key in ("hand", "bulk_hand"):
        if o.get(key, "auto") != "auto":
            want[key] = _count(o, key, lo=1)
    if len(want) < 2 and ctx.hands is None:
        ctx.hands = _force_hands(ctx)
    hand, bulk, note = ctx.hands if len(want) < 2 else (1, 1, "")
    if want:
        note = "inserter hands as given" if len(want) == 2 else note
    return want.get("hand", hand), want.get("bulk_hand", bulk), note


_FORCE_FILE = "force.json"                           # in out/: the force's hands, by diff
_STANDING_FILE = "standing.json"                     # in out/: the poles built, by diff (2.0.1)
_STAMP_FILE = "source.json"             # in out/<step>/: the source its checkpoint was laid from
_LAID_FILE = "layout-source.json"       # in out/: the source write_layout's .fkp files came from
#: the source files of a game codebase (beside the build script): what a layout is laid from.
#: The build script itself counts by its lines up to each step; the .fkp files are its output.
_SOURCE_EXT = (".fk", ".surface", ".json", ".model.py")


def _source_files(root):
    """{file: sha1} of the game codebase's source files in ``root``."""
    out = {}
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if name.endswith(_SOURCE_EXT) and os.path.isfile(full):
            h = hashlib.sha1()
            with open(full, "rb") as fh:
                h.update(fh.read())
            out[name] = h.hexdigest()
    return out


def _changed(was, now):
    """The source files that differ between two ``_source_files`` reads, sorted, each with how."""
    out = []
    for name in sorted(set(was) | set(now)):
        if was.get(name) != now.get(name):
            how = "changed" if name in was and name in now else "added" if name in now \
                else "removed"
            out.append(f"{name} {how}")
    return out


def _script_sha(lines):
    return hashlib.sha1("\n".join(ln.text for ln in lines).encode()).hexdigest()


def layout_source_changes(game):
    """What changed in the source of the placed factories (their modules' ``.fk``, the surface
    file) since write_layout last wrote the ``.fkp`` files, one line each; [] when nothing did or
    no build has said what it wrote from. 2.0.4: ``fk look`` judges against the ``.fkp`` files,
    and after a paste from stale checkpoints it said OK while the machine ran the old recipe (the
    second lead run, 2026-10-22); a look now says when the .fkp is not the source's."""
    try:
        with open(os.path.join(game, "out", _LAID_FILE), encoding="utf-8") as fh:
            was = json.load(fh)["files"]
        sf = surfacemod.load_game(game)
    except (OSError, ValueError, KeyError, TypeError, surfacemod.SurfaceError):
        return []
    now = _source_files(game)
    lines = []
    for name in _changed(was, now):
        file, how = name.rsplit(" ", 1)
        mods = sorted({p.module for p in sf.places.values()
                       if p.lifecycle != "retired" and f"{p.module}.fk" == file})
        if mods:
            lines.append(f"{file} {how} since {mods[0]}.fkp was written: this look judges the "
                         f"design as last written, and the next fk build lays out the change")
        elif file.endswith(".surface"):
            lines.append(f"{file} {how} since the .fkp files were written: this look judges the "
                         f"design as last written, and the next fk build lays out the change")
    return lines


def _force_hands(ctx):
    r = _link(ctx) if ctx.surface is not None else None
    if r is not None:
        try:
            hand, bulk = _save_hands(ctx, r)
            return hand, bulk, f"inserter hands {hand}, bulk {bulk} (force {_force(ctx)}'s research)"
        except Exception as exc:                    # noqa: BLE001 - a report line, not a stop
            return 1, 1, f"inserter hands 1 (could not read the force's bonuses: {exc})"
    try:
        with open(os.path.join(ctx.out, _FORCE_FILE), encoding="utf-8") as fh:
            saved = json.load(fh)
        hand, bulk = int(saved["hand"]), int(saved["bulk_hand"])
    except (OSError, ValueError, KeyError, TypeError):
        why = ctx.link_error or "no surface read"
        return 1, 1, (f"inserter hands 1 (no game link: {why}; no diff has saved the force's "
                      f"yet; --hand N sets them)")
    return hand, bulk, (f"inserter hands {hand}, bulk {bulk} (force {saved.get('force', '?')}'s "
                        f"research at the last diff, out/{_FORCE_FILE})")


def _save_hands(ctx, r):
    """Read the force's inserter capacity bonuses over the link and save the hands in
    ``out/force.json``. -> (hand, bulk hand)."""
    force = _force(ctx)
    reply = r.lua(f"local f = game.forces['{force}'] rcon.print(f.inserter_stack_size_bonus "
                  ".. ' ' .. f.bulk_inserter_capacity_bonus)")
    a, b = (int(float(x)) for x in reply.split())
    os.makedirs(ctx.out, exist_ok=True)
    with open(os.path.join(ctx.out, _FORCE_FILE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"force": force, "hand": 1 + a, "bulk_hand": 1 + b}, fh)
        fh.write("\n")
    return 1 + a, 1 + b


def _save_standing(ctx, rep):
    """The poles the diff finds built (OK) in ``out/standing.json``, updated over the diff's
    scope and kept elsewhere: the next build's cover step runs where there is no game link, and
    keeps a built pole of another kind than its own (2.0.1)."""
    path = os.path.join(ctx.out, _STANDING_FILE)
    poles = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            poles = dict(json.load(fh).get("poles") or {})
    for v in rep.verdicts:
        if not v.key or not ctx.cat.has_entity(v.name) \
                or ctx.cat.kind(v.name) != "electric-pole":
            continue
        if v.verdict.split()[0] == "OK":
            poles[v.key] = v.name
        else:
            poles.pop(v.key, None)
    os.makedirs(ctx.out, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"poles": dict(sorted(poles.items()))}, fh, indent=0)
        fh.write("\n")


def _standing(ctx, factory):
    """The keys (``power/p3``) of ``factory``'s poles the last diff found built, or None when no
    diff has said (then a pole of another kind is never kept, as before)."""
    path = os.path.join(ctx.out, _STANDING_FILE)
    if ctx.surface is None or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            poles = json.load(fh).get("poles") or {}
    except (OSError, ValueError):
        return None
    head = f"{ctx.surface.name}:{factory}/"
    return {k[len(head):] for k in poles if k.startswith(head)}


def _factories(ctx):
    if ctx.surface is None:
        raise FlowError("no surface read yet: the script needs read_surface first")
    return [p for p in ctx.surface.places.values() if p.lifecycle != "retired"]


def _invariant_checks(where, problems):
    return [Check("INVARIANT", where, p) for p in problems]


# -- steps: each returns (report lines, checks) ---------------------------------------------------
def s_read_surface(ctx, args):
    name = args[0] if args else None
    if not name:
        raise FlowError("read_surface <name>")
    path = os.path.join(ctx.root, f"{name}.surface")
    ctx.surface = surfacemod.load(path)
    sf = ctx.surface
    lines = [f"surface {sf.name}: mode {sf.mode}, terrain {sf.terrain}, catalog {sf.catalog}, "
             f"notify {sf.notify_mode}, watch plots {sf.watch['plots']} / sanctioned "
             f"{sf.watch['sanctioned']}"]
    for p in sf.places.values():
        lines.append(f"  place {p.factory} = {p.module} plot {p.x},{p.y} {p.w}x{p.h} rot {p.rot}"
                     f" ({p.lifecycle})")
    for item, r in sf.targets.items():
        lines.append(f"  target {item} {r * 60:g}/min")
    for p in sf.places.values():
        prev = os.path.join(ctx.root, f"{p.module}.fkp")
        if os.path.exists(prev):
            ctx.previous[p.factory] = fkp.load(prev)
    return lines, []


def s_read_terrain(ctx, args):
    name = args[0] if args else "none"
    if name == "none":
        return ["terrain none: no ore, water or cliffs constrain the layout (a paper surface)"], []
    path = os.path.join(ctx.root, f"{name}.terrain.json")
    if not os.path.exists(path):
        return [f"terrain {name}: no {name}.terrain.json in the game codebase"], [
            Check("TERRAIN", name, "no terrain file; the layout is not checked against the ground")]
    t = terrainmod.load(path)
    ctx.ground = t
    ctx.terrain = set(t.blocked)
    lines, checks = terrainmod.summary(t, name), []
    if ctx.surface is None:
        return lines, checks
    if t.surface != ctx.surface.name:
        checks.append(Check("TERRAIN", name, f"read from surface {t.surface}; this surface is "
                                             f"{ctx.surface.name}"))
    x0, y0, x1, y1 = t.area
    for p in _factories(ctx):
        outside = p.w * p.h - (max(0, min(x1, p.x + p.w) - max(x0, p.x))
                               * max(0, min(y1, p.y + p.h) - max(y0, p.y)))
        lines.append("  " + _plot_ground(t, p))
        if outside:
            checks.append(Check("TERRAIN", f"{name} plot {p.factory}",
                                f"{outside} of its {p.w * p.h} tiles are outside the terrain's "
                                "area: unknown ground"))
    return lines, checks


def _plot_ground(t, p):
    """One line: what the terrain holds inside a plot (blocked ground, ore by patch)."""
    def inside(tile):
        return p.x <= tile[0] < p.x + p.w and p.y <= tile[1] < p.y + p.h

    parts = [f"{sum(1 for b in t.water if inside(b))} water",
             f"{sum(1 for b in t.cliff_tiles if inside(b))} cliff",
             f"{sum(1 for b in t.other if inside(b))} other blocked tiles"]
    for res, ps in sorted(t.patches.items()):
        held = [(pt.n, sum(1 for tile in pt.tiles if inside(tile))) for pt in ps]
        held = [(n, k) for n, k in held if k]
        if held:
            parts.append(f"{res} " + ", ".join(f"#{n} {k} tiles" for n, k in held))
    return f"plot {p.factory} at {p.x},{p.y} {p.w}x{p.h}: " + "; ".join(parts)


def s_run_models(ctx, args):
    found = [p.module for p in _factories(ctx)
             if os.path.exists(os.path.join(ctx.root, f"{p.module}.model.py"))]
    if not found:
        return ["no model scripts (<module>.model.py); parameters are as written in the .fk"], []
    return [f"model scripts found but not run in V1 yet: {', '.join(found)}"], [
        Check("MODEL", ", ".join(found), "model scripts are not run yet")]


def s_elaborate(ctx, args):
    lines, checks = [], []
    for p in _factories(ctx):
        path = os.path.join(ctx.root, f"{p.module}.fk")
        try:
            flat = elaborate_file(path, ctx.cat, name=p.module, layout=ctx.previous.get(p.factory))
        except (FkSyntaxError, ElabError, OSError) as exc:
            return lines, [Check("INVARIANT", p.factory, f"no netlist: {exc}")]
        ctx.flats[p.factory] = flat
        sushi = sum(n.sushi for n in flat.nets.values())
        autos = [path for path, inst in flat.insts.items() if inst.auto]
        lines.append(f"{p.factory}: {len(flat.insts)} instances, {len(flat.machines)} machines, "
                     f"{len(flat.nets)} nets ({sushi} sushi), {len(flat.checks)} check lines"
                     + (f"; {len(autos)} n=auto rows (at the count their .fkp laid out, or their "
                        "low bound, until the size step counts them)" if autos else ""))
        checks += [Check(c.code, f"{p.factory} {c.where}", c.msg, c.line) for c in flat.checks]
        if autos and "size" not in ctx.steps:
            checks.append(Check("SIZE", p.factory, f"n=auto rows ({', '.join(autos)}) and no size "
                                "step in the build script: each keeps the count its .fkp laid "
                                "out last, else its low bound"))
    return lines, checks


def s_size(ctx, args):
    """The counts of the ``n=auto`` rows (``fkcore.size``): the fewest machines that meet the
    surface's targets, the factories' asserts and what each row's consumers ask, every factory
    together. The report says what each count serves; a constraint no count can meet is a
    ``SIZE`` line, a sized row that runs past its plot or into another instance a ``FIT`` line.
    Rows grow; where they stand is the player's (and ``place`` stops on two entities on a
    tile)."""
    from . import size as sizemod
    makers, previous = {}, {}
    for p in _factories(ctx):
        if p.factory not in ctx.flats:
            continue
        path = os.path.join(ctx.root, f"{p.module}.fk")
        makers[p.factory] = sizemod.maker(path, ctx.cat, p.module, ctx.previous.get(p.factory))
        if p.factory in ctx.previous:
            previous[p.factory] = ctx.previous[p.factory]
    sz = sizemod.size(makers, ctx.surface.targets if ctx.surface is not None else None, previous)
    lines, checks = sizemod.report(sz, ctx.cat)
    if not sz.rows:
        return lines, checks
    ctx.flats.update(sz.flats)
    ctx.sized = sz
    patch = [r for r in sz.rows if "patch" in sz.flats[r.factory].insts[r.path].hints
             and "at" not in sz.flats[r.factory].insts[r.path].hints]
    if patch:
        lines += ["", "  on their ore by place (@patch): " + ", ".join(
            f"{r.path} n={r.n}" for r in patch) + "; place says when that many drills don't fit"]
    return lines, checks + sizemod.fit(sz, ctx.surface.places if ctx.surface else {}, ctx.cat)


def s_report_rates(ctx, args):
    """The nominal rate model per factory (V1); once a factory is laid out (after ``place`` and
    ``route``), also its routed rates (V2, ``fkcore.routed``: the lanes and inserters as laid,
    ``CAPACITY`` where a carrier binds). ``--hand N`` / ``--bulk-hand N``: the inserter hand
    sizes (1 + the research bonus); ``auto`` (the default) reads the force's over the game link.
    Run again later in the script (after ``route``), it reports in full but adds as checks only
    what is new: ``CAPACITY``, and a ``TARGET`` the nominal rates met and the routed ones don't
    (the ``ASSERT`` and ``TARGET`` lines of the nominal model are the first run's)."""
    o = _opts(args, hand="auto", bulk_hand="auto")
    for key in ("hand", "bulk_hand"):
        if o[key] != "auto":
            _count(o, key, lo=1)
    ctx.rates_runs += 1
    again = ctx.rates_runs > 1
    lines, checks, made, routed_made = [], [], {}, None
    hands = None
    for factory, flat in ctx.flats.items():
        model = rates.solve(flat)
        lines += rates.report(model, factory).splitlines() + [""]
        for text, ok, value, target, op in model.asserts:
            if not ok and not again:
                checks.append(Check("ASSERT", factory, f"{text}: {value * 60:.3f}/min"))
        for net, item, can, want in ([] if again else rates.underfed(model)):
            checks.append(Check(
                "UNDERFED", f"{factory} net {net}",
                f"{item}: its drivers make {can * 60:.1f}/min at most, its consumers would take "
                f"{want * 60:.1f}/min, so they run at about {can / want:.0%} for it; "
                f"`fk plan {item} {want * 60:.0f}/min` sizes the drivers"))
        for key, m in flat.machines.items():
            for item, r in m.makes.items():
                made[item] = made.get(item, 0.0) + r * model.util[key]
        lay = ctx.layouts.get(factory)
        if lay is not None:
            from . import routed
            if hands is None:
                hands = _hands(ctx, o)
            r_ = routed.solve(flat, lay, ctx.cat, model, hand=hands[0], bulk_hand=hands[1])
            rlines, rchecks = routed.report(r_, factory)
            lines += rlines + [""]
            checks += rchecks
            if ctx.sized is not None:
                from . import size as sizemod
                checks += sizemod.belts(ctx.sized, factory, r_)
            routed_made = routed_made if routed_made is not None else {}
            for key, m in flat.machines.items():
                u = r_.util(key)
                for item, rate in m.makes.items():
                    if u is not None and rate != float("inf"):
                        routed_made[item] = routed_made.get(item, 0.0) + rate * u
    if ctx.surface is not None:
        for item, want in ctx.surface.targets.items():
            got = made.get(item, 0.0)
            nominal_ok = ok = got >= want - 1e-9
            text = f"{got * 60:.3f}/min nominal"
            if routed_made is not None:
                rgot = routed_made.get(item, 0.0)
                ok = ok and rgot >= want - 1e-9
                text += f", {rgot * 60:.3f}/min routed"
            lines.append(f"target {item} {want * 60:g}/min: {'met' if ok else 'NOT met'}, {text}")
            if not ok and not (again and not nominal_ok):
                checks.append(Check("TARGET", item, f"{text}, target {want * 60:g}/min"))
    if hands is not None:
        lines.append(hands[2])
    return lines, checks


def _classify(new, prev):
    """unchanged | trivial | stale | new per instance, plus orphans, against the committed .fkp."""
    out = {}
    for path, r in new.insts.items():
        p = prev.insts.get(path) if prev is not None else None
        if p is None:
            out[path] = "new"
        elif (p.kind, p.sig, p.x, p.y, p.rot) != (r.kind, r.sig, r.x, r.y, r.rot):
            out[path] = "stale"
        elif p.params != r.params:
            out[path] = "trivial"
        else:
            out[path] = "unchanged"
    for path in (prev.insts if prev is not None else {}):
        if path not in new.insts:
            out[path] = "orphan"
    return out


_OWN_POLE = re.compile(r"[prs]\d+")   # a cover's own: poles p<k>, roboports r<k>, storage s<k>


def _pinned_covers(new, prev, cat):
    """Carry over a cover's pinned entities (a merged factory's poles, hand-placed ones: every
    entity under a cover that is not the cover's own ``p<k>``) from the committed .fkp."""
    if prev is None:
        return 0
    taken = set()
    for e in new.entities.values():
        taken |= fkp.tiles_of(cat, e)
    kept = 0
    for name, c in prev.covers.items():
        new.covers.setdefault(name, fkp.Cover(c.name, c.kind, dict(c.params)))
        for e in prev.entities.values():
            local = e.key[len(name) + 1:]
            if e.owner != name or _OWN_POLE.fullmatch(local):
                continue
            tiles = fkp.tiles_of(cat, e)
            if tiles & taken or e.key in new.entities:
                continue
            taken |= tiles
            new.add(fkp.Entity(e.key, e.name, e.x, e.y, e.dir, dict(e.attrs)))
            kept += 1
    return kept


def s_place(ctx, args):
    lines, checks = [], []
    for p in _factories(ctx):
        flat = ctx.flats[p.factory]
        ground, placed = None, []
        if ctx.ground is not None:
            # a quarter-turned plot's frame depends on the factory's size, not known before it
            # is laid out: the placer takes the frame to be the plot's own extent
            ground = terrainmod.frame_ground(ctx.ground, p, terrainmod.frame_size(p),
                                             patch=p.patch)
        lay, notes = expand.expand_factory(flat, ctx.cat, ctx.previous.get(p.factory), ground,
                                           placed)
        lay.name = p.factory
        pinned = _pinned_covers(lay, ctx.previous.get(p.factory), ctx.cat)
        if pinned:
            notes = list(notes)
            lines.append(f"{p.factory}: {pinned} pinned cover entities kept from the committed .fkp")
        ctx.layouts[p.factory] = lay
        cls = _classify(lay, ctx.previous.get(p.factory))
        count = {}
        for c in cls.values():
            count[c] = count.get(c, 0) + 1
        lines.append(f"{p.factory}: {len(lay.insts)} instances placed by their hints, "
                     f"{len(lay.entities)} entities, {lay.size[0]}x{lay.size[1]}; "
                     + ", ".join(f"{n} {c}" for c, n in sorted(count.items())))
        lines += [f"  {path}: {c}" for path, c in sorted(cls.items()) if c != "unchanged"]
        lines += [f"  placed {line}" for line in placed]
        checks += [Check("UNPLACED", p.factory, n) for n in notes]
        checks += _invariant_checks(p.factory, fkp.invariants(lay, ctx.cat))
    return lines, checks


def _pinned_routes(flat, new, prev, cat):
    """The committed routes the router may keep (route --only stale): -> ({net: its committed
    carriers}, {net: why it is routed again}). A net is routed again when an end its route is
    laid to moved (``route.NetJob.moved_ends``: a belt end, or a machine it inserts into or
    picks from), when the new layout takes one of its tiles, or (a fluid net) when its ends
    changed at all. Every other committed route goes to the router, which keeps it as it stands,
    patches it for the ends added and dropped, or routes the net again (``route._standing``).

    2.0 (Rory, 2026-10-21): "Pin what stands and make patch changes rather than regenerating
    the base": a consumer added to a net no longer re-lays the whole net."""
    if prev is None:
        return {}, {}
    old = route.jobs(flat, prev, cat) if prev.insts else {}
    now = route.jobs(flat, new, cat)
    taken = set()
    for e in new.entities.values():
        taken |= fkp.tiles_of(cat, e)
    pinned, again = {}, {}
    by_net = {}
    for e in prev.entities.values():
        if e.owner.startswith("~"):
            by_net.setdefault(e.owner[1:], []).append(e)
    for net, ents in sorted(by_net.items()):
        if net not in now:
            continue
        moved = now[net].moved_ends(old[net]) if net in old else []
        if moved:
            again[net] = f"its ends moved since the committed .fkp ({', '.join(moved)})"
            continue
        if net not in old or (now[net].fluid and old[net].signature() != now[net].signature()):
            again[net] = "its ends changed since the committed .fkp"
            continue
        tiles = set()
        for e in ents:
            tiles |= fkp.tiles_of(cat, e)
        if tiles & taken:
            again[net] = "the new layout takes some of its tiles"
            continue
        taken |= tiles
        pinned[net] = [fkp.Entity(e.key, e.name, e.x, e.y, e.dir, dict(e.attrs)) for e in ents]
    return pinned, again


def _one_inserter(ctx, factory, flat, lay):
    """2.0 (Rory, 2026-10-21): a sushi net laid as one inserter from its source straight into
    each sink can't clog (the inserter takes only what the sink accepts), so its ``CLOG`` line
    from elaborate goes; on any other route it stays. -> the report lines that say so."""
    sushi = {n: e for n, e in connect.endpoints(flat).items()
             if flat.nets[n].sushi and not flat.nets[n].limited}
    if not sushi:
        return []
    clear = connect.one_inserter(lay, ctx.cat, sushi)
    where = {f"{factory} net {n}" for n in clear}
    ctx.checks = [(s, c) for s, c in ctx.checks if not (c.code == "CLOG" and c.where in where)]
    return [f"  one hand  {n}: one inserter from its source straight into each sink, which takes "
            "only what the sink accepts: no CLOG" for n in sorted(clear)]


def _frame_blocked(ctx, factory, size):
    """The terrain's blocked tiles in ``factory``'s frame (empty on a paper surface)."""
    if ctx.ground is None or ctx.surface is None or factory not in ctx.surface.places:
        return frozenset()
    p = ctx.surface.places[factory]
    return terrainmod.frame_blocked(ctx.ground, p, size or terrainmod.frame_size(p))


def _need(ctx, kind):
    """How many entities of ``kind`` the design holds (its committed layout when this build has
    none yet): what a family choice must be able to build, at least. A tier the network holds one
    or two of is no better than none for forty, and this keeps ``any`` from choosing it."""
    lays = list(ctx.layouts.values()) or list(ctx.previous.values())
    n = sum(1 for lay in lays for e in lay.entities.values()
            if ctx.cat.has_entity(e.name) and ctx.cat.kind(e.name) == kind)
    return max(n, 1)


def s_route(ctx, args):
    o = _opts(args, only="all", effort="normal", hand="fast-inserter")
    hand, _note = availmod.choose("hand", o["hand"], need=_need(ctx, "inserter"))
    limit, retries = (400000, None) if o["effort"] == "high" else (60000, None)
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        flat = ctx.flats[factory]
        pinned, again = {}, {}
        if o["only"] == "stale":
            pinned, again = _pinned_routes(flat, lay, ctx.previous.get(factory), ctx.cat)
        blocked = _frame_blocked(ctx, factory, lay.size)
        r = route.route_layout(flat, lay, ctx.cat, limit=limit, retries=retries, blocked=blocked,
                               hand=hand, patch=pinned)
        r.layout, rehanded = _rehand(r.layout, ctx.cat, hand)
        again.update(r.again)
        ctx.layouts[factory] = r.layout
        lines.append(f"{factory}: {len(r.routed)} routed, {len(r.kept)} kept"
                     + (f", {len(r.patched)} patched" if r.patched else "")
                     + f" ({len(pinned)} pinned from the committed .fkp), {len(r.failed)} failed, "
                     f"{r.passes} pass{'es' if r.passes != 1 else ''}"
                     + (f"; {len(blocked)} terrain tiles kept clear" if ctx.ground is not None
                        else ""))
        lines += [f"  stale     {n}: routed again: {why}" for n, why in sorted(again.items())]
        if rehanded:
            lines.append(f"  rehanded  {rehanded} standing inserter"
                         f"{'s' if rehanded != 1 else ''} robots cannot build, to {hand}")
        lines += [f"  {l}" for l in r.lines]
        lines += _one_inserter(ctx, factory, flat, r.layout)
        checks += [Check("UNROUTED", f"{factory} net {n}", why) for n, why in r.failed.items()]
        checks += [Check("UNROUTED", f"{factory} net {l.split(':')[0].split()[-1]}",
                         l.split(": ", 1)[1]) for l in r.lines if l.startswith("skipped")]
        checks += _invariant_checks(factory, fkp.invariants(r.layout, ctx.cat, nets=flat.nets))
    return lines, checks


def _rehand(lay, cat, hand):
    """The standing route's inserters that robots cannot build now take ``hand`` instead: -> (new
    layout, how many changed). A route that stands keeps its carriers (2.0), so ``--hand any`` alone
    would leave the fast inserter a run pasted while none was researched exactly where it was: the
    2026-10-25 run's four LOCKED ghosts, on a net that never changes. Only a short hand becomes
    another short hand (the footprint is one tile either way), only one the network cannot build
    now is touched, and only when it can build ``hand``: an inserter that stands built is left
    alone, since it works and its speed is not worth losing."""
    out = dict(lay.entities)
    n = 0
    for key, e in lay.entities.items():
        if not e.owner.startswith("~") or not cat.has_entity(e.name) \
                or cat.kind(e.name) != "inserter" or e.name == hand:
            continue
        if connect.REACH.get(e.name, 1) != 1 or connect.REACH.get(hand, 1) != 1:
            continue
        if availmod.buildable(e.name) or not availmod.buildable(hand):
            continue
        out[key] = fkp.Entity(e.key, hand, e.x, e.y, e.dir, dict(e.attrs))
        n += 1
    if not n:
        return lay, 0
    return fkp.Layout(lay.level, lay.name, lay.size, dict(lay.insts), dict(lay.covers),
                      dict(lay.plots), dict(lay.claims), dict(lay.marks), out), n


def s_tier(ctx, args):
    """Belt tiers per connector (CORE-V2, ``fkcore.tiers``): ``tier minimize|maximize|yellow``
    (default minimize) ``--allow yellow,red,blue,turbo`` (the tiers it may use; default yellow,
    which yellow always is) ``--red N --blue N --turbo N`` (at most N entities gain a tier),
    ``--downgrade`` (minimize and maximize may go below the tier a belt has; without it they
    never do), ``--hand N`` / ``--bulk-hand N`` (the inserter hand sizes, as for report_rates)."""
    from . import tiers
    o = _opts(args, allow="yellow", hand="auto", bulk_hand="auto")
    mode = (o.get("_") or ["minimize"])[0]
    allow = [t.strip() for t in str(o["allow"]).split(",") if t.strip()] \
        if o["allow"] is not True else []
    unknown = sorted(set(allow) - set(tiers.TIERS))
    if unknown or not allow or mode not in ("minimize", "maximize", "yellow"):
        raise FlowError("tier minimize|maximize|yellow [--allow yellow,red,blue,turbo] "
                        "[--red N] [--blue N] [--turbo N] [--downgrade]"
                        + (f": unknown tier {', '.join(unknown)}" if unknown else ""))
    budgets = {t: _count(o, t) for t in tiers.TIERS if o.get(t) is not None}
    hand, bulk, note = _hands(ctx, o)
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        new, tlines, _changed = tiers.assign(ctx.flats[factory], lay, ctx.cat, mode, allow,
                                             budgets, hand=hand, bulk_hand=bulk,
                                             downgrade=o.get("downgrade") is True)
        ctx.layouts[factory] = new
        lines += [f"{factory}: {tlines[0]}"] + tlines[1:]
        checks += _invariant_checks(factory, fkp.invariants(new, ctx.cat))
    return lines + [note], checks


def _own(prev, owner, prefix):
    """The committed .fkp's own entities of cover ``owner`` keyed ``<owner>/<prefix><k>``."""
    if prev is None:
        return []
    pat = re.compile(re.escape(prefix) + r"\d+")
    return [e for e in prev.entities.values()
            if e.owner == owner and pat.fullmatch(e.key[len(owner) + 1:])]


def s_cover_power(ctx, args):
    """Poles for every electric entity (``fkcore.cover``). 1.7 (Rory, 2026-10-21: pin and patch):
    the committed poles stay where they still fit and new ones go only where coverage is missing;
    ``--fresh`` lays every pole anew, as before."""
    o = _opts(args, pole="medium-electric-pole")
    pole, _note = availmod.choose("pole", o["pole"], need=_need(ctx, "electric-pole"))
    if not ctx.cat.has_entity(pole) or ctx.cat.kind(pole) != "electric-pole":
        raise FlowError(f"--pole {pole}: not an electric pole (small-electric-pole, "
                        "medium-electric-pole, big-electric-pole, substation), or any")
    try:
        from . import cover
    except ImportError:
        return ["cover power: fkcore.cover is not built yet; nothing placed"], [
            Check("NO_POWER", "all factories", "no power coverage step yet")]
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        keep_out = _frame_blocked(ctx, factory, lay.size)
        pinned = [] if o.get("fresh") is True else _own(ctx.previous.get(factory), "power", "p")
        standing = _standing(ctx, factory)
        _poles, rep = cover.cover_power(lay, ctx.cat, pole=pole, keep_out=keep_out,
                                        pinned=pinned, standing=standing)
        new = cover.apply_cover(lay, ctx.cat, pole=pole, keep_out=keep_out, pinned=pinned,
                                standing=standing)
        ctx.layouts[factory] = new
        lines.append(f"{factory}: {rep.summary()}"
                     + (f"; {len(keep_out)} terrain tiles kept out" if ctx.ground is not None
                        else ""))
        checks += [Check(c.code, f"{factory} {c.where}", c.msg) for c in rep.checks]
        checks += _invariant_checks(factory, fkp.invariants(new, ctx.cat))
    return lines, checks


def _infra(ctx):
    """The surface .fkp's own entities (shared infrastructure: the kit's roboport, the bridge),
    as last written; [] before the first floorplan."""
    path = os.path.join(ctx.root, f"{ctx.surface.name}.fkp") if ctx.surface is not None else None
    if path is None or not os.path.exists(path):
        return []
    return list(fkp.load(path).entities.values())


def s_cover_robots(ctx, args):
    """Roboports so every logistic chest of a factory is in a logistic area (``fkcore.robots``);
    before ``cover power`` in the script, so the poles power them. A chest the surface's network
    already reaches (the kit's roboport and every roboport joined to it) needs none (1.2), and
    each roboport placed gets a storage chest beside it (``--storage none``: no chest). 1.7 (pin
    and patch): the committed roboports and their chests stay where they still fit and reach a
    chest; ``--fresh`` places them all anew, as before."""
    from . import robots
    o = _opts(args, roboport="roboport", storage="storage-chest")
    if ctx.surface is not None and ctx.surface.mode == "lab":
        return ["cover robots: lab mode revives the ghosts, no robots build here; nothing placed"], []
    storage = None if o["storage"] in ("none", "off") else \
        ("storage-chest" if o["storage"] is True else o["storage"])
    if storage and not ctx.cat.has_entity(storage):
        return [f"cover robots: no {storage} in the catalog; nothing placed"], [
            Check("NO_ROBOTS", "cover robots", f"--storage {storage}: not an entity")]
    infra = _infra(ctx)
    places = ctx.surface.places if ctx.surface is not None else {}
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        near = robots.served(places, infra, ctx.layouts, factory, ctx.cat)
        keep_out = _frame_blocked(ctx, factory, lay.size)        # no roboport or chest on water
        prev = ctx.previous.get(factory)
        pinned = [] if o.get("fresh") is True else \
            _own(prev, "robots", "r") + _own(prev, "robots", "s")
        new, rep = robots.apply_robots(lay, ctx.cat, keep_out=keep_out, roboport=o["roboport"],
                                       served=near, storage=storage, pinned=pinned)
        ctx.layouts[factory] = new
        lines.append(f"{factory}: {rep.summary()}")
        checks += [Check(c.code, f"{factory} {c.where}", c.msg) for c in rep.checks]
        checks += _invariant_checks(factory, fkp.invariants(new, ctx.cat))
    return lines, checks


_BRIDGE_POLE = re.compile(r"bridge/p\d+")      # the bridge's own poles (cover bridge power)


def _bridge_in_plots(ents, sf, cat):
    """The bridge's own poles that stand in a plot of the surface file: -> (the entities without
    them, their keys). A plot laid over an old bridge takes its poles, and ``--bridge-power``
    lays the bridge again around the plots (1.2: the 0534 run's new plot stopped the build with
    INVARIANT shared infrastructure)."""
    boxes = [(p.x, p.y, p.x + p.w, p.y + p.h) for p in sf.places.values()
             if p.lifecycle != "retired"]
    keep, gone = {}, []
    for key, e in ents.items():
        if _BRIDGE_POLE.fullmatch(key) and cat.has_entity(e.name) \
                and cat.kind(e.name) == "electric-pole" \
                and any(b[0] <= x < b[2] and b[1] <= y < b[3] for b in boxes
                        for x, y in fkp.tiles_of(cat, e)):
            gone.append(key)
            continue
        keep[key] = e
    return keep, sorted(gone, key=fkp.natural_key)


def _circuits(ctx):
    """2.0 (circuits in the source, ``fkcore.circuits``): each factory's circuit settings and
    wires, laid again from its source on the layout as it stands, before the floorplan composes
    it. -> (report lines, checks)."""
    from . import circuits
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        flat = ctx.flats.get(factory)
        if flat is None:
            continue
        new, clines, cchecks = circuits.lay(flat, lay, ctx.cat)
        ctx.layouts[factory] = new
        lines += [f"circuits {factory}: {line}" for line in clines]
        checks += [Check(c.code, f"{factory} {c.where}", c.msg) for c in cchecks]
        checks += _invariant_checks(factory, fkp.invariants(new, ctx.cat))
    return lines, checks


def s_floorplan(ctx, args):
    sf = ctx.surface
    o = _opts(args)
    infra_path = os.path.join(ctx.root, f"{sf.name}.fkp")
    infra = None
    lines, checks = _circuits(ctx)
    if os.path.exists(infra_path):
        prev = fkp.load(infra_path)
        ents = prev.entities
        if o.get("bridge_power"):
            ents, gone = _bridge_in_plots(prev.entities, sf, ctx.cat)
            if gone:
                lines.append(f"bridge power: {len(gone)} of its poles stand in a plot now "
                             f"({', '.join(gone)}): taken out, the bridge is laid again around "
                             "the plots")
        infra = fkp.Layout("surface", sf.name, covers=prev.covers, marks=prev.marks,
                           entities=ents)
    ctx.surface_lay = surfacemod.floorplan(sf, infra)
    ctx.composed = compose.compose(ctx.surface_lay, ctx.layouts, ctx.cat)
    if o.get("bridge_power"):
        from . import cover
        pole = o["bridge_power"] if isinstance(o["bridge_power"], str) else "medium-electric-pole"
        pole, _note = availmod.choose("pole", pole, need=_need(ctx, "electric-pole"))
        if not ctx.cat.has_entity(pole) or ctx.cat.kind(pole) != "electric-pole":
            raise FlowError(f"--bridge-power {pole}: not an electric pole (small-electric-pole, "
                            "medium-electric-pole, big-electric-pole, substation), or any")
        s = ctx.composed
        keep = set()
        for p in s.plots.values():
            keep |= {(x, y) for x in range(p.x, p.x + p.w) for y in range(p.y, p.y + p.h)}
        for c in s.claims.values():
            keep |= {(x, y) for x in range(c.x0, c.x1) for y in range(c.y0, c.y1)}
        for m in s.marks.values():
            keep |= {(int(x), int(y)) for x, y in m.tiles}
        keep |= ctx.terrain                          # no bridge pole on water or a cliff
        poles, blines = cover.bridge(list(s.entities.values()), ctx.cat, keep, pole)
        if poles and "bridge" not in ctx.surface_lay.covers:
            ctx.surface_lay.covers["bridge"] = fkp.Cover("bridge", "power", {"pole": pole})
        for e in poles:
            ctx.surface_lay.add(e)
        lines += [f"bridge power: {l}" for l in blines] or ["bridge power: every network is "
                                                             "already joined"]
        ctx.composed = compose.compose(ctx.surface_lay, ctx.layouts, ctx.cat)
    s = ctx.composed
    lines.insert(0, f"surface {sf.name}: {len(s.plots)} plots, {len(s.claims)} claims, "
                    f"{len(s.marks)} marks, {len(s.entities)} entities composed, {len(s.tiles)} tiles")
    if ctx.ground is not None:
        tlines, tchecks = _on_terrain(ctx.ground, s, ctx.cat)
        lines += tlines
        checks += tchecks
    for name, p in sorted(s.plots.items()):
        lay = ctx.layouts.get(name)
        size = f"{lay.size[0]}x{lay.size[1]}" if lay is not None and lay.size else "?"
        lines.append(f"  plot {name} at {p.x},{p.y} rot {p.rot} {p.w}x{p.h} (factory {size})")
    try:
        from . import cover
    except ImportError:
        cover = None
    if cover is not None:
        nets = cover.networks(list(s.entities.values()), ctx.cat)
        lines.append(f"power: {len(nets)} wire network{'s' if len(nets) != 1 else ''}, "
                     f"{sum(1 for n in nets if n['sources'])} with generation")
        for name in sorted(s.plots):
            mine = {k for k in s.entities if k.startswith(f"{sf.name}:{name}/")
                    and ctx.cat.kind(s.entities[k].name) == "electric-pole"}
            powered = any(n["sources"] for n in nets if mine & set(n["poles"]))
            lines.append(f"  {name}: {len(mine)} poles, "
                         + ("on a grid with generation" if powered else "NOT on a grid with "
                                                                         "generation"))
            if mine and not powered:
                checks.append(Check("NO_POWER", f"{sf.name} {name}",
                                    "its grid reaches no generator (bridge it: floorplan "
                                    "--bridge-power)"))
    from . import robots
    rlines, rchecks = robots.check_surface(s, ctx.cat)
    return lines + rlines, checks + rchecks + _invariant_checks(sf.name, s.problems)


def _on_terrain(t, s, cat):
    """``ON_TERRAIN``: a composed entity on blocked ground (water, cliff); ``OFF_ORE``: a drill
    with no ore of its resource in its mining area (the game would not place it); ``OFF_WATER``
    (1.4.2): an offshore pump whose water tiles are dry ground (the lead world's kickoff plant
    stood where world 3 had a lake: no water, no power, and every look said OK). -> (report
    lines, checks); checks, never gates."""
    lines, checks, hits = [], [], 0
    for key in sorted(s.entities, key=fkp.natural_key):
        e = s.entities[key]
        tiles = set(e.tiles)
        parts = [(len(tiles & t.water), "water"), (len(tiles & t.cliff_tiles), "cliff"),
                 (len(tiles & t.other), "other blocked")]
        if not any(n for n, _k in parts):
            continue
        hits += 1
        first = min(tiles & t.blocked, key=lambda q: (q[1], q[0]))
        what = ", ".join(f"{n} {k}" for n, k in parts if n)
        checks.append(Check("ON_TERRAIN", key,
                            f"{e.name} at {fkp.fmt(e.x)},{fkp.fmt(e.y)} stands on {what} "
                            f"tile{'s' if sum(n for n, _k in parts) != 1 else ''} (first "
                            f"{first[0]},{first[1]})"))
    x0, y0, x1, y1 = t.area
    unknown = {tuple(c) for c in t.ungenerated}
    for key in sorted(s.entities, key=fkp.natural_key):
        e = s.entities[key]
        wet = cat.water_tiles(e.name, e.x, e.y, e.dir) if cat.has_entity(e.name) else set()
        seen = {q for q in wet if x0 <= q[0] < x1 and y0 <= q[1] < y1
                and (q[0] // 32, q[1] // 32) not in unknown}
        dry = sorted(seen - t.water, key=lambda q: (q[1], q[0]))
        if dry:
            checks.append(Check("OFF_WATER", key,
                                f"{e.name} at {fkp.fmt(e.x)},{fkp.fmt(e.y)}: {len(dry)} of the "
                                f"{len(wet)} tiles it pumps from are not water (first "
                                f"{dry[0][0]},{dry[0][1]}): it gives no water"))
    drills = sorted((e for e in s.entities.values() if e.attrs.get("resource")
                     and cat.has_entity(e.name) and cat.kind(e.name) == "mining-drill"),
                    key=lambda e: fkp.natural_key(e.key))
    full = under = amount = 0
    for e in drills:
        ore = t.resources.get(e.attrs["resource"], {})
        body = [ore[q] for q in e.tiles if q in ore]
        full += len(body) == len(e.tiles)
        under += len(body)
        amount += sum(body)
        if not any(q in ore for q in placer.mining_area(e.name, float(e.x), float(e.y))):
            checks.append(Check("OFF_ORE", e.key,
                                f"{e.name} at {fkp.fmt(e.x)},{fkp.fmt(e.y)}: no "
                                f"{e.attrs['resource']} in its mining area"))
    lines.append(f"terrain: {hits} of {len(s.entities)} entities on blocked ground; "
                 + (f"{full}/{len(drills)} drills with ore under every tile, {under} ore tiles "
                    f"under them ({terrainmod.fmt_amount(amount)})" if drills else "no drills"))
    return lines, checks


def _bootstrap_checks(ctx, factory, flat, lay):
    """BOOTSTRAP (2.0.4, the live run's mall): a net whose own route needs a building item (a
    belt, an underground, a splitter, an inserter ...: a carrier whose name is also an item) that
    only makers fed from that same net make. Then the route cannot be built before its makers,
    and its makers cannot run before the route is built.

    For each net: the items of the carriers on it (``e.attrs["net"]``, lanes included), the
    machines that make each item, and whether every one of them takes an item from this net. One
    line per net, and none when there is no maker in the factory (the item comes from outside, a
    raw resource or stock) or a maker independent of the net (a second row, a requester chest)."""
    on_net = {}
    for e in lay.entities.values():
        for name in fkp.net_names(e.attrs.get("net")):
            on_net.setdefault(name, []).append(e)
    out = []
    for net in flat.nets.values():
        ents = on_net.get(net.name)
        if not ents:
            continue
        counts = {}
        for e in ents:
            counts[e.name] = counts.get(e.name, 0) + 1
        fed_by = {key for key, _item in net.consumers}
        rows = []
        for item in sorted(counts, key=lambda i: (-counts[i], i)):
            if not ctx.cat.is_item(item):
                continue                    # not a building item (a carrier that is no item)
            makers = [m for m in flat.machines.values() if item in m.makes]
            if not makers:                  # it comes from outside: stock, a raw resource
                continue
            if not all(m.key in fed_by for m in makers):
                continue                    # a maker that does not depend on this net
            keys = {m.key for m in makers}
            takes = sorted({i for key, i in net.consumers if key in keys})
            rows.append((item, counts[item], makers, takes))
        if not rows:
            continue
        clauses = []
        for item, _count, makers, takes in rows:
            insts = sorted({f"{factory}/{m.inst}" for m in makers})
            only = f"the only maker ({insts[0]})" if len(insts) == 1 \
                else f"the only makers ({', '.join(insts)})"
            clauses.append(f"{only} {'takes' if len(insts) == 1 else 'take'} "
                           f"{', '.join(takes)} from this same net")
        if len(rows) == 1:
            msg = (f"its route needs {rows[0][1]} {rows[0][0]}, and {clauses[0]}: stock the "
                   f"{rows[0][0]} first, or build that maker first")
        else:
            needs = " and ".join(f"{count} {item}" for item, count, _m, _t in rows)
            detail = "; ".join(f"{item}: {clause}" for (item, _n, _m, _t), clause
                               in zip(rows, clauses))
            msg = (f"its route needs {needs}: {detail}: stock what the route needs first, or "
                   "build those makers first")
        out.append(Check("BOOTSTRAP", f"net {factory}/{net.name}", msg))
    return out


def s_report_checks(ctx, args):
    """Connectivity of every net and the invariants, now; then every check line of the run."""
    lines, checks = [], []
    for factory, lay in ctx.layouts.items():
        flat = ctx.flats[factory]
        rep = connect.connect(lay, ctx.cat, connect.endpoints(flat))
        lines.append(f"{factory}: {rep.summary()}")
        checks += [Check(c.code, f"{factory} {c.where}", c.msg) for c in rep.checks]
        sink_lines, sink_checks = _sinks(ctx, factory, flat, rep)
        lines += sink_lines
        checks += sink_checks
        checks += _invariant_checks(factory, fkp.invariants(lay, ctx.cat, nets=flat.nets))
        seen = {c.where for _step, c in ctx.checks if c.code == "BOOTSTRAP"}
        checks += [c for c in _bootstrap_checks(ctx, factory, flat, lay) if c.where not in seen]
    if ctx.composed is not None:
        checks += _invariant_checks(ctx.surface.name, ctx.composed.problems)
    run = [(step, c) for step, c in ctx.checks] + [("report_checks", c) for c in checks]
    codes = {}
    for _step, c in run:
        codes[c.code] = codes.get(c.code, 0) + 1
    lines.append("check lines this run: " + (", ".join(f"{k} {v}" for k, v in sorted(codes.items()))
                                             or "none"))
    lines += [f"  {step:<13} {c}" for step, c in run]
    return lines, checks


#: the machines that make something for a net (2.0.12, NO_SINK)
_MAKERS = ("assembling-machine", "furnace", "mining-drill")


def _sinks(ctx, factory, flat, rep):
    """2.0.12: does each maker's product reach a sink? One report line, and ``NO_SINK`` for a
    maker whose product reaches none of the consumers of a net it drives while the net's other
    pairs connect (a net none of whose pairs connect has its UNROUTED line). The solo run's Mall4
    went out with its products belt unrouted and its makers had no output (2026-10-23 23:23)."""
    def maker(m):
        try:
            return bool(m.makes) and not m.source and ctx.cat.kind(m.prototype) in _MAKERS
        except KeyError:
            return False
    makers = {k for k, m in flat.machines.items() if maker(m)}
    feeding = {d for r in rep.nets.values() if r.consumers for d in r.drivers if d in makers}
    if not feeding:
        return [], []
    cut = connect.cut_off(rep, makers)
    keys = sorted({k for k, _n, _c in cut}, key=fkp.natural_key)
    line = (f"  sinks     {len(feeding) - len(keys)} of {len(feeding)} makers on a net reach a sink "
            "with what they make")
    if cut:
        line += ("; none reached: " + ", ".join(f"{k} (net {n})" for k, n, _c in cut[:4])
                 + (f" ... {len(cut) - 4} more" if len(cut) > 4 else ""))
    checks = [Check("NO_SINK", f"{factory} {k}",
                    f"what it makes reaches none of the {c} consumer{'s' if c != 1 else ''} of net "
                    f"{n}: it has nowhere to go")
              for k, n, c in cut if rep.nets[n].reached]
    return [line], checks


def _to_build(ctx):
    """{entity: count} still to build: after a diff its MISSING, GHOST and WRONG entities, else
    the whole composed design."""
    need = {}
    if ctx.last_diff is not None:
        for v in ctx.last_diff.verdicts:
            if v.verdict.split()[0] in ("MISSING", "GHOST", "WRONG"):
                need[v.name] = need.get(v.name, 0) + 1
        return need, "what the last diff found missing, ghosted or wrong"
    for e in (ctx.composed.entities.values() if ctx.composed is not None else ()):
        need[e.name] = need.get(e.name, 0) + 1
    return need, "the whole design (no diff before this step)"


def _bom_live(ctx):
    """report_bom --stock live: what still has to be built against the network's stock, and every
    item and machine recipe against what is researched (LOW_STOCK, LOCKED). The first V1 run
    (2026-10-20) waited on 295 ghosts the network held nothing for."""
    from . import supply
    r = _link(ctx)
    if r is None:
        return [f"report_bom --stock live: skipped, no game link ({ctx.link_error})"], []
    need, what = _to_build(ctx)
    used = sorted({e.attrs["recipe"] for e in (ctx.composed.entities.values() if ctx.composed
                                                else ()) if e.attrs.get("recipe")
                   and ctx.cat.kind(e.name) == "assembling-machine"})
    # the availability families too: this is the read the next (linkless) build's inserter=any,
    # --hand any and --pole any choose from (out/avail.json, beside out/force.json)
    sup = supply.read(r, _force(ctx), ctx.surface.name, list(need) + list(availmod.CANDIDATES),
                      used)
    availmod.save(ctx.root, sup, "report_bom --stock live")
    lines, checks = supply.bom(need, sup, used)
    lines = ([lines[0], f"  to build: {what}; {sum(need.values())} entities",
              f"  {supply.research_line(sup.research)}"] + lines[1:])
    # the first lead run (2026-10-21): a paste took up the burner row before the 137 belts its
    # replacement needed were made (23 in stock), and iron stood still until they were
    short = [c.where for c in checks if c.code == "LOW_STOCK"]
    running = _machines_taken_up(ctx) if short else []
    if running:
        warn = (f"the paste takes up {len(running)} machine{'s' if len(running) != 1 else ''} "
                f"that stand now while {len(short)} kind{'s' if len(short) != 1 else ''} it lays "
                f"are SHORT ({', '.join(short[:6])}): what they make stops until those are made; "
                "`stop_on LOW_STOCK` in the build script holds the paste until the network has them")
        lines.append(f"  {warn}")
        checks.append(Check("RIP", ctx.surface.name, warn))
    return lines, checks


#: what a paste that takes it up stops (2.0, report_bom's warning)
_MACHINE_KINDS = ("assembling-machine", "furnace", "mining-drill", "lab", "boiler", "generator",
                  "rocket-silo")


def _machines_taken_up(ctx):
    """The built machines the last diff says the paste takes up: a NOBODY one that is no ghost,
    and what stands built under a WRONG verdict. [name]."""
    if ctx.last_diff is None:
        return []

    def machine(name):
        try:
            return ctx.cat.kind(name) in _MACHINE_KINDS
        except (KeyError, ValueError):
            return False
    out = []
    for v in ctx.last_diff.verdicts:
        head = v.verdict.split()[0]
        if head == "NOBODY" and not v.ghost and machine(v.name):
            out.append(v.name)
        elif head == "WRONG":
            out += [u[0] for u in v.under if len(u) > 4 and not u[4] and machine(u[0])]
    return out


def s_report_bom(ctx, args):
    o = _opts(args, stock="none")
    if o["stock"] == "live":
        return _bom_live(ctx)
    need = {}
    ents = (ctx.composed.entities.values() if ctx.composed is not None
            else [e for lay in ctx.layouts.values() for e in lay.entities.values()])
    for e in ents:
        need[e.name] = need.get(e.name, 0) + 1
    stock = None
    if o["stock"] == "live":
        lines = ["stock live: needs the game link, which this offline build has not; needs only"]
    elif o["stock"] != "none":
        with open(os.path.join(ctx.root, o["stock"]), encoding="utf-8") as fh:
            stock = json.load(fh)
        lines = [f"stock from {o['stock']}"]
    else:
        lines = ["stock none: needs only"]
    checks = []
    for name in sorted(need, key=lambda n: (-need[n], n)):
        have = None if stock is None else int(stock.get(name, 0))
        lines.append(f"  {name:<28} {need[name]:>5}" + ("" if have is None else f"  have {have}"))
        if have is not None and have < need[name]:
            checks.append(Check("LOW_STOCK", name, f"need {need[name]}, have {have}"))
    lines.append(f"  {'total':<28} {sum(need.values()):>5}")
    return lines, checks


def s_write_layout(ctx, args):
    lines, checks = [], []
    if ctx.surface is not None and ownmod.load(ctx.root, ctx.surface.name) is None:
        # 1.2: the toolkit's own entities start as the .fkp files last written (what was built
        # from them), before this step writes the new ones; each play apply keeps it after that
        record = ownmod.seed(ctx.root, ctx.surface.name, ctx.cat)
        ownmod.save(ctx.root, ctx.surface.name, record)
        lines.append(f"own: {len(record)} entities of the last written .fkp files are the "
                     f"toolkit's own (out/own/{ctx.surface.name}.json)")
    for p in _factories(ctx):
        lay = ctx.layouts.get(p.factory)
        if lay is None:
            continue
        path = os.path.join(ctx.root, f"{p.module}.fkp")
        try:
            fkp.save(lay, path, ctx.cat)
            lines.append(f"wrote {os.path.basename(path)}: {len(lay.entities)} entities")
        except fkp.InvariantError as exc:
            checks += _invariant_checks(p.factory, exc.problems)
    if ctx.surface_lay is not None:
        path = os.path.join(ctx.root, f"{ctx.surface.name}.fkp")
        try:
            fkp.save(ctx.surface_lay, path, ctx.cat)
            lines.append(f"wrote {os.path.basename(path)}: {len(ctx.surface_lay.plots)} plots")
        except fkp.InvariantError as exc:
            checks += _invariant_checks(ctx.surface.name, exc.problems)
    # 2.0.4: the source these .fkp files were laid from, for the look (layout_source_changes)
    os.makedirs(ctx.out, exist_ok=True)
    with open(os.path.join(ctx.out, _LAID_FILE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"files": ctx.source}, fh, indent=0, sort_keys=True)
        fh.write("\n")
    return lines, checks


def _link(ctx):
    """The game link, opened on first use; None (``ctx.link_error`` says why) without one."""
    if ctx.link is None and ctx.link_error is None:
        from . import link
        ctx.link, ctx.link_error = link.open_from_env()
    return ctx.link


def _scope(ctx, o):
    """(area, key prefixes) from --area X0,Y0,X1,Y1 and --plot NAME[,NAME]; None, None = all."""
    area = tuple(int(v) for v in o["area"].split(",")) if isinstance(o.get("area"), str) else None
    keys = None
    if isinstance(o.get("plot"), str):
        keys = [f"{ctx.surface.name}:{p}/" for p in o["plot"].split(",")]
        if area is None:
            boxes = [ctx.composed.plots[p].box() for p in o["plot"].split(",")
                     if p in ctx.composed.plots]
            if boxes:
                area = (min(b[0] for b in boxes) - 2, min(b[1] for b in boxes) - 2,
                        max(b[2] for b in boxes) + 2, max(b[3] for b in boxes) + 2)
    return area, keys


def _net_items(ctx):
    return {f"{factory}/{n}": list(net.items) for factory, flat in ctx.flats.items()
            for n, net in flat.nets.items()}


def s_diff(ctx, args):
    o = _opts(args, scope="all")
    if ctx.composed is None:
        return ["diff: no composed surface yet (floorplan first)"], []
    r = _link(ctx)
    if r is None:
        return [f"diff: skipped, no game link ({ctx.link_error})"], []
    from . import apply as applymod
    area, keys = _scope(ctx, o)
    own = ownmod.load(ctx.root, ctx.surface.name)
    if area is None:
        area = applymod.default_area(ctx.composed, ctx.cat, keys, own)
    if area is None:
        return ["diff: nothing is designed on this surface"], []
    rep = applymod.diff(r, ctx.composed, ctx.cat, area, ctx.surface, _net_items(ctx), own=own,
                        force=_force(ctx))
    try:
        _save_hands(ctx, r)            # for the next build's rates and tiers, on the laptop
    except Exception:                  # noqa: BLE001 - they fall back to hand 1, and say so
        pass
    try:
        _save_standing(ctx, rep)       # for the next build's cover step, on the laptop
    except (OSError, ValueError):
        pass
    ghosts = sorted({v.name for v in rep.verdicts if v.verdict == "GHOST"})
    if ghosts:
        from . import supply
        supply.mark_ghosts(rep.verdicts, supply.read(r, _force(ctx), ctx.surface.name, ghosts))
    ctx.last_diff = rep
    checks = [Check("DIFF", ctx.surface.name, f"{k} {n}") for k, n in sorted(rep.counts().items())
              if k != "OK"]
    lines = rep.lines()
    # 2.0 (Rory, 2026-10-21): a hand change the build would replace is said before the paste
    from . import sense
    hand = sense.hand_edits(rep)
    if hand:
        lines.append(f"hand: {len(hand)} hand edits that the apply would replace, remove or set "
                     "back:")
        lines += [f"  {line}" for line in hand]
        checks += [Check("HAND", ctx.surface.name, line) for line in hand]
    turned = _turned(ctx, rep)
    if turned:
        lines.append(f"  {turned.msg}")
        checks.append(turned)
    if ctx.surface.mode != "lab":
        far = _unreached(ctx, r, rep)
        if far:
            lines.append(f"  {far.msg}")
            checks.append(far)
    pts = applymod.rip_points(rep)
    if pts and ctx.surface.mode != "lab":
        # 1.1: what the apply will take up, and how long the robots need for it (before it starts)
        from . import link
        try:
            load = applymod.rip_load(r, ctx.surface.name, _force(ctx), pts)
        except (ValueError, OSError, link.LinkError) as exc:
            lines.append(f"rip: not estimated ({type(exc).__name__}: {exc})")
        else:
            line, warn = applymod.rip_report(load, applymod.moved(rep))
            lines.append(line)
            if warn:
                checks.append(Check("RIP", ctx.surface.name, warn))
    return lines, checks


#: the diff's verdicts the paste lays an entity for
_TO_LAY = ("MISSING", "GHOST", "WRONG")


def _turned(ctx, rep):
    """A ``TURNED`` check for the belts, undergrounds, splitters, inserters (and pipes-to-ground,
    pumps, drills) that stand, or wait as ghosts, on their design entity's position under its name
    but facing another way or as the other underground end, or None. Their lines stop there. 2.0.5
    (the 2.0 run's south iron array, 2026-10-22): a factory built over another kept the old one's
    belts wherever the names matched, facing the old ways; on uncharted ground the paste turns
    nothing, so every build kept them, and the diff's DRIFT count said so only as a number. The
    apply now orders them out and lays them fresh as designed."""
    bad = [v for v in rep.verdicts if v.turned]
    if not bad:
        return None
    shown = ", ".join(f"{(v.key or v.name).split(':', 1)[-1]} "
                      f"({'a ghost' if v.verdict.startswith('GHOST') else v.detail})"
                      for v in bad[:4])
    names = sorted({v.name for v in bad})
    msg = (f"{len(bad)} {', '.join(names)} stand on their design tiles facing another way or as "
           f"the other underground end, so their lines stop there ({shown}"
           f"{' ...' if len(bad) > 4 else ''}): the apply lays them fresh as designed (ordered "
           "out, robots take each up and build it again). A factory built over another keeps the "
           "old one's belts where the names match, facing the old ways")
    return Check("TURNED", ctx.surface.name, msg)


def _unreached(ctx, r, rep, batch=80):
    """An ``UNREACHED`` check for what the paste would lay where no powered roboport's
    construction area reaches, or None: robots never build it. 2.0.1 (the first lead run's
    plates worker): the coal site's power bridge ran through ground no powered roboport reached,
    and the relay roboport that would have reached it was powered only through that bridge: its
    poles stood as ghosts for ever. The world line says the same after the paste; this says it
    before."""
    from . import link
    lay = [v for v in rep.verdicts if v.verdict.split()[0] in _TO_LAY]
    if not lay:
        return None
    far = []
    try:
        for i in range(0, len(lay), batch):
            part = lay[i:i + batch]
            got = json.loads(r.lua(link.lua_unreached(ctx.surface.name, _force(ctx),
                                                      [(v.x, v.y) for v in part])).strip() or "[]")
            far += [part[int(k) - 1] for k in (got if isinstance(got, list) else [])]
    except (ValueError, OSError, link.LinkError):
        return None
    # a roboport the paste lays where robots reach covers its own area once built (its poles
    # come with it), and so on outward; one that stands without power covers nothing (the
    # deadlock), and the read above already left it out
    reach = []
    grew = True
    while grew and far:
        grew = False
        for v in [v for v in lay if v not in far and ctx.cat.kind(v.name) == "roboport"
                  and (v.x, v.y) not in {(x, y) for x, y, _r in reach}]:
            row = ctx.cat.entity(v.name) if ctx.cat.has_entity(v.name) else {}
            reach.append((v.x, v.y, float(row.get("construction_radius") or 0)))
            grew = True
        far = [v for v in far if not any(abs(v.x - x) <= d and abs(v.y - y) <= d
                                         for x, y, d in reach)]
    if not far:
        return None
    bridge = [v for v in far if (v.key or "").split(":", 1)[-1].startswith("bridge/")]
    shown = ", ".join(f"{v.name} {fkp.fmt(v.x)},{fkp.fmt(v.y)}" for v in far[:4])
    msg = (f"{len(far)} of the {len(lay)} entities the paste lays stand where no powered "
           f"roboport's construction area reaches ({shown}{' ...' if len(far) > 4 else ''}): "
           "robots never build them until a powered roboport reaches them")
    if bridge:
        msg += (f"; {len(bridge)} of them are power-bridge poles, and a roboport powered only "
                "through such a bridge never gets its power")
    return Check("UNREACHED", ctx.surface.name, msg)


def _force(ctx):
    from .apply import force_for
    return getattr(ctx.surface, "force", None) or force_for(ctx.surface.mode)


def s_apply(ctx, args):
    o = _opts(args, scope="all")
    if ctx.composed is None:
        return ["apply: no composed surface yet (floorplan first)"], []
    if ctx.composed.problems:
        return [f"apply: refused, the composed surface has {len(ctx.composed.problems)} invariant "
                "problems"], _invariant_checks(ctx.surface.name, ctx.composed.problems)
    r = _link(ctx)
    if r is None:
        return [f"apply: skipped, no game link ({ctx.link_error})"], []
    from . import apply as applymod
    area, keys = _scope(ctx, o)
    rep = applymod.apply(r, ctx.composed, ctx.cat, area, mode=ctx.surface.mode,
                         force=getattr(ctx.surface, "force", None), policy=ctx.surface,
                         keys=keys, net_items=_net_items(ctx),
                         label=f"fk build {os.path.basename(ctx.script)}",
                         seed=ctx.ground is None, own=ownmod.load(ctx.root, ctx.surface.name))
    if rep.own is not None:
        ownmod.save(ctx.root, ctx.surface.name, rep.own)
    checks = []
    if rep.hand:
        # 2.0: what this build replaced or removed that was placed by hand, for the player (the
        # Claude loop hands out/hand.txt's new lines to the lead the way it hands it chat)
        checks += [Check("HAND", ctx.surface.name, line) for line in rep.hand]
        _hand_file(ctx, rep.hand)
    if rep.misplaced:
        checks.append(Check("MISPLACED", ctx.surface.name, f"{rep.misplaced} ghosts are not where "
                                                           "the design says"))
    if rep.present < rep.design:
        checks.append(Check("UNPLACED", ctx.surface.name, f"{rep.design - rep.present} of "
                                                          f"{rep.design} designed entities are not "
                                                          "there as ghost or entity"))
    return rep.lines(), checks


def _hand_file(ctx, lines):
    """Append a build's hand edits to ``out/hand.txt`` (never rewritten: the loop reads what is
    new since its last look)."""
    import time
    with open(os.path.join(ctx.out, "hand.txt"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# {time.strftime('%Y-%m-%d %H:%M')} fk build ({os.path.basename(ctx.script)}): "
                 f"{len(lines)} hand edits this build replaced, removed or set back\n")
        fh.writelines(f"  {line}\n" for line in lines)


def s_stop_on(ctx, args):
    # the first lead run (2026-10-21): "stop_on: INVARIANT" as a full build's last line read as
    # the failure behind a nonzero exit, which came from the worker's own shell chain
    codes = ", ".join(sorted(ctx.stop_on))
    return [f"stop_on {codes}: a check of these stops the run; none has stopped it so far"], []


STEPS = {
    "read_surface": s_read_surface, "read_terrain": s_read_terrain, "run_models": s_run_models,
    "elaborate": s_elaborate, "size": s_size, "report_rates": s_report_rates, "place": s_place,
    "route": s_route, "tier": s_tier,
    "cover_power": s_cover_power, "cover_robots": s_cover_robots, "floorplan": s_floorplan,
    "report_checks": s_report_checks, "report_bom": s_report_bom, "write_layout": s_write_layout,
    "diff": s_diff, "apply": s_apply, "stop_on": s_stop_on,
}
_SOURCE = ("read_surface", "read_terrain", "run_models", "elaborate", "size", "stop_on")
_LAYOUT = ("place", "route", "tier", "cover_power", "cover_robots")


def _write_checkpoint(ctx, step, upto):
    """``out/<step>/``: each factory's layout as the step left it, and (2.0.4) ``source.json``:
    the source it was laid from (the files as the run began, and the script's lines ``upto``
    and including the step), so a later run that starts after it can tell it is stale."""
    folder = os.path.join(ctx.out, step)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, _STAMP_FILE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"line": upto[-1].n, "script": _script_sha(upto), "files": ctx.source}, fh,
                  indent=0, sort_keys=True)
        fh.write("\n")
    for factory, lay in ctx.layouts.items():
        with open(os.path.join(folder, f"{factory}.fkp"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(fkp.dumps(lay))
    if step == "floorplan" and ctx.surface_lay is not None:
        with open(os.path.join(folder, f"{ctx.surface.name}.fkp"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(fkp.dumps(ctx.surface_lay))


def _stale_checkpoint(ctx, step, upto):
    """Why ``out/<step>/`` was not laid from the source as it is now (the script's lines ``upto``
    and including the step, the source files as this run began): a list of reasons, [] when it
    was. A checkpoint with no ``source.json`` (an older toolkit's) is stale: nothing says what it
    was laid from."""
    try:
        with open(os.path.join(ctx.out, step, _STAMP_FILE), encoding="utf-8") as fh:
            stamp = json.load(fh)
        files, script, line = dict(stamp["files"]), stamp["script"], stamp["line"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["it does not say what source it was laid from"]
    why = _changed(files, ctx.source)
    if line != upto[-1].n or script != _script_sha(upto):
        why.append(f"{os.path.basename(ctx.script)} changed")
    return why


def _load_checkpoint(ctx, step):
    folder = os.path.join(ctx.out, step)
    for p in _factories(ctx):
        path = os.path.join(folder, f"{p.factory}.fkp")
        if not os.path.exists(path):
            raise FlowError(f"no checkpoint {path}: run the steps before it first")
        ctx.layouts[p.factory] = fkp.load(path)


def run(script, frm=None, to=None, cat=None, echo=print, link=None) -> tuple:
    """Run ``script`` (a .fkb path). -> (exit code, Ctx). 0 = ran to the end (or to ``to``), 1 =
    stopped by a stop_on check, 2 = malformed script or source. ``link``: an open game link the
    steps use instead of opening their own (``fkcore.lab``, 2.0.3), and the caller closes."""
    root = os.path.dirname(os.path.abspath(script))
    with open(script, encoding="utf-8") as fh:
        lines = parse(fh.read(), script)
    ctx = Ctx(root, script, cat or Catalog.load(), os.path.join(root, "out"))
    availmod.use(root)          # what the game can build, as the host last read it (out/avail.json)
    if link is not None:
        ctx.link, ctx.link_lent = link, True
    ctx.steps = [ln.cmd for ln in lines]
    for ln in lines:
        if ln.cmd == "stop_on":
            ctx.stop_on |= {a.upper() for a in ln.args}
    names = [ln.cmd for ln in lines]
    first = _at(names, frm) if frm else 0
    last = _at(names, to) if to else len(lines) - 1
    os.makedirs(ctx.out, exist_ok=True)
    # the source as the run begins, before any step reads it: a file edited while the run goes
    # on makes its checkpoints stale, never the other way round
    ctx.source = _source_files(root)
    for ln in lines[:first]:
        if ln.cmd in _SOURCE:
            STEPS[ln.cmd](ctx, ln.args)
    before = [k for k, ln in enumerate(lines[:first]) if ln.cmd in _LAYOUT]
    notes = []
    if before:
        k = before[-1]
        why = _stale_checkpoint(ctx, lines[k].cmd, lines[:k + 1])
        if not why:
            _load_checkpoint(ctx, lines[k].cmd)
        else:
            # 2.0.4 (the second lead run, 2026-10-22): a recipe changed in red.fk, the build
            # resumed on checkpoints laid from the old source, and the paste laid the old
            # recipe. A stale checkpoint is laid out again from the source, never taken
            notes.append(f"out/{lines[k].cmd} was laid from other source ({'; '.join(why)}): the "
                         f"layout steps before {lines[first].cmd} ran again on the source as it is")
            echo(notes[-1])
            for j, ln in enumerate(lines[:first]):
                if ln.cmd not in _LAYOUT and ln.cmd != "floorplan":
                    continue
                _report, checks = STEPS[ln.cmd](ctx, ln.args)
                ctx.checks += [(ln.cmd, c) for c in checks]
                _write_checkpoint(ctx, ln.cmd, lines[:j + 1])
                stops = [c for c in checks if c.code.upper() in ctx.stop_on]
                if stops:
                    echo(f"stopped at line {ln.n} ({ln.cmd}), laid out again: {len(stops)} "
                         f"{stops[0].code} line(s), first: {stops[0]}")
                    _close(ctx)
                    return 1, ctx
    plans = [k for k, ln in enumerate(lines[:first]) if ln.cmd == "floorplan"]
    if plans and ctx.layouts and not notes:
        STEPS["floorplan"](ctx, lines[plans[-1]].args)
    width = len(lines)
    written = set()
    for i in range(first, last + 1):
        ln = lines[i]
        report, checks = STEPS[ln.cmd](ctx, ln.args)
        report = report + availmod.drain()      # what inserter=any / --hand any / --pole any chose
        if i == first:
            report = report + notes
        ctx.checks += [(ln.cmd, c) for c in checks]
        text = [f"# {ln.text}   (line {ln.n} of {os.path.basename(script)})"] + report
        if checks:
            text += ["", "checks:"] + [f"  {c}" for c in checks]
        # a step the script runs again adds its report to the same file, after the first's
        with open(os.path.join(ctx.out, f"{ln.cmd}.txt"), "a" if ln.cmd in written else "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(("\n" if ln.cmd in written else "") + "\n".join(text) + "\n")
        written.add(ln.cmd)
        if ln.cmd in _LAYOUT or ln.cmd == "floorplan":
            _write_checkpoint(ctx, ln.cmd, lines[:i + 1])
        stops = [c for c in checks if c.code.upper() in ctx.stop_on]
        head = report[0] if report else ""
        summary = (f"[{i + 1:>2}/{width}] {ln.text:<44} {head[:70]}"
                   + (f"  ({len(checks)} check lines)" if checks else ""))
        ctx.log.append(summary)
        echo(summary)
        if stops:
            why = (f"stopped at line {ln.n} ({ln.cmd}): {len(stops)} {stops[0].code} "
                   f"line(s), first: {stops[0]}")
            echo(why)
            # the steps this run would have reached say so, instead of keeping an earlier run's
            # report (the first lead run's mall2 designer read stale report_checks and route
            # lines after a build stopped at elaborate, 2026-10-21)
            for later in lines[i + 1:last + 1]:
                if later.cmd in written:
                    continue
                with open(os.path.join(ctx.out, f"{later.cmd}.txt"), "w", encoding="utf-8",
                          newline="\n") as fh:
                    fh.write(f"# {later.text}   (line {later.n} of {os.path.basename(script)})\n"
                             f"not run: the build {why}\n")
                written.add(later.cmd)
            _close(ctx)
            return 1, ctx
    _close(ctx)
    return 0, ctx


def _at(names, spec):
    """The index of the step ``spec`` names: ``route``, or ``report_rates:2`` for the second
    report_rates of the script."""
    name, _, k = spec.partition(":")
    where = [i for i, n in enumerate(names) if n == name]
    try:
        k = int(k or 1)
        if k < 1:
            raise ValueError(k)
        return where[k - 1]
    except (ValueError, IndexError):
        raise FlowError(f"--from/--to must name a step of the script, NAME or NAME:K for its K-th "
                        f"time ({spec!r}): {', '.join(names)}") from None


def _close(ctx):
    if ctx.link is not None and not ctx.link_lent:
        ctx.link.close()
        ctx.link = None
