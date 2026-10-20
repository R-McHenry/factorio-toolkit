"""fkcore.flow: the build script (``<surface>.build.fkb``), run as a Vivado-style flow (CORE-V1 §7).

One contained tool per line, straight-line, no control flow. Every step reads the state the steps
before it left and writes a report, ``out/<step>.txt``. A step that changes a layout also writes a
checkpoint, ``out/<step>/<factory>.fkp`` (and ``<surface>.fkp`` once there is a floorplan).
``stop_on <check ...>`` lines (anywhere in the script) name the check codes that stop the run;
``invariant`` is always among them, because malformed data can't be written. Everything else is a
report line, never a gate.

``run(script, frm=None, to=None)`` runs the whole script or the lines from ``frm`` to ``to``.
Steps before ``frm`` that only read source (``read_surface``, ``read_terrain``, ``run_models``,
``elaborate``) are re-run quietly: source is cheap and pure. Layouts come from the checkpoint of
the last layout step before ``frm``, and a ``floorplan`` before ``frm`` is replayed on them (it is
pure too), so ``--from diff`` on the game host applies what a laptop build laid out.

Steps: read_surface, read_terrain, run_models, elaborate, report_rates, place, route,
cover power, cover robots, floorplan, report_checks, report_bom, write_layout, diff, apply,
stop_on. ``diff`` and ``apply`` use the game link (``fkcore.link``: RCON, 5 s per call; the
surface file's name is the game surface, its mode picks the force and the rules, see
``fkcore.apply``). The link is used only when ``FK_LINK=on`` is set (so a paper game run on the
game host never pastes by accident); without it, or with no RCON password file or nothing
listening, they report that they were skipped. Apart from those two steps it is pure: it reads
the game codebase and writes ``out/`` and, in write_layout, the ``.fkp`` files.
"""
from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field

from . import compose, connect, expand, fkp, rates, route
from . import surface as surfacemod
from .catalog import Catalog
from .elaborate import Check, ElabError, elaborate_file
from .lang import FkSyntaxError

__all__ = ["FlowError", "Ctx", "Line", "parse", "run", "STEPS"]


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
    stop_on: set = field(default_factory=lambda: {"INVARIANT"})
    log: list = field(default_factory=list)          # one summary line per step run
    checks: list = field(default_factory=list)       # [(step, Check)] of every step run so far
    link: object = None                              # the game link (fkcore.link.Rcon), on use
    link_error: str | None = None


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
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    ctx.terrain = {tuple(t) for t in data.get("blocked", ())}
    return [f"terrain {name}: {len(ctx.terrain)} blocked tiles"], []


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
        lines.append(f"{p.factory}: {len(flat.insts)} instances, {len(flat.machines)} machines, "
                     f"{len(flat.nets)} nets ({sushi} sushi), {len(flat.checks)} check lines")
        checks += [Check(c.code, f"{p.factory} {c.where}", c.msg, c.line) for c in flat.checks]
    return lines, checks


def s_report_rates(ctx, args):
    lines, checks, made = [], [], {}
    for factory, flat in ctx.flats.items():
        model = rates.solve(flat)
        lines += rates.report(model, factory).splitlines() + [""]
        for text, ok, value, target, op in model.asserts:
            if not ok:
                checks.append(Check("ASSERT", factory, f"{text}: {value * 60:.3f}/min"))
        for key, m in flat.machines.items():
            for item, r in m.makes.items():
                made[item] = made.get(item, 0.0) + r * model.util[key]
    if ctx.surface is not None:
        for item, want in ctx.surface.targets.items():
            got = made.get(item, 0.0)
            ok = got >= want - 1e-9
            lines.append(f"target {item} {want * 60:g}/min: {'met' if ok else 'NOT met'}, "
                         f"{got * 60:.3f}/min nominal")
            if not ok:
                checks.append(Check("TARGET", item, f"{got * 60:.3f}/min nominal, target "
                                                    f"{want * 60:g}/min"))
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


