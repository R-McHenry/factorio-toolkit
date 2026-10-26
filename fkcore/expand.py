"""fkcore.expand: template instances -> the factory's .fkp (visible expansion), explain, unfold.

``expand_factory`` writes every placed instance's Fragment into one factory layout under the
instance's keys (``red/m0``, ``red/f0``, ``red/in1b3``): from then on they are data, not code. A
role is bound to the net its machines' endpoints sit on, which gives every carrier its ``net=``.
Placement in V1 is manual: an instance's ``@(x, y, rot r)`` hint is the top-left of its turned
frame, relative to its sub-module's own hint; a sub-module instance's ``rot`` turns its whole
contents inside the module's frame, the way a plot turns a factory (``_origin``). A MinerRow with
``@patch(resource)`` and no ``@(x, y)`` is placed on its ore by ``fkcore.placer`` (given the
terrain in the factory frame, ``ground``), after every pinned instance, so it keeps clear of them.
Unplaced instances are listed, never guessed; the routes between attach points are the router's
(the next step), so a factory expanded here has its template segments and none of the nets' own
carriers yet.

Two nets that share a belt (``lanes A | B``, 2.0) are one input belt: a consumer on either of them
gets one role bound to the pair's ``A|B``, so its belt carries both lanes (and its inserters
``A+B``: each takes from both lanes what its machine accepts). A template's own belt of two nets is
a role written ``in1|in2``: its carriers carry the two roles' nets, in1's on the left lane
(``SmelterArray``'s feed belts, where the template side-loads ore and fuel).

``explain`` prints one instance both ways: the template line and the plain entities, nets and
attach points it stands for. ``unfold`` replaces the template line with ``Literal`` and keeps every
.fkp key and line, so the world does not change; the Literal's machines are read back from its
entities. Pure, stdlib only.
"""
from __future__ import annotations

import math
import re

from . import avail as availmod
from . import fkp as fkpmod
from . import placer
from .codec import config_text
from .compose import turn
from .fragments import FEnt, Fragment, FragmentError, Role, _finish, fragment
from .templates import CONTACT
from .terrain import fmt_amount

__all__ = ["belts", "fragment_of", "expand_factory", "explain", "unfold", "attach_points",
           "frame_of", "planned_frame"]

_SINGLE = ("Assembler", "Furnace", "ChemPlant", "Refinery", "Chest", "Pumpjack", "OffshorePump",
           "Boiler", "SteamEngine", "InfinityPipe", "Lab", "Reactor", "HeatExchanger",
           "SteamTurbine", "Constant", "Roboport")
_NO_DIRECTION = ("infinity-pipe",)          # fluid prototypes the game never turns
_H = {0: 0, 4: 1, 8: 2, 12: 3}
_DX = (0, 1, 0, -1)
_DY = (-1, 0, 1, 0)


def belts(flat, key, side):
    """[(net, [items])] for machine ``key``: one entry per distinct net, recipe order first. A
    net of contact items (2.0: heat, ``templates.CONTACT``) is left out: it has no route, so no
    role and no attach point. An input on a net that shares a belt (``lanes``) is on the pair's
    ``A|B``: one belt."""
    hold = flat._in_hold if side == "in" else flat._out_hold
    m = flat.machines[key]
    order = list(m.needs if side == "in" else m.makes)
    lane_of = getattr(flat, "lane_of", {}) if side == "in" else {}
    pairs = [(item, lane_of.get(nets[0], nets[0])) for (k, item), nets in hold.items()
             if k == key and item not in CONTACT]
    pairs.sort(key=lambda p: order.index(p[0]) if p[0] in order else len(order))
    out = []
    for item, net in pairs:
        for b in out:
            if b[0] == net:
                b[1].append(item)
                break
        else:
            out.append((net, [item]))
    return out


