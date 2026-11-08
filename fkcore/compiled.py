"""Sealed modules compile once (3.0, PLAN-3.0 §4, phase 5): the routed inside of a sealed module,
stored in the design database and laid again wherever the module stands.

A sealed instance's inner nets route only inside its frame (``route.net_frames``), so what they lay
depends on nothing outside it: the same inside routes the same wherever the frame is put. The
route step stores each sealed instance's inner routes, once every inner net of it routed, under
``out/design/modules/<module>/<key>.fkp``, in the frame's own tiles (its top-left is 0,0).
``key`` (``inside_key``) is a sha over what the routes are laid to, relative to the frame: every
entity the layout places inside it (machines, a row's belts, a Literal's entities: name, tile,
direction, settings), every inner net (its items, drivers and consumers) and every port of it,
the frame's turn and size, and ``ROUTER``. The module's source and its parameters change the key
through what they elaborate to; an edit that elaborates the same keeps it.

The next route step (``route --only stale``, the build's) takes a stored inside for every sealed
instance whose key it finds, translated to where the instance stands now (``reuse``), as the
committed routes of its inner nets: each stands as it is, or the router patches it, as for any
committed route. A world build sees the inner nets of its compiled modules as kept, and searches
only the nets that cross frames. A module moved is laid where it went with nothing searched.

``fk compile MODULE`` routes one module's instances alone (their inner nets only) and stores
them; ``route --reuse-lab`` also reads the stores the lab's builds left (``fk lab MODULE``:
``<run>/lab/<name>/out``), the cheap way to bring a module the lab already routed into the
world. Pure, stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from . import fkp

__all__ = ["ROUTER", "inside_key", "store_path", "save", "load", "reuse", "sealed_roots",
           "inner_nets"]

#: the router generation a stored inside was laid by: a change to what the router lays for the
#: same inside raises it, and every stored inside is laid again once
ROUTER = "3.0.2"
_HERE = "@"


def store_dir(out):
    return os.path.join(out, "design", "modules")


def store_path(out, module, key):
    return os.path.join(store_dir(out), module, f"{key}.fkp")


def _rel(text, path):
    """``path``'s own names in ``text`` (keys, nets, lane pairs ``a|b``) relative: ``@/...``."""
    return re.sub(rf"(?<![\w/@-]){re.escape(path)}/", f"{_HERE}/", str(text))


def _abs(text, path):
    return re.sub(rf"(?<![\w/@-]){re.escape(_HERE)}/", f"{path}/", str(text))


def inner_nets(flat, path):
    """The nets inside instance ``path`` (``path/...``), sorted."""
    return sorted(n for n in flat.nets if n.startswith(path + "/"))


def sealed_roots(flat, lay):
    """The sealed instances placed in ``lay`` that no other sealed instance holds: what a stored
    inside covers (a sealed child's nets are its parent's inner nets too)."""
    sealed = sorted(p for p in getattr(flat, "sealed", ()) if p in lay.insts)
    return [p for p in sealed if not any(p.startswith(q + "/") for q in sealed if q != p)]