_OWN_POLE = re.compile(r"[pr]\d+")          # a cover's own: poles p<k>, roboports r<k>


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
        lay, notes = expand.expand_factory(flat, ctx.cat, ctx.previous.get(p.factory))
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
        checks += [Check("UNPLACED", p.factory, n) for n in notes]
        checks += _invariant_checks(p.factory, fkp.invariants(lay, ctx.cat))
    return lines, checks


def _pinned_routes(flat, new, prev, cat):
    """Carry over the committed routes of nets whose ends did not move (route --only stale)."""
    if prev is None:
        return new, []
    old_ends = {n: j.ends() for n, j in route.jobs(flat, prev, cat).items()} if prev.insts else {}
    now = route.jobs(flat, new, cat)
    taken = set()
    for e in new.entities.values():
        taken |= fkp.tiles_of(cat, e)
    kept = []
    by_net = {}
    for e in prev.entities.values():
        if e.owner.startswith("~"):
            by_net.setdefault(e.owner[1:], []).append(e)
    for net, ents in sorted(by_net.items()):
        if net not in now or old_ends.get(net) != now[net].ends():
            continue
        tiles = set()
        for e in ents:
            tiles |= fkp.tiles_of(cat, e)
        if tiles & taken:
            continue
        taken |= tiles
        for e in ents:
            new.add(fkp.Entity(e.key, e.name, e.x, e.y, e.dir, dict(e.attrs)))
        kept.append(net)
    return new, kept


def s_route(ctx, args):
    o = _opts(args, only="all", effort="normal")
    limit, retries = (400000, None) if o["effort"] == "high" else (60000, None)
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        flat = ctx.flats[factory]
        pinned = []
        if o["only"] == "stale":
            lay, pinned = _pinned_routes(flat, lay, ctx.previous.get(factory), ctx.cat)
        r = route.route_layout(flat, lay, ctx.cat, limit=limit, retries=retries)
        ctx.layouts[factory] = r.layout
        lines.append(f"{factory}: {len(r.routed)} routed, {len(r.kept)} kept "
                     f"({len(pinned)} pinned from the committed .fkp), {len(r.failed)} failed, "
                     f"{r.passes} pass{'es' if r.passes != 1 else ''}")
        lines += [f"  {l}" for l in r.lines]
        checks += [Check("UNROUTED", f"{factory} net {n}", why) for n, why in r.failed.items()]
        checks += [Check("UNROUTED", f"{factory} net {l.split(':')[0].split()[-1]}",
                         l.split(": ", 1)[1]) for l in r.lines if l.startswith("skipped")]
        checks += _invariant_checks(factory, fkp.invariants(r.layout, ctx.cat, nets=flat.nets))
    return lines, checks


def s_cover_power(ctx, args):
    o = _opts(args, pole="medium-electric-pole")
    try:
        from . import cover
    except ImportError:
        return ["cover power: fkcore.cover is not built yet; nothing placed"], [
            Check("NO_POWER", "all factories", "no power coverage step yet")]
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        _poles, rep = cover.cover_power(lay, ctx.cat, pole=o["pole"])
        new = cover.apply_cover(lay, ctx.cat, pole=o["pole"])
        ctx.layouts[factory] = new
        lines.append(f"{factory}: {rep.summary()}")
        checks += [Check(c.code, f"{factory} {c.where}", c.msg) for c in rep.checks]
        checks += _invariant_checks(factory, fkp.invariants(new, ctx.cat))
    return lines, checks


def s_cover_robots(ctx, args):
    """Roboports so every logistic chest of a factory is in a logistic area (``fkcore.robots``);
    before ``cover power`` in the script, so the poles power them."""
    from . import robots
    o = _opts(args, roboport="roboport")
    lines, checks = [], []
    for factory, lay in list(ctx.layouts.items()):
        new, rep = robots.apply_robots(lay, ctx.cat, roboport=o["roboport"])
        ctx.layouts[factory] = new
        lines.append(f"{factory}: {rep.summary()}")
        checks += [Check(c.code, f"{factory} {c.where}", c.msg) for c in rep.checks]
        checks += _invariant_checks(factory, fkp.invariants(new, ctx.cat))
    return lines, checks