def fragment_of(flat, path, cat):
    """(Fragment, {role: net}) for template instance ``path``."""
    inst = flat.insts[path]
    if inst.kind == "Bus":
        return _bus_fragment(flat, path)
    keys = inst.machines
    ins, outs = belts(flat, keys[0], "in"), belts(flat, keys[0], "out")
    for k in keys[1:]:
        if belts(flat, k, "in") != ins or belts(flat, k, "out") != outs:
            raise FragmentError(f"{path}: its machines sit on different nets, so no single row "
                                "belt can serve them")
    m0 = flat.machines[keys[0]]
    if inst.kind in _SINGLE:
        frag = _single(flat, keys, cat, ins, outs)
    else:
        params = {k: v for k, v in inst.params.items() if k not in ("duty",)}
        if params.get("inserter") is not None:
            params["inserter"] = _hand_param(path, params["inserter"], cat)
        elif inst.kind != "SmelterArray":
            # 2.0.15 (Rory, 2026-10-25): a row laid without inserter= comes in on the lowest hand
            # the network can build, and the hands step raises the connectors the flow needs more
            # of. A SmelterArray keeps its own plain default (Rory's stack).
            params["inserter"] = availmod.choose("hand", "any", need=_row_hands(inst))[0]
        if inst.kind in ("SmelterRow", "SmelterArray"):
            params["_recipe"] = m0.recipe
            fuel = [i for i in m0.needs if i not in cat.recipe_rates(m0.recipe, 1)[0]]
            params["_fuel"] = fuel[0] if fuel else None
        if inst.kind == "SmelterArray":
            params["_per"] = _array_column(cat, m0)
        frag = fragment(inst.kind, params, [b[1] for b in ins], [b[1] for b in outs])
    binding = {}
    names_in = [r for r in frag.roles if frag.roles[r].side == "in"]
    names_out = [r for r in frag.roles if frag.roles[r].side == "out"]
    for name, (net, _items) in zip(names_in, ins):
        binding[name] = net
    for name, (net, _items) in zip(names_out, outs):
        binding[name] = net
    return frag, binding


def _row_hands(inst):
    """How many short hands a row instance lays, at least: one per machine, which is what the
    availability choice must be able to build (two for a two-handed row, but the row's machine count
    is the number that matters for stock)."""
    return max(len(inst.machines), 1)


def _hand_param(path, want, cat):
    """A row's ``inserter=``: the prototype it names, checked, or the one ``any`` picks now
    (``fkcore.avail``: the best hand the network can build, else the best it can make)."""
    got, _note = availmod.choose("hand", want)
    if not cat.has_entity(got):
        raise FragmentError(f"{path}: inserter={want}: no prototype {got!r} in the catalog")
    if cat.kind(got) != "inserter":
        raise FragmentError(f"{path}: inserter={want}: {got} is a {cat.kind(got)}, not an inserter "
                            "(inserter, fast-inserter, long-handed-inserter, bulk-inserter, ... "
                            "or any)")
    return str(got)


def _array_column(cat, m):
    """How many of machine ``m`` one SmelterArray column holds: as many as one yellow lane of
    their main ingredient feeds (24 stone furnaces on ore: 7.5/s at 0.3125 each, Rory's stack)."""
    from .lanes import lane_rate
    main = [r for i, r in m.needs.items() if i in cat.recipe_rates(m.recipe, 1)[0]]
    if not main or max(main) <= 0:
        return 24
    return max(1, int(lane_rate(cat, "transport-belt") / max(main) + 1e-9))


def _bus_fragment(flat, path):
    """A Bus: its ports' sides turned by its own rot (they are compass sides of the frame its
    hint is written in: the factory's, or its module's, which turns them with everything in it),
    a stub for each port a net names, bound to that net; its belts and splitters on its own net
    (``elaborate._bus_nets``)."""
    inst = flat.insts[path]
    item = inst.params.get("item")
    binding, used = {"pool": path}, set()
    for key in inst.machines:
        port = flat.machines[key].extra["port"]
        hold = flat._in_hold if port == "load" else flat._out_hold
        nets = [n for n in hold.get((key, item), ()) if n != path]
        if nets:
            local = key.rsplit("/", 1)[1]
            binding[local] = nets[0]
            used.add(local)
    params = {k: v for k, v in inst.params.items() if k != "duty"}
    params.update(_rot=int((inst.hints.get("at") or (0, 0, 0))[2]), _used=used,
                  _mouths=sorted(local for local in used if local.startswith("in")))
    return fragment("Bus", params, [], []), binding


