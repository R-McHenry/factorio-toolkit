"""fkcore.hull: the achieved hull and the assigned frame of a sealed module (PLAN-ORGANIC H5,
43-hull).

A sealed module's frame has three sources, each refining the last (PLAN-ORGANIC "A frame has three
sources"): the **declaration** on its module line (``size WxH`` or ``shape (x,y) ...``), the
**territory** the world placer assigned its instance (``out/territories.json``, part T: one cell of
row runs per instance, in the scope's frame, with the corner the instance was placed at), and the
**achieved hull**: what the module actually covers once it has been laid out and routed alone as a
compile unit (its entities and carriers, closed under the 1-tile neighbourhood, grown by its
``gap``, clipped to the frame it was built in). The hull is recorded here, in ``out/frames.json``
beside the design, one entry per module instance path, in the module's own unturned coordinates::

    {"design": "shape.fk", "hulls": {"m": {"module": "Mod", "inside": "<sha of the inside>",
        "at": [x, y, rot], "box": [x0, y0, x1, y1], "area": 183, "runs": [[y, x0, x1], ...],
        "frame": {"source": "declared" | "territory" | "hull", "area": 240, "runs": [...]},
        "declared": {"area": 240, "size": [W, H]},
        "build": {"factory": "shape", "key": "<unit key>", "when": "2026-11-09T..."}}}}

The readers (``expand.own_frame``, ``frame_shape_of``, ``planned_shape``) resolve a module
instance's frame **hull, then territory, then declaration**, through a ``Resolver`` bound to the
design's ``Flat`` (``bind``: every module ``Inst`` and ``PortInst`` gets a ``_hull`` attribute;
``own_frame(inst)`` needs no other handle). Three rules keep it honest:

- the hull only refines: it never holds a tile outside the frame the unit was routed in (the
  declaration or the territory on the first build, the hull itself after), so a no-op rebuild
  records the same hull and re-keys nothing;
- a hull is stamped with a fingerprint of the module instance's inside (``inside_sha``: its
  declared frame, its ports, every instance and net in it, with their parameters and hints); a
  module whose inside changed drops its hull and is read as its declared or assigned frame
  again, so the ratchet never binds a module the designer is changing;
- ``fk layout FILE MODULE`` (module mode) lays the inside out in the declared or assigned frame,
  never the hull (``laying_out``: the scope being laid out skips the hull); a port's frame is the
  assigned or declared one too (a used port lies on the hull by construction: its carrier stands
  on the frame's edge tile).

A territory is read only while the instance stands where the placer put it (its corner hint equals
the cell's ``at``); a hand-moved instance is read as its declaration. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from .frame import Frame

__all__ = ["frames_path", "territories_path", "bind", "resolver", "laying_out", "inside_sha",
           "achieved", "assigned", "source", "declared", "record", "read_frames"]

_FILES = {}                   # abs path -> (mtime, size, data): frames.json / territories.json once
LINES = 12                    # the report names at most this many new or changed hulls


def frames_path(design):
    """``out/frames.json`` beside design file ``design``."""
    return os.path.join(os.path.dirname(os.path.abspath(design)), "out", "frames.json")


def territories_path(design):
    """``out/territories.json`` beside design file ``design`` (part T writes it)."""
    return os.path.join(os.path.dirname(os.path.abspath(design)), "out", "territories.json")


def _read_json(path):
    """A JSON file read once per change (mtime and size), {} when missing or unreadable."""
    try:
        st = os.stat(path)
    except OSError:
        _FILES.pop(path, None)
        return {}
    got = _FILES.get(path)
    if got is not None and got[0] == st.st_mtime_ns and got[1] == st.st_size:
        return got[2]
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    _FILES[path] = (st.st_mtime_ns, st.st_size, data)
    return data


def read_frames(design):
    """{instance path: entry} of ``out/frames.json`` beside ``design`` ({} when none)."""
    return dict(_read_json(frames_path(design)).get("hulls") or {})


def _design_of(flat):
    path = getattr(flat, "path", None)
    return os.path.abspath(path) if path else None


# -- the fingerprint ------------------------------------------------------------------------------
def inside_sha(flat, path):
    """A short sha of module instance ``path``'s inside as the design states it: its module and
    parameters, its declared frame, its ports, every instance under it (relative path, kind,
    parameters, ``@`` hint, count, Literal signature) and every net written in it (ends, items,
    width, lane, flags). The hull is stamped with it; a hull whose stamp differs from the design
    now is not read."""
    inst = flat.insts[path]
    pre = path + "/"
    insts = []
    for p in sorted(flat.insts):
        if not p.startswith(pre):
            continue                    # the instance's own place is not its inside: a twin
        q = flat.insts[p]               # moved keeps its hull
        hints = q.hints or {}
        at = hints.get("origin") or hints.get("at")
        lit = q.literal[3] if getattr(q, "literal", None) else None
        insts.append((p[len(path):], q.kind, q.module, sorted((k, repr(v)) for k, v in
                                                                (q.params or {}).items()),
                      None if at is None else tuple(at), repr(hints.get("patch")),
                      repr(getattr(q, "auto", None)), repr(lit)))
    ports = []
    for key in sorted(flat.ports):
        port = flat.ports[key]
        if port.scope != path and not port.scope.startswith(pre):
            continue
        ports.append((key[len(path):], port.dir, list(port.items), list(port.right or ()),
                      port.side, port.pos, port.lane))
    nets = []
    for name in sorted(flat.nets):
        if not name.startswith(pre):
            continue
        n = flat.nets[name]
        nets.append((name[len(path):], list(n.items), sorted(n.drivers), sorted(n.consumers),
                     n.width, n.lane, n.any, n.group, n.chain, repr(n.when)))
    own = sorted((k, repr(v)) for k, v in (inst.params or {}).items())
    text = repr((inst.module, inst.kind, own, inst.size, inst.shape, insts, ports, nets))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def declared(inst):
    """The declared frame of a module instance or a port's module (``shape`` as a Frame, else the
    ``size`` box), None when it declares neither: the last source."""
    from .expand import _declared_frame
    return _declared_frame(inst)


# -- the resolver -----------------------------------------------------------------------------------
class Resolver:
    """One design's frame overlay: the hulls of ``out/frames.json`` and the cells of
    ``out/territories.json`` beside it, resolved per module instance path in the module's own
    unturned coordinates. Bound to the Flat (``flat._hull``) and to each module Inst and PortInst
    (``_hull``), so ``expand.own_frame(inst)`` finds it."""

    def __init__(self, flat):
        self.flat = flat
        self.design = _design_of(flat)
        self.laying = None              # the scope `fk layout FILE MODULE` lays out: no hull
        self._sha = {}
        self._hull = {}
        self._cell = {}
        self._frames = None             # the files, read once per Flat: the overlay a build
        self._cells = None              # reads is fixed for its life (the hulls it records are
                                        # the next build's, never a later step's of this one)

    # -- the files
    def frames(self):
        if self._frames is None:
            self._frames = {} if self.design is None else \
                dict(_read_json(frames_path(self.design)).get("hulls") or {})
        return self._frames

    def cells(self):
        if self._cells is None:
            self._cells = {} if self.design is None else \
                dict(_read_json(territories_path(self.design)).get("cells") or {})
        return self._cells

    def sha(self, path):
        got = self._sha.get(path)
        if got is None:
            got = self._sha[path] = inside_sha(self.flat, path)
        return got

    def _ref(self, path):
        """The reference box (0, 0, W, H) of a declared module instance, or None."""
        inst = self.flat.insts.get(path)
        if inst is None or inst.module is None or inst.size is None:
            return None
        return (0, 0, int(inst.size[0]), int(inst.size[1]))

    # -- the sources
    def achieved(self, path):
        """The achieved hull of module instance ``path`` in its own frame, or None (none recorded,
        or recorded for another inside)."""
        if path in self._hull:
            return self._hull[path]
        got = None
        entry = self.frames().get(path)
        if isinstance(entry, dict) and entry.get("runs") and self._ref(path) is not None \
                and entry.get("inside") == self.sha(path):
            got = Frame.from_runs(tuple(r) for r in entry["runs"])
            if not got:
                got = None
        self._hull[path] = got
        return got

    def assigned(self, path):
        """The territory assigned to module instance ``path`` (part T's cell), in its own frame,
        or None: no cell, a module without a declared frame, or an instance moved since."""
        if path in self._cell:
            return self._cell[path]
        got = None
        cell = self.cells().get(path)
        ref = self._ref(path)
        if isinstance(cell, dict) and cell.get("runs") and cell.get("at") and ref is not None:
            inst = self.flat.insts[path]
            at = (inst.hints or {}).get("at")
            cx, cy, rot = (int(v) for v in cell["at"][:3])
            if at is not None and (int(at[0]), int(at[1]), int(at[2]) % 4) == (cx, cy, rot % 4):
                size = (ref[2] - ref[0], ref[3] - ref[1])
                got = Frame.from_runs(tuple(r) for r in cell["runs"]).moved(-cx, -cy) \
                    .unturn(rot, size)
                if not got:
                    got = None
        self._cell[path] = got
        return got

    def source(self, path, hull=True):
        """Which source ``path``'s frame comes from: "hull", "territory", "declared" or None."""
        if hull and path != self.laying and self.achieved(path) is not None:
            return "hull"
        if self.assigned(path) is not None:
            return "territory"
        inst = self.flat.insts.get(path)
        return "declared" if inst is not None and declared(inst) is not None else None

    def frame_for(self, path, hull=True):
        """The resolved frame of module instance ``path`` in its own coordinates (hull, territory,
        declaration), or None when nothing declares one."""
        if hull and path != self.laying:
            f = self.achieved(path)
            if f is not None:
                return f
        f = self.assigned(path)
        if f is not None:
            return f
        inst = self.flat.insts.get(path)
        return None if inst is None else declared(inst)

    def frame_of(self, obj):
        """``expand.own_frame``'s question for a bound object: a module Inst (its path; the hull
        unless it is the scope being laid out) or a PortInst (its scope; no hull). None hands the
        question back to the declaration."""
        path = getattr(obj, "scope", None) if getattr(obj, "side", None) is not None \
            else getattr(obj, "path", None)
        if path is None or path not in self.flat.insts:
            return None
        hull = getattr(obj, "side", None) is None
        if hull and path != self.laying:
            f = self.achieved(path)
            if f is not None:
                return f
        return self.assigned(path)


def resolver(flat):
    """The Flat's Resolver (made and bound on first use), or None for an object with no Flat."""
    if flat is None:
        return None
    res = flat.__dict__.get("_hull")
    if res is None:
        res = bind(flat)
    return res


def bind(flat):
    """Bind ``flat``'s Resolver to it and to every module instance and port in it (``_hull``):
    the frame readers call this; it costs one pass over the instances once per Flat."""
    res = flat.__dict__.get("_hull")
    if res is None:
        res = Resolver(flat)
        flat.__dict__["_hull"] = res
    for inst in flat.insts.values():
        if inst.module is not None and inst.__dict__.get("_hull") is not res:
            inst.__dict__["_hull"] = res
    for port in getattr(flat, "ports", {}).values():
        if port.__dict__.get("_hull") is not res:
            port.__dict__["_hull"] = res
    return res


def laying_out(flat, module):
    """``fk layout FILE MODULE`` (module mode) lays MODULE's first instance out inside its declared
    or assigned frame: that scope skips its hull while this Flat is read. ``module`` None clears
    it. -> the scope path, or None."""
    res = bind(flat)
    scope = None
    if module:
        scope = next((p for p, i in flat.insts.items() if i.module == module), None)
    res.laying = scope
    return scope


def achieved(flat, path):
    """Module instance ``path``'s achieved hull in its own frame, or None."""
    return resolver(flat).achieved(path)


def assigned(flat, path):
    """Module instance ``path``'s assigned territory in its own frame, or None."""
    return resolver(flat).assigned(path)


def source(flat, path, hull=True):
    """"hull", "territory", "declared" or None for module instance ``path``."""
    return resolver(flat).source(path, hull)


# -- recording ------------------------------------------------------------------------------------
def _unit_of(net, sealed):
    """The innermost sealed module instance net ``net`` is written in, "" for none."""
    parts = net.split("/")[:-1]
    found = ""
    for i in range(1, len(parts) + 1):
        pre = "/".join(parts[:i])
        if pre in sealed:
            found = pre
    return found


def record(flat, lay, cat, layout, sealed, compiled, own_all, failed, store, cinfo=None):
    """Write every sealed unit's achieved hull to ``out/frames.json`` beside the design: the one
    call ``route._route_layout`` makes once the units are laid. ``layout`` is the routed layout,
    ``sealed`` {unit path: (x0, y0, x1, y1, tiles)} the units' claimed frames, ``compiled``
    {unit path: key} the units compiled this build, ``cinfo`` the router's record of every
    sealed unit (twins included), ``own_all`` {unit: its nets}, ``failed`` {net: why}. Nothing
    is written without a ``store`` (a build; a bare ``route_layout`` call records nothing).

    The hull is not in the compile key: the unit's own frame there is its claim
    (``expand.claim_shape_of``), so a key is the same wherever the same inside is built and a
    rebuild that reads the hull stores nothing new. A unit with a failed net, with a net of its
    own the build did not lay (held by the player, skipped), or whose module declares no frame
    keeps the hull it has. -> the report lines: one per hull that is new or changed (at most
    ``LINES``), then one summary line."""
    if not store or (not cinfo and not compiled):
        return []
    design = _design_of(flat)
    if design is None:
        return []
    from . import fkp as fkpmod
    from .expand import claim_shape_of
    res = bind(flat)
    res.frames()                       # the overlay this build read, fixed before the file moves
    path = frames_path(design)
    old = _read_json(path)
    hulls = dict(old.get("hulls") or {}) if isinstance(old.get("hulls"), dict) else {}
    units = sorted(set(cinfo or {}) | set(compiled), key=lambda u: (-u.count("/"), u))
    cinfo = cinfo if cinfo is not None else {}
    # every entity by the unit it belongs to: the unit's own machines, and the carriers of its
    # nets and of the nets of every unsealed scope inside it (a nested sealed unit's are its own)
    tiles_of = {}
    nets_laid = {}                      # unit -> the nets whose carriers stand in it
    for e in layout.entities.values():
        owner = e.owner
        if owner.startswith("~"):
            u = _unit_of(owner[1:], sealed)
            if u:
                nets_laid.setdefault(u, set()).add(owner[1:])
        else:
            u = owner
            while u and u not in sealed:
                u = u.rsplit("/", 1)[0] if "/" in u else ""
        if not u:
            continue
        tiles_of.setdefault(u, []).append(e)
    when = time.strftime("%Y-%m-%dT%H:%M:%S")
    lines, changed, done = [], 0, 0
    for u in units:
        inst = flat.insts.get(u)
        rec = lay.insts.get(u)
        if inst is None or rec is None or inst.module is None or inst.size is None:
            continue
        mine = list(own_all.get(u, ()))
        if any(n in failed for n in mine):
            continue
        if any(n not in mine for n in nets_laid.get(u, ())):
            continue                    # a net of its own the build did not lay: held, skipped
        ref = (int(inst.size[0]), int(inst.size[1]))
        # the frame the unit's own nets were searched in: its claim (territory or declaration);
        # the hull is clipped to it and never holds a tile outside it
        routed_in = claim_shape_of(flat, lay, u, cat)
        src = res.source(u, hull=False)
        ents = [e for v, es in tiles_of.items() if v == u or v.startswith(u + "/") for e in es]
        tiles = set()
        for e in ents:
            for t in fkpmod.tiles_of(cat, e):
                tiles.add((int(t[0]), int(t[1])))
        gap = int((inst.hints or {}).get("gap", 0) or 0)
        hull_abs = Frame.from_tiles(tiles).grow(1 + gap).overlap(routed_in)
        own = hull_abs.moved(-int(rec.x), -int(rec.y)).unturn(rec.rot, ref)
        frame_own = routed_in.moved(-int(rec.x), -int(rec.y)).unturn(rec.rot, ref)
        decl = declared(inst)
        entry = {"module": inst.module, "inside": res.sha(u),
                 "at": [int(rec.x), int(rec.y), int(rec.rot) % 4],
                 "box": list(own.box) if own.box else None, "area": own.area,
                 "runs": [list(r) for r in own.runs()],
                 "frame": {"source": src, "area": routed_in.area,
                           "runs": [list(r) for r in frame_own.runs()]},
                 "declared": {"area": decl.area if decl is not None else None, "size": list(ref)},
                 "build": {"factory": flat.name,
                           "key": compiled.get(u) or (cinfo.get(u) or {}).get("key"),
                           "when": when}}
        was = hulls.get(u)
        same = isinstance(was, dict) and was.get("runs") == entry["runs"] \
            and was.get("inside") == entry["inside"]
        hulls[u] = entry
        done += 1
        if not same:
            changed += 1
            free = routed_in.area - own.area
            pct = (own.area * 100 // routed_in.area) if routed_in.area else 0
            if changed <= LINES:
                lines.append(f"hull      {u}: {own.area} of the {routed_in.area} tiles of its {src} "
                             f"frame ({pct} %), {free} left free")
    if not done:
        return []
    if changed > LINES:
        lines.append(f"hull      ... and {changed - LINES} more (out/frames.json has every one)")
    data = {"design": os.path.basename(design), "hulls": hulls}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
    except OSError as exc:
        return [f"hull      out/frames.json not written: {exc}"]
    _FILES.pop(path, None)
    lines.append(f"hull      {done} sealed module{'s' if done != 1 else ''} in out/frames.json: "
                 + (f"{changed} new or changed" if changed else "unchanged"))
    return lines