def inside_key(flat, lay, cat, path):
    """The sha (16 hex) of what instance ``path``'s inner routes are laid to, relative to its
    frame, and ``ROUTER``. None when it is not placed."""
    from .expand import frame_of
    rec = lay.insts.get(path)
    if rec is None:
        return None
    x0, y0, x1, y1 = frame_of(flat, lay, path, cat)
    ents = []
    for e in lay.entities.values():
        if e.key.startswith(path + "/") and not e.key.startswith("~"):
            attrs = sorted((k, _rel(v, path)) for k, v in e.attrs.items())
            ents.append((_rel(e.key, path), e.name, float(e.x) - x0, float(e.y) - y0, e.dir,
                         attrs))
    nets = []
    for n in inner_nets(flat, path):
        net = flat.nets[n]
        nets.append((_rel(n, path), sorted(map(str, net.items or ())),
                     sorted(_rel(k, path) + "|" + str(i) for k, i in net.drivers),
                     sorted(_rel(k, path) + "|" + str(i) for k, i in net.consumers)))
    ports = sorted((_rel(k, path), str(getattr(p, "dir", "")), sorted(map(str, p.items or ())))
                   for k, p in getattr(flat, "ports", {}).items() if k.startswith(path + "/"))
    blob = json.dumps([ROUTER, int(rec.rot) % 4, x1 - x0, y1 - y0, sorted(ents), nets, ports],
                      sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def _module(flat, path):
    inst = flat.insts[path]
    return re.sub(r"[^A-Za-z0-9_.-]", "_", inst.module or inst.kind)


def save(out, flat, lay, cat, path, routed, key=None):
    """Store instance ``path``'s inner routes from ``routed`` (the layout after the route step),
    in its frame's tiles. -> the file written, or None when an inner net has no carriers in it
    (unrouted: nothing complete to keep) or the instance has no inner nets."""
    from .expand import frame_of
    key = key or inside_key(flat, lay, cat, path)
    nets = inner_nets(flat, path)
    if key is None or not nets:
        return None
    x0, y0, _x1, _y1 = frame_of(flat, lay, path, cat)
    by_net = {}
    for e in routed.entities.values():
        if e.owner.startswith("~") and fkp.net_names(e.owner[1:]) and \
                all(n.startswith(path + "/") for n in fkp.net_names(e.owner[1:])):
            by_net.setdefault(e.owner[1:], []).append(e)
    if not by_net:
        return None
    lines = [f"# module: {flat.insts[path].module or flat.insts[path].kind}",
             f"# key: {key}", f"# router: {ROUTER}", f"# from: {path}",
             f"# nets: {len(by_net)}", f"fkp 1 factory {_HERE}"]
    for net in sorted(by_net, key=fkp.natural_key):
        for e in sorted(by_net[net], key=lambda e: fkp.natural_key(e.key)):
            attrs = {k: _rel(v, path) for k, v in e.attrs.items()}
            rel = fkp.Entity(_rel(e.key, path), e.name, _clean(float(e.x) - x0),
                             _clean(float(e.y) - y0), e.dir, attrs)
            lines.append(fkp.entity_line(rel))
    target = store_path(out, _module(flat, path), key)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, target)
    return target


def load(dirs, module, key):
    """The stored entities of ``module`` under ``key`` from the first store in ``dirs`` that has
    it (each an ``out`` folder), in frame tiles, keys relative; None when none has it."""
    for out in dirs:
        p = store_path(out, module, key)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                lay = fkp.loads(fh.read(), p)
            return list(lay.entities.values())
    return None


def reuse(dirs, flat, lay, cat, skip=(), locked=None):
    """{net: carriers} of every sealed instance of ``lay`` whose inside a store in ``dirs`` holds,
    translated to its frame now; ``skip``: nets left out (held, pinned, asked for again);
    ``locked(name)``: True for an entity the force can't build yet, and a stored inside holding
    one is not reused (the router lays it again with what the force has). ->
    ({net: [Entity]}, {instance: (module, key, how many nets)}, {instance: (module, [names])})."""
    from .expand import frame_of
    nets, used, refused = {}, {}, {}
    for path in sealed_roots(flat, lay):
        key = inside_key(flat, lay, cat, path)
        got = load(dirs, _module(flat, path), key) if key else None
        if not got:
            continue
        bad = sorted({e.name for e in got if locked and locked(e.name)})
        if bad:
            refused[path] = (_module(flat, path), bad)
            continue
        x0, y0, _x1, _y1 = frame_of(flat, lay, path, cat)
        mine = {}
        for e in got:
            attrs = {k: _abs(v, path) for k, v in e.attrs.items()}
            ent = fkp.Entity(_abs(e.key, path), e.name, _clean(float(e.x) + x0),
                             _clean(float(e.y) + y0), e.dir, attrs)
            mine.setdefault(ent.owner[1:], []).append(ent)
        mine = {n: ents for n, ents in mine.items() if n not in skip}
        nets.update(mine)
        used[path] = (_module(flat, path), key, len(mine))
    return nets, used, refused


def _clean(v):
    return int(v) if float(v).is_integer() else v