def _rot_of(flat, path):
    """An instance's absolute rot: its own and every enclosing module's (0 where unplaced)."""
    parts = path.split("/")
    rot = 0
    for i in range(len(parts), 0, -1):
        hint = flat.insts["/".join(parts[:i])].hints.get("at")
        if hint is not None:
            rot += int(hint[2])
    return rot % 4


def _single(flat, keys, cat, ins, outs):
    m = flat.machines[keys[0]]
    w, h = cat.size(m.prototype)
    local = keys[0].rsplit("/", 1)[1]
    attrs = _machine_attrs(m)
    ents = [FEnt(local, m.prototype, w / 2, h / 2, _facing(m, cat), None, attrs)]
    roles = {}
    for i, (_net, items) in enumerate(ins):
        roles[f"in{i + 1}"] = Role(f"in{i + 1}", "in", items, [local], [(w / 2, h / 2, None)])
    for i, (_net, items) in enumerate(outs):
        name = "out" if i == 0 else f"out{i + 1}"
        roles[name] = Role(name, "out", items, [local], [(w / 2, h / 2, None)])
    return _finish(Fragment(flat.insts[keys[0].rsplit("/", 1)[0]].kind, {}, ents, roles, (w, h)))


def _facing(m, cat):
    """N for a machine on a fluid net (its pipe connections turn with it, so ``rot`` in the hint
    turns it); None, as before, for every other single machine."""
    fluid = any(cat.is_fluid(i) for i in list(m.needs) + list(m.makes))
    if fluid and cat.has_fluid_boxes(m.prototype) and m.prototype not in _NO_DIRECTION:
        return 0
    return None


def _machine_attrs(m):
    attrs = {}
    if m.recipe:
        attrs["recipe"] = m.recipe
    for k in ("resource", "role", "fuel", "fluid"):
        if k in m.extra:
            attrs[k] = m.extra[k]
    if m.drain is not None:
        attrs["rate"] = fkpmod.fmt(m.drain)
    if m.makes and not m.recipe and not m.source and "resource" not in m.extra:
        attrs["rate"] = fkpmod.fmt(next(iter(m.makes.values())))
    if m.source and "item" not in attrs:
        attrs["item"] = next(iter(m.makes))
    if m.takes is not None and m.sink and len(m.takes) == 1:
        attrs["item"] = next(iter(m.takes))
    fields = {}
    if m.extra.get("role") in _REQUESTS and m.makes:
        item = next(iter(m.makes))
        attrs["item"] = item
        fields.update(_request_fields(list(m.makes), m.extra.get("request"), m.makes[item],
                                      m.extra.get("max")))
        if m.extra.get("trash"):
            fields["request_filters"]["trash_not_requested"] = True
    if m.extra.get("limit") is not None:
        fields["bar"] = int(m.extra["limit"])    # the chest's inventory bar: its usable slots
    if fields:
        attrs["config"] = config_text(fields)
    return attrs


#: logistic chests that ask the network for their item: the request has to be in the paste, or
#: the chest asks for nothing (the V1 rehearsal's gear factory got no plates, 2026-10-20)
_REQUESTS = ("requester", "buffer")


def _request_fields(item, request, rate, most=None):
    """The game's ``request_filters`` for one item, or a list of them (``item="a,b"``): each at
    the same count, ``request=`` if given, else a minute of the chest's ``rate`` (at least 10),
    else 100; ``most`` (2.0, ``max=``) is each filter's upper bound, ``max_count``, which the
    count is clamped to (the game refuses a request with count > max_count)."""
    if request is not None:
        count = int(request)
    elif rate is not None and not math.isinf(rate):
        count = max(10, math.ceil(rate * 60))
    else:
        count = 100
    items = item if isinstance(item, list) else [item]
    top = {} if most is None else {"max_count": int(most)}
    if top:
        count = min(count, top["max_count"])
    return {"request_filters": {"sections": [{"index": 1, "filters": [
        dict({"index": k + 1, "name": it, "quality": "normal", "comparator": "=", "count": count},
             **top)
        for k, it in enumerate(items)]}]}}


def _request_config(item, request, rate):
    """``_request_fields`` as the ``config`` attr the codec writes."""
    return config_text(_request_fields(item, request, rate))


