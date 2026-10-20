"""fkcore.expand: template instances -> the factory's .fkp (visible expansion), explain, unfold.

``expand_factory`` writes every placed instance's Fragment into one factory layout under the
instance's keys (``red/m0``, ``red/f0``, ``red/in1b3``): from then on they are data, not code. A
role is bound to the net its machines' endpoints sit on, which gives every carrier its ``net=``.
Placement in V1 is manual: an instance's ``@(x, y, rot r)`` hint is the top-left of its turned
frame, relative to its sub-module's own hint. Unplaced instances are listed, never guessed; the
routes between attach points are the router's (the next step), so a factory expanded here has its
template segments and none of the nets' own carriers yet.

``explain`` prints one instance both ways: the template line and the plain entities, nets and
attach points it stands for. ``unfold`` replaces the template line with ``Literal`` and keeps every
.fkp key and line, so the world does not change; the Literal's machines are read back from its
entities. Pure, stdlib only.
"""
from __future__ import annotations

import math
import re

from . import fkp as fkpmod
from .compose import turn
from .fragments import FEnt, Fragment, FragmentError, Role, _finish, fragment

__all__ = ["belts", "fragment_of", "expand_factory", "explain", "unfold", "attach_points",
           "frame_of"]

_SINGLE = ("Assembler", "Furnace", "ChemPlant", "Refinery", "Chest", "Pumpjack", "OffshorePump",
           "Boiler", "SteamEngine", "InfinityPipe")
_NO_DIRECTION = ("infinity-pipe",)          # fluid prototypes the game never turns


def belts(flat, key, side):
    """[(net, [items])] for machine ``key``: one entry per distinct net, recipe order first."""
    hold = flat._in_hold if side == "in" else flat._out_hold
    m = flat.machines[key]
    order = list(m.needs if side == "in" else m.makes)
    pairs = [(item, nets[0]) for (k, item), nets in hold.items() if k == key]
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
        if inst.kind == "SmelterRow":
            params["_recipe"] = m0.recipe
            fuel = [i for i in m0.needs if i not in cat.recipe_rates(m0.recipe, 1)[0]]
            params["_fuel"] = fuel[0] if fuel else None
        frag = fragment(inst.kind, params, [b[1] for b in ins], [b[1] for b in outs])
    binding = {}
    names_in = [r for r in frag.roles if frag.roles[r].side == "in"]
    names_out = [r for r in frag.roles if frag.roles[r].side == "out"]
    for name, (net, _items) in zip(names_in, ins):
        binding[name] = net
    for name, (net, _items) in zip(names_out, outs):
        binding[name] = net
    return frag, binding


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
    return attrs


def _param_text(v):
    if v is True:
        return "true"
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    if isinstance(v, float):
        return fkpmod.fmt(v)
    return str(v)


def _origin(flat, path):
    """Absolute (x, y, rot) of an instance: its hint plus every enclosing module's hint."""
    x = y = 0
    parts = path.split("/")
    for i in range(1, len(parts)):
        hint = flat.insts["/".join(parts[:i])].hints.get("at")
        if hint:
            x, y = x + hint[0], y + hint[1]
    hint = flat.insts[path].hints.get("at")
    if hint is None:
        return None
    return x + hint[0], y + hint[1], int(hint[2]) % 4


def expand_factory(flat, cat, previous=None):
    """-> (factory Layout, notes). ``previous`` supplies a Literal's pinned entities."""
    lay = fkpmod.Layout("factory", flat.name)
    notes = []
    xmax = ymax = 0
    for path, inst in flat.insts.items():
        if inst.module is not None:
            continue
        if inst.kind == "Literal" and inst.literal is not None:
            # imported from a file: placed by its hint like any fragment, keys from the import
            ents, size, _file_corner, sig = inst.literal
            hint = _origin(flat, path) or (0, 0, 0)
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
        at = _origin(flat, path)
        if at is None:
            notes.append(f"{path}: unplaced (no @(x, y) hint)")
            continue
        try:
            frag, binding = fragment_of(flat, path, cat)
        except FragmentError as exc:
            notes.append(str(exc) if str(exc).startswith(path) else f"{path}: {exc}")
            continue
        x0, y0, rot = at
        params = {k: _param_text(v) for k, v in inst.params.items()}
        lay.insts[path] = fkpmod.Inst(path, inst.kind, params, x0, y0, rot, frag.sig)
        for fe in frag.entities:
            x, y, d = turn(float(fe.x), float(fe.y), fe.dir, rot, frag.size)
            attrs = dict(fe.attrs)
            if fe.role is not None:
                net = binding.get(fe.role)
                if net is None:
                    notes.append(f"{path}/{fe.local}: role {fe.role} has no net (UNFED/UNCONSUMED)")
                    continue
                attrs["net"] = net
            e = fkpmod.Entity(f"{path}/{fe.local}", fe.name, _clean(x + x0), _clean(y + y0), d,
                              attrs)
            lay.add(e)
            xmax, ymax = _grow(cat, e, xmax, ymax)
    lay.size = (xmax, ymax)
    return lay, notes


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


def unfold(fk_text, flat, lay, path):
    """-> (new .fk text, new layout): ``path`` becomes a Literal; every .fkp line stays."""
    inst = flat.insts[path]
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