def s_floorplan(ctx, args):
    sf = ctx.surface
    infra_path = os.path.join(ctx.root, f"{sf.name}.fkp")
    infra = None
    if os.path.exists(infra_path):
        prev = fkp.load(infra_path)
        infra = fkp.Layout("surface", sf.name, covers=prev.covers, marks=prev.marks,
                           entities=prev.entities)
    ctx.surface_lay = surfacemod.floorplan(sf, infra)
    ctx.composed = compose.compose(ctx.surface_lay, ctx.layouts, ctx.cat)
    o = _opts(args)
    lines, checks = [], []
    if o.get("bridge_power"):
        from . import cover
        pole = o["bridge_power"] if isinstance(o["bridge_power"], str) else "medium-electric-pole"
        s = ctx.composed
        keep = set()
        for p in s.plots.values():
            keep |= {(x, y) for x in range(p.x, p.x + p.w) for y in range(p.y, p.y + p.h)}
        for c in s.claims.values():
            keep |= {(x, y) for x in range(c.x0, c.x1) for y in range(c.y0, c.y1)}
        for m in s.marks.values():
            keep |= {(int(x), int(y)) for x, y in m.tiles}
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


def s_report_checks(ctx, args):
    """Connectivity of every net and the invariants, now; then every check line of the run."""
    lines, checks = [], []
    for factory, lay in ctx.layouts.items():
        flat = ctx.flats[factory]
        rep = connect.connect(lay, ctx.cat, connect.endpoints(flat))
        lines.append(f"{factory}: {rep.summary()}")
        checks += [Check(c.code, f"{factory} {c.where}", c.msg) for c in rep.checks]
        checks += _invariant_checks(factory, fkp.invariants(lay, ctx.cat, nets=flat.nets))
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


def s_report_bom(ctx, args):
    o = _opts(args, stock="none")
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
    return lines, checks


def _link(ctx):
    """The game link, opened on first use; None (``ctx.link_error`` says why) without one."""
    if ctx.link is None and ctx.link_error is None:
        if os.environ.get("FK_LINK", "off").lower() != "on":
            ctx.link_error = "FK_LINK is not on (FK_LINK=on uses the game link)"
        else:
            from . import link
            try:
                ctx.link = link.Rcon()
            except (OSError, link.LinkError) as exc:
                ctx.link_error = f"{type(exc).__name__}: {exc}"
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
    if area is None:
        area = applymod.scope_area(applymod.scope_rows(ctx.composed, None, keys), ctx.cat)
    if area is None:
        return ["diff: nothing is designed on this surface"], []
    rep = applymod.diff(r, ctx.composed, ctx.cat, area, ctx.surface, _net_items(ctx))
    checks = [Check("DIFF", ctx.surface.name, f"{k} {n}") for k, n in sorted(rep.counts().items())
              if k != "OK"]
    return rep.lines(), checks


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
                         label=f"fk build {os.path.basename(ctx.script)}")
    checks = []
    if rep.misplaced:
        checks.append(Check("MISPLACED", ctx.surface.name, f"{rep.misplaced} ghosts are not where "
                                                           "the design says"))
    if rep.present < rep.design:
        checks.append(Check("UNPLACED", ctx.surface.name, f"{rep.design - rep.present} of "
                                                          f"{rep.design} designed entities are not "
                                                          "there as ghost or entity"))
    return rep.lines(), checks


def s_stop_on(ctx, args):
    return [f"stop_on: {', '.join(sorted(ctx.stop_on))}"], []