def _param_text(v):
    if v is True:
        return "true"
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    if isinstance(v, float):
        return fkpmod.fmt(v)
    return str(v)


def _origin(flat, path, cat=None, size=(0, 0), frames=None):
    """Absolute (x, y, rot) of an instance, None when it has no ``@(x, y)`` hint. ``size`` is
    its own frame (w, h), unturned.

    A module instance ``@(x, y, rot r)`` turns its whole contents r quarter turns clockwise inside
    its frame (``_module_frame``), the way a plot turns a factory: a child's turned frame lands
    where turning the module's frame puts it, then moves by (x, y), and the child's rot adds the
    module's. Under unturned modules only the hints add up, so ``size`` and ``cat`` (for the
    module frames; ``frames`` caches them) matter only under a turned one."""
    hint = flat.insts[path].hints.get("at")
    if hint is None:
        return None
    rot = int(hint[2]) % 4
    w, h = size if rot % 2 == 0 else size[::-1]
    box = (hint[0], hint[1], hint[0] + w, hint[1] + h)
    parts = path.split("/")
    for i in range(len(parts) - 1, 0, -1):            # the innermost module first
        mod = "/".join(parts[:i])
        mx, my, mr = flat.insts[mod].hints.get("at") or (0, 0, 0)
        mr = int(mr) % 4
        if mr:
            box = _turn_box(box, mr, _module_frame(flat, mod, cat, frames))
        box = (box[0] + mx, box[1] + my, box[2] + mx, box[3] + my)
        rot += mr
    return _clean(box[0]), _clean(box[1]), rot % 4


def _turn_box(box, rot, frame):
    """``box`` (x0, y0, x1, y1) inside ``frame`` (the same) turned ``rot`` quarter turns
    clockwise, the turned frame's top-left on the frame's own."""
    fx, fy = frame[0], frame[1]
    size = (frame[2] - fx, frame[3] - fy)
    ax, ay, _d = turn(box[0] - fx, box[1] - fy, None, rot, size)
    bx, by, _d = turn(box[2] - fx, box[3] - fy, None, rot, size)
    return min(ax, bx) + fx, min(ay, by) + fy, max(ax, bx) + fx, max(ay, by) + fy


def _module_frame(flat, path, cat, frames=None):
    """(x0, y0, x1, y1): module instance ``path``'s frame in its own coordinates, the box of its
    origin and every placed child's turned frame, or the frame the module declares with ``size
    WxH`` (2.0.28: a port list needs a frame before anything is placed). A child with no ``@(x, y)``
    hint (unplaced, or
    ``@patch``: placed in the factory frame), a pinned Literal (its entities stay where the
    .fkp has them) and one whose fragment fails (its note says why) are not in it."""
    if frames is not None and path in frames:
        return frames[path]
    if flat.insts[path].size is not None:      # a module that declares its frame (2.0.28: ports)
        w, h = flat.insts[path].size
        if frames is not None:
            frames[path] = (0, 0, w, h)
        return 0, 0, w, h
    x0 = y0 = x1 = y1 = 0
    for child in flat.scopes[path].values():
        hint = child.hints.get("at")
        own = None if hint is None else _own_frame(flat, child.path, cat, frames)
        if own is None:
            continue
        w, h = own[2] - own[0], own[3] - own[1]
        if int(hint[2]) % 2:
            w, h = h, w
        bx, by = hint[0] + own[0], hint[1] + own[1]
        x0, y0, x1, y1 = min(x0, bx), min(y0, by), max(x1, bx + w), max(y1, by + h)
    if frames is not None:
        frames[path] = (x0, y0, x1, y1)
    return x0, y0, x1, y1


def _own_frame(flat, path, cat, frames):
    """An instance's unturned frame (x0, y0, x1, y1) in its own coordinates, or None."""
    inst = flat.insts[path]
    if inst.module is not None:
        return _module_frame(flat, path, cat, frames)
    if inst.kind == "Literal":
        return None if inst.literal is None else (0, 0) + tuple(inst.literal[1])
    try:
        frag, _binding = fragment_of(flat, path, cat)
    except FragmentError:
        return None
    return (0, 0) + tuple(frag.size)


def expand_factory(flat, cat, previous=None, ground=None, log=None):
    """-> (factory Layout, notes). ``previous`` supplies a Literal's pinned entities. ``ground``
    (a ``terrain.FrameGround``: blocked tiles, ore and the plot, in the factory frame) places the
    ``@patch`` rows; ``log`` (a list) gets one line per row placed that way."""
    lay = fkpmod.Layout("factory", flat.name)
    notes = []
    xmax = ymax = 0
    on_patch = []
    frames = {}                                 # module path -> its frame, for turned modules
    for path, inst in flat.insts.items():
        if inst.module is not None:
            continue
        if inst.kind == "Literal" and inst.literal is not None:
            # imported from a file: placed by its hint like any fragment, keys from the import
            ents, size, _file_corner, sig = inst.literal
            hint = _origin(flat, path, cat, size, frames) or (0, 0, 0)
            x0, y0, rot = hint
            params = {k: _param_text(v) for k, v in inst.params.items()}
            lay.insts[path] = fkpmod.Inst(path, "Literal", params, x0, y0, rot, sig)
            for e in ents:
                x, y, d = turn(float(e.x), float(e.y), e.dir, rot, size)
                placed = fkpmod.Entity(e.key, e.name, _clean(x + x0), _clean(y + y0), d,
                                       dict(e.attrs))
                lay.add(placed)
                xmax, ymax = _grow(cat, placed, xmax, ymax)
            continue
        if inst.kind == "Literal":
            if previous is None or path not in previous.insts:
                notes.append(f"{path}: a Literal needs its entities from the previous .fkp")
                continue
            lay.insts[path] = previous.insts[path]
            for key, e in previous.entities.items():
                if e.owner == path:
                    lay.add(fkpmod.Entity(e.key, e.name, e.x, e.y, e.dir, dict(e.attrs)))
                    xmax, ymax = _grow(cat, e, xmax, ymax)
            continue
        if "at" not in inst.hints and "patch" in inst.hints:
            on_patch.append(path)
            continue
        if "at" not in inst.hints:
            notes.append(f"{path}: unplaced (no @(x, y) hint)")
            continue
        try:
            frag, binding = fragment_of(flat, path, cat)
        except FragmentError as exc:
            notes.append(str(exc) if str(exc).startswith(path) else f"{path}: {exc}")
            continue
        at = _origin(flat, path, cat, frag.size, frames)
        for e in _put(lay, path, inst, frag, binding, at, notes, cat):
            xmax, ymax = _grow(cat, e, xmax, ymax)
    for path in on_patch:
        at, line, frag, binding = _on_patch(flat, lay, path, cat, ground)
        if at is None:
            notes.append(line)
            continue
        if log is not None:
            log.append(line)
        for e in _put(lay, path, flat.insts[path], frag, binding, at, notes, cat):
            xmax, ymax = _grow(cat, e, xmax, ymax)
    lay.size = (xmax, ymax)
    return lay, notes


def role_net(binding, role):
    """The ``net=`` of a carrier that works ``role``: its net, or for a template's belt of two
    nets (``in1|in2``) both, in1's on the left lane; None when a role has none."""
    if "|" not in role:
        return binding.get(role)
    nets = [binding.get(r) for r in role.split("|")]
    return None if None in nets else fkpmod.pair_net(*nets)


def _put(lay, path, inst, frag, binding, at, notes, cat=None):
    """Write one placed fragment into ``lay`` under its keys; -> the entities added. A carrier
    without lanes (an inserter) on a belt of two nets carries both (``ore+fuel``)."""
    x0, y0, rot = at
    params = {k: _param_text(v) for k, v in inst.params.items()}
    lay.insts[path] = fkpmod.Inst(path, inst.kind, params, x0, y0, rot, frag.sig)
    added = []
    for fe in frag.entities:
        x, y, d = turn(float(fe.x), float(fe.y), fe.dir, rot, frag.size)
        attrs = dict(fe.attrs)
        if fe.role is not None:
            net = role_net(binding, fe.role)
            if net is None:
                notes.append(f"{path}/{fe.local}: role {fe.role} has no net (UNFED/UNCONSUMED)")
                continue
            if "|" in net and cat is not None and cat.has_entity(fe.name) \
                    and cat.kind(fe.name) not in fkpmod.LANE_TYPES:
                net = fkpmod.hand_net(net)
            attrs["net"] = net
        e = fkpmod.Entity(f"{path}/{fe.local}", fe.name, _clean(x + x0), _clean(y + y0), d, attrs)
        lay.add(e)
        added.append(e)
    return added