STEPS = {
    "read_surface": s_read_surface, "read_terrain": s_read_terrain, "run_models": s_run_models,
    "elaborate": s_elaborate, "report_rates": s_report_rates, "place": s_place, "route": s_route,
    "cover_power": s_cover_power, "cover_robots": s_cover_robots, "floorplan": s_floorplan,
    "report_checks": s_report_checks, "report_bom": s_report_bom, "write_layout": s_write_layout,
    "diff": s_diff, "apply": s_apply, "stop_on": s_stop_on,
}
_SOURCE = ("read_surface", "read_terrain", "run_models", "elaborate", "stop_on")
_LAYOUT = ("place", "route", "cover_power", "cover_robots")


def _write_checkpoint(ctx, step):
    folder = os.path.join(ctx.out, step)
    os.makedirs(folder, exist_ok=True)
    for factory, lay in ctx.layouts.items():
        with open(os.path.join(folder, f"{factory}.fkp"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(fkp.dumps(lay))
    if step == "floorplan" and ctx.surface_lay is not None:
        with open(os.path.join(folder, f"{ctx.surface.name}.fkp"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(fkp.dumps(ctx.surface_lay))


def _load_checkpoint(ctx, step):
    folder = os.path.join(ctx.out, step)
    for p in _factories(ctx):
        path = os.path.join(folder, f"{p.factory}.fkp")
        if not os.path.exists(path):
            raise FlowError(f"no checkpoint {path}: run the steps before it first")
        ctx.layouts[p.factory] = fkp.load(path)


def run(script, frm=None, to=None, cat=None, echo=print) -> tuple:
    """Run ``script`` (a .fkb path). -> (exit code, Ctx). 0 = ran to the end (or to ``to``), 1 =
    stopped by a stop_on check, 2 = malformed script or source."""
    root = os.path.dirname(os.path.abspath(script))
    with open(script, encoding="utf-8") as fh:
        lines = parse(fh.read(), script)
    ctx = Ctx(root, script, cat or Catalog.load(), os.path.join(root, "out"))
    for ln in lines:
        if ln.cmd == "stop_on":
            ctx.stop_on |= {a.upper() for a in ln.args}
    names = [ln.cmd for ln in lines]
    if frm and frm not in names or to and to not in names:
        raise FlowError(f"--from/--to must name a step of the script: {', '.join(names)}")
    first = names.index(frm) if frm else 0
    last = names.index(to) if to else len(lines) - 1
    os.makedirs(ctx.out, exist_ok=True)
    for ln in lines[:first]:
        if ln.cmd in _SOURCE:
            STEPS[ln.cmd](ctx, ln.args)
    before = [ln.cmd for ln in lines[:first] if ln.cmd in _LAYOUT]
    if before:
        _load_checkpoint(ctx, before[-1])
    plans = [ln for ln in lines[:first] if ln.cmd == "floorplan"]
    if plans and ctx.layouts:
        STEPS["floorplan"](ctx, plans[-1].args)
    width = len(lines)
    for i in range(first, last + 1):
        ln = lines[i]
        report, checks = STEPS[ln.cmd](ctx, ln.args)
        ctx.checks += [(ln.cmd, c) for c in checks]
        text = [f"# {ln.text}   (line {ln.n} of {os.path.basename(script)})"] + report
        if checks:
            text += ["", "checks:"] + [f"  {c}" for c in checks]
        with open(os.path.join(ctx.out, f"{ln.cmd}.txt"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("\n".join(text) + "\n")
        if ln.cmd in _LAYOUT or ln.cmd == "floorplan":
            _write_checkpoint(ctx, ln.cmd)
        stops = [c for c in checks if c.code.upper() in ctx.stop_on]
        head = report[0] if report else ""
        summary = (f"[{i + 1:>2}/{width}] {ln.text:<44} {head[:70]}"
                   + (f"  ({len(checks)} check lines)" if checks else ""))
        ctx.log.append(summary)
        echo(summary)
        if stops:
            echo(f"stopped at line {ln.n} ({ln.cmd}): {len(stops)} {stops[0].code} "
                 f"line(s), first: {stops[0]}")
            _close(ctx)
            return 1, ctx
    _close(ctx)
    return 0, ctx


def _close(ctx):
    if ctx.link is not None:
        ctx.link.close()
        ctx.link = None