def _taken(flat, lay, cat):
    """Tiles a row placed now must keep clear of: every entity, every placed instance's frame
    and the tiles its routes start or end on."""
    taken = set()
    for e in lay.entities.values():
        taken |= fkpmod.tiles_of(cat, e)
    for path, rec in lay.insts.items():
        if rec.kind == "Literal" or path not in flat.insts:
            continue
        x0, y0, x1, y1 = frame_of(flat, lay, path, cat)
        taken |= {(x, y) for x in range(x0, x1) for y in range(y0, y1)}
        for _role, side, _net, (x, y, d) in attach_points(flat, lay, path, cat):
            if d is None:
                continue
            k, sign = _H[int(d)], (1 if side == "out" else -1)
            taken.add((math.floor(x) + sign * _DX[k], math.floor(y) + sign * _DY[k]))
    return taken


def _on_patch(flat, lay, path, cat, ground):
    """(at, report line, fragment, binding) for a ``@patch`` row; at is None when it can't be
    placed, and the line says why (and how many drills would fit: n is never changed)."""
    inst = flat.insts[path]
    res = inst.hints["patch"]
    if inst.kind != "MinerRow":
        return None, f"{path}: @patch places MinerRow rows only in V1; give it an @(x, y) hint", \
            None, None
    if inst.params.get("resource") != res:
        return None, (f"{path}: @patch({res}), but the row mines {inst.params.get('resource')}"), \
            None, None
    if ground is None:
        return None, (f"{path}: @patch({res}) needs the terrain (read_terrain <name>) and the "
                      "factory's plot"), None, None
    try:
        frag, binding = fragment_of(flat, path, cat)
    except FragmentError as exc:
        return None, f"{path}: {exc}", None, None
    n = int(inst.params["n"])
    ore = ground.ore.get(res, {})
    where = "the plot" + (f" (patch {ground.patch})" if ground.patch else "")
    if not ore:
        return None, f"{path}: @patch({res}): no {res} inside {where}", None, None
    taken = _taken(flat, lay, cat)
    spot = placer.place_on_patch(frag, cat, ore, ground.blocked, taken, ground.box)
    xs, ys = [t[0] for t in ore], [t[1] for t in ore]
    w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    span = f"the {res} in {where} spans {w}x{h}, long axis {'E-W' if w >= h else 'N-S'}"
    if spot is None:
        outs = [b[1] for b in belts(flat, inst.machines[0], "out")]

        def make(k):
            return fragment("MinerRow", dict(frag.params, n=k), [], outs)

        k, alt = placer.largest_fit(make, n, cat, ore, ground.blocked, taken, ground.box)
        line = (f"{path}: @patch({res}): no spot in {where} puts all {n} drills on {res} with "
                f"no row entity on blocked or taken ground ({span}); "
                + (f"n={k} would fit, at {alt.x},{alt.y} rot {alt.rot}; n stays {n}" if k
                   else "not even one drill fits"))
        return None, line, None, None
    line = (f"{path}: @patch({res}) at {spot.x},{spot.y} rot {spot.rot}, the row runs "
            f"{'E-W' if spot.rot % 2 == 0 else 'N-S'} ({span}): {spot.drills}/{n} drills on "
            f"{res}, {spot.under} ore tiles under them ({fmt_amount(spot.under_amount)}), "
            f"{spot.reach} in their mining areas ({fmt_amount(spot.reach_amount)})")
    return (spot.x, spot.y, spot.rot), line, frag, binding


def _grow(cat, e, xmax, ymax):
    for tx, ty in fkpmod.tiles_of(cat, e):
        xmax, ymax = max(xmax, tx + 1), max(ymax, ty + 1)
    return xmax, ymax


def _clean(v):
    return int(v) if float(v).is_integer() else v


def attach_points(flat, lay, path, cat):
    """[(role, side, net, (x, y, dir))] of a placed instance, in the factory frame."""
    rec = lay.insts[path]
    frag, binding = fragment_of(flat, path, cat)
    out = []
    for name, role in frag.roles.items():
        net = binding.get(name)
        for ax, ay, ad in role.attach:
            x, y, d = turn(float(ax), float(ay), ad, rec.rot, frag.size)
            out.append((name, role.side, net, (_clean(x + rec.x), _clean(y + rec.y), d)))
    return out


def planned_frame(flat, path, cat, frames=None):
    """(x0, y0, x1, y1): where instance ``path``'s turned frame lands in the factory frame by its
    ``@(x, y)`` hint, before anything is placed (the size step's FIT); None without a hint (an
    ``@patch`` row, an unplaced one), for a module or a pinned Literal, and when its fragment
    fails. ``frames`` caches the module frames, as for ``_origin``."""
    inst = flat.insts[path]
    if inst.module is not None or "at" not in inst.hints:
        return None
    own = _own_frame(flat, path, cat, frames)
    if own is None:
        return None
    size = (own[2] - own[0], own[3] - own[1])
    x0, y0, rot = _origin(flat, path, cat, size, frames)
    w, h = size if rot % 2 == 0 else size[::-1]
    return x0, y0, x0 + w, y0 + h


def frame_of(flat, lay, path, cat):
    """(x0, y0, x1, y1): the tiles of a placed instance's turned frame."""
    rec = lay.insts[path]
    frag, _binding = fragment_of(flat, path, cat)
    w, h = frag.size if rec.rot % 2 == 0 else frag.size[::-1]
    return (int(rec.x), int(rec.y), int(rec.x) + w, int(rec.y) + h)


def _span(keys):
    """'red/m0..m4' style summary of a key list."""
    if not keys:
        return "-"
    groups = {}
    for k in keys:
        owner, local = k.rsplit("/", 1)
        m = re.fullmatch(r"([a-z_]+\d*[a-z]+|[a-z]+)(\d+)", local)
        stem = m.group(1) if m else local
        groups.setdefault((owner, stem), []).append(local)
    out = []
    for (owner, stem), locs in groups.items():
        out.append(f"{owner}/{locs[0]}" + (f"..{locs[-1]}" if len(locs) > 1 else ""))
    return ", ".join(out)


def explain(flat, lay, path, cat) -> str:
    inst = flat.insts[path]
    rec = lay.insts.get(path)
    params = ", ".join(f"{k}={_param_text(v)}" for k, v in inst.params.items())
    head = f"{path} = {inst.kind}<{params}>"
    if rec is not None:
        head += f" at {fkpmod.fmt(rec.x)},{fkpmod.fmt(rec.y)} rot {rec.rot} sig {rec.sig}"
    if getattr(inst, "auto", None):
        head += f"   (n=auto {inst.auto[0]}..{inst.auto[1]}: the size step's count)"
    lines = [head]
    mine = sorted((k for k, e in lay.entities.items() if e.owner == path), key=fkpmod.natural_key)
    machines = [k for k in mine if lay.entities[k].net is None]
    protos = sorted({lay.entities[k].name for k in machines})
    recipes = sorted({lay.entities[k].attrs.get("recipe", "") for k in machines} - {""})
    lines.append(f"  machines  {_span(machines)}  ({len(machines)} x {', '.join(protos)}"
                 + (f", recipe {', '.join(recipes)}" if recipes else "") + ")")
    if inst.kind == "Literal" or rec is None:
        nets = sorted({lay.entities[k].net for k in mine if lay.entities[k].net})
        lines.append(f"  nets      {', '.join(nets) or '-'}")
        return "\n".join(lines)
    frag, binding = fragment_of(flat, path, cat)
    if inst.kind == "Bus":
        return "\n".join(lines[:1] + _explain_bus(flat, lay, path, frag, binding))
    for name, role in frag.roles.items():
        net = binding.get(name, "?")
        carriers = [k for k in mine if lay.entities[k].net == net
                    and k.rsplit("/", 1)[1] in {e.local for e in frag.entities if e.role == name}]
        (ax, ay, ad), = role.attach[:1] or [(0, 0, None)]
        x, y, d = turn(ax, ay, ad, rec.rot, frag.size)
        where = f"{fkpmod.fmt(x + rec.x)},{fkpmod.fmt(y + rec.y)}"
        if d is not None:
            where += " " + fkpmod.DIRS[d]
        lines.append(f"  {role.side:<4} {name:<4} net {net:<14} items {', '.join(role.items):<30} "
                     f"attach {where:<11} carriers {_span(carriers)}")
    lines.append(f"  size      {frag.size[0]}x{frag.size[1]} (its own frame)")
    return "\n".join(lines)


def _explain_bus(flat, lay, path, frag, binding):
    """A Bus's lines for ``explain``: its own net, then each port: its side and tile as written,
    its net, where the router meets it (the stub's tile and the way items cross it) and its
    staircase."""
    inst, rec = flat.insts[path], lay.insts[path]
    item = inst.params.get("item")
    mine = [k for k, e in lay.entities.items() if e.owner == path]
    belts = sum(1 for k in mine if lay.entities[k].name.endswith("transport-belt")
                and k.rsplit("/", 1)[1].startswith("b"))
    splitters = sum(1 for k in mine if lay.entities[k].name.endswith("splitter"))
    w, h = frag.size
    runs = ("east", "south", "west", "north")[_rot_of(flat, path)]
    out = [f"  bus       {item} on {h - 2} belts, {w} tiles, running {runs}: net {path} "
           f"(its own: {belts} belts, {splitters} splitters)"]
    for key in inst.machines:
        m = flat.machines[key]
        local = key.rsplit("/", 1)[1]
        side = "in" if m.extra["port"] == "load" else "out"
        stair = [k for k in mine if k.rsplit("/", 1)[1].startswith(local + "s")]
        role = frag.roles.get(local)
        if role is None:
            out.append(f"  {side:<4} {local:<5} {m.extra['at']:<4} no net names it: its staircase "
                       f"{_span(sorted(stair, key=fkpmod.natural_key))} only")
            continue
        (ax, ay, ad), = role.attach
        x, y, d = turn(ax, ay, ad, rec.rot, frag.size)
        where = f"{fkpmod.fmt(x + rec.x)},{fkpmod.fmt(y + rec.y)} {fkpmod.DIRS[d]}"
        out.append(f"  {side:<4} {local:<5} {m.extra['at']:<4} net {binding[local]:<14} attach "
                   f"{where:<11} carriers {path}/{local}, staircase "
                   f"{_span(sorted(stair, key=fkpmod.natural_key))}")
    out.append(f"  size      {w}x{h} (its own frame: the belts are its rows 1..{h - 2}, the ports "
               "come in and go out at rows 0 and " + str(h - 1) + ")")
    return out


def unfold(fk_text, flat, lay, path):
    """-> (new .fk text, new layout): ``path`` becomes a Literal; every .fkp line stays."""
    inst = flat.insts[path]
    if inst.kind == "Bus":
        raise ValueError(f"{path} is a Bus: its ports are what nets name, and a Literal has none")
    if "/" in path:
        raise ValueError(f"{path} is inside a sub-module; unfold the module's instance instead")
    lines = fk_text.split("\n")
    i = inst.line - 1
    m = re.match(rf"^(\s*{re.escape(path)}\s*=\s*){re.escape(inst.kind)}(<[^>]*>)?(.*)$", lines[i])
    if not m:
        raise ValueError(f"line {inst.line} is not the instance line of {path}")
    was = inst.kind + (m.group(2) or "")
    duty = inst.params.get("duty")
    kept = f"<duty={_param_text(duty)}>" if duty is not None else ""
    rest = m.group(3)
    lines[i] = f"{m.group(1)}Literal{kept}{rest}   # unfolded from {was}: pinned in the .fkp"
    new = fkpmod.Layout(lay.level, lay.name, lay.size, dict(lay.insts), dict(lay.covers),
                        dict(lay.plots), dict(lay.claims), dict(lay.marks), dict(lay.entities))
    rec = lay.insts[path]
    params = {"from": inst.kind}
    params.update(rec.params)
    new.insts[path] = fkpmod.Inst(rec.path, "Literal", params, rec.x, rec.y, rec.rot, rec.sig)
    return "\n".join(lines), new
