"""fkcore.elaborate: a factory's .fk source -> the flat logical netlist, plus the netlist checks.

Elaboration expands every instance (built-in template or sub-module) into machines keyed
``<instance path>/<local>`` (``gears/m0``, ``iron/smelt/m3``), then resolves every net to endpoint
sets (CORE.md "Objects"):

1. explicit drivers, 2. ``X.*`` drivers (free output endpoints only), 3. the net's items (declared,
else the drivers' products), 4. explicit consumers, 5. ``X.*`` consumers (free input endpoints).

A ref adds only endpoints of the net's items. The checks are report lines and never stop anything:
TYPE, SUSHI_SINK, UNFED, UNCONSUMED, DOUBLE, UNBOUNDED. Malformed source (an unknown template, a
ref that resolves to nothing, a bad parameter) raises ElabError: no netlist exists for it.
Pure, stdlib only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import lang
from .templates import MSpec, TemplateError, literal_machines, machines as template_machines

__all__ = ["ElabError", "Machine", "FlatNet", "Check", "Flat", "load", "elaborate", "elaborate_file"]


class ElabError(ValueError):
    def __init__(self, path, line, msg):
        super().__init__(f"{path}:{line}: {msg}")
        self.path, self.line, self.msg = path, line, msg


@dataclass
class Machine:
    key: str
    inst: str                  # instance path, "/"-joined
    kind: str                  # template kind
    prototype: str
    recipe: str | None
    needs: dict
    makes: dict
    takes: frozenset | None
    sink: bool
    drain: float | None
    source: bool
    duty: float
    extra: dict = field(default_factory=dict)

    def accepts(self, item):
        return self.takes is None or item in self.takes


@dataclass
class FlatNet:
    name: str                  # path-qualified: "gear", "iron/ore"
    items: list
    drivers: list              # [(machine key, item)]
    consumers: list            # [(machine key, item)]
    declared: bool
    line: int

    @property
    def sushi(self):
        return len(self.items) > 1


@dataclass
class Check:
    code: str
    where: str
    msg: str
    line: int = 0

    def __str__(self):
        return f"{self.code:<11} {self.where}: {self.msg}"


@dataclass
class Inst:
    path: str
    kind: str
    params: dict
    hints: dict
    machines: list             # machine keys, all of them (recursively for a module)
    module: str | None         # module name when this is a sub-module instance
    scope: dict | None         # name -> Inst for a sub-module instance
    line: int
    literal: tuple | None = None   # Literal<file>: (entities, frame size, file origin, sig)


@dataclass
class Flat:
    name: str
    path: str
    machines: dict = field(default_factory=dict)    # key -> Machine
    nets: dict = field(default_factory=dict)        # name -> FlatNet
    insts: dict = field(default_factory=dict)       # path -> Inst
    asserts: list = field(default_factory=list)     # [(lang.Assert, scope path)]
    covers: list = field(default_factory=list)      # [(lang.Cover, scope path)]
    checks: list = field(default_factory=list)      # [Check]
    scopes: dict = field(default_factory=dict)      # scope path -> {name: Inst}

    def resolve_ref(self, ref, scope=""):
        """``Ref`` -> (Inst or None, machine keys); the Inst is None for a single machine."""
        return _resolve(self, ref, scope)


# -- loading --------------------------------------------------------------------------------------
def load(path):
    """Parse ``path`` and the modules it imports (relative to its folder). -> (File, modules)."""
    with open(path, encoding="utf-8") as fh:
        f = lang.parse(fh.read(), path)
    modules = dict(f.modules)
    _imports(f, os.path.dirname(os.path.abspath(path)), modules, {os.path.abspath(path)})
    return f, modules


def _imports(f, folder, modules, seen):
    for names, rel, line in f.imports:
        target = os.path.abspath(os.path.join(folder, rel))
        if not os.path.exists(target):
            raise ElabError(f.path, line, f"import: no file {rel}")
        with open(target, encoding="utf-8") as fh:
            g = lang.parse(fh.read(), target)
        if target not in seen:
            seen.add(target)
            _imports(g, os.path.dirname(target), modules, seen)
        for name in names:
            if name not in g.modules:
                raise ElabError(f.path, line, f"import: {rel} has no module {name}")
            if name in modules and modules[name] is not g.modules[name]:
                raise ElabError(f.path, line, f"import: module {name} is defined twice")
            modules[name] = g.modules[name]


def elaborate_file(path, cat, name=None, layout=None):
    f, modules = load(path)
    return elaborate(f, modules, cat, name or os.path.splitext(os.path.basename(path))[0],
                     layout)


# -- elaboration ----------------------------------------------------------------------------------
def _join(*parts):
    return "/".join(p for p in parts if p)


def _duty(params, path, line, src):
    v = params.get("duty")
    if v is None:
        return 1.0
    if not isinstance(v, (int, float)) or not 0 <= v <= 1:
        raise ElabError(src, line, f"{path}: duty must be between 0 and 1, got {v!r}")
    return float(v)


def elaborate(f, modules, cat, name="main", layout=None) -> Flat:
    """``layout`` (the factory's .fkp) is needed only by Literal instances."""
    flat = Flat(name, f.path)
    flat._layout = layout
    _expand(flat, f.body, "", modules, cat, 1.0, f.path, ())
    _resolve_nets(flat)
    _endpoint_checks(flat)
    return flat


def _expand(flat, mod, prefix, modules, cat, duty, src, stack):
    scope = {}
    flat.scopes[prefix] = scope
    for inst in mod.insts:
        path = _join(prefix, inst.name)
        if inst.name in scope:
            raise ElabError(src, inst.line, f"{inst.name} is defined twice")
        d = min(duty, _duty(inst.params, path, inst.line, src))
        if inst.kind in modules:
            if inst.kind in stack:
                raise ElabError(src, inst.line, f"module {inst.kind} contains itself")
            extra = sorted(set(inst.params) - {"duty"})
            if extra:
                raise ElabError(src, inst.line, f"{path}: a module instance takes only duty=, "
                                                f"not {', '.join(extra)}")
            before = set(flat.machines)
            _expand(flat, modules[inst.kind], path, modules, cat, d, src, stack + (inst.kind,))
            keys = [k for k in flat.machines if k not in before]
            node = Inst(path, inst.kind, inst.params, inst.hints, keys, inst.kind,
                        flat.scopes[path], inst.line)
        else:
            params = {k: v for k, v in inst.params.items() if k != "duty"}
            imported = None
            try:
                if inst.kind == "Literal":
                    ents = _literal_entities(flat, path, params, cat, src)
                    if isinstance(ents, tuple):
                        imported, ents = ents, ents[0]
                    specs = literal_machines(ents, cat)     # a power plant may have none
                else:
                    specs = template_machines(inst.kind, params, cat)
            except TemplateError as exc:
                raise ElabError(src, inst.line, f"{path} = {inst.kind}: {exc}") from None
            keys = []
            for spec in specs:
                m = _machine(spec, path, inst.kind, d)
                flat.machines[m.key] = m
                keys.append(m.key)
            node = Inst(path, inst.kind, inst.params, inst.hints, keys, None, None, inst.line,
                        imported)
        scope[inst.name] = node
        flat.insts[path] = node
    for net in mod.nets:
        full = _join(prefix, net.name)
        if full in flat.nets:
            raise ElabError(src, net.line, f"net {net.name} is defined twice")
        flat.nets[full] = _Pending(net, prefix, src)
    for a in mod.asserts:
        flat.asserts.append((a, prefix))
    for c in mod.covers:
        flat.covers.append((c, prefix))


def _literal_entities(flat, path, params, cat, src):
    """A Literal's entities: imported from ``file=`` (-> the import tuple), else pinned in the .fkp."""
    from . import literal
    extra = sorted(set(params) - {"file", "box"})
    if extra:
        raise TemplateError(f"a Literal takes file=, box= and duty=, not {', '.join(extra)}")
    if "file" in params:
        try:
            ents, size, origin = literal.import_entities(literal.resolve(src, params["file"]),
                                                         path, cat, params.get("box"))
        except (literal.LiteralError, OSError) as exc:
            raise TemplateError(str(exc)) from None
        return ents, size, origin, literal.signature(ents, size)
    if flat._layout is None:
        raise TemplateError("a Literal without file= needs the factory's .fkp")
    ents = [e for e in flat._layout.entities.values() if e.owner == path]
    if not ents:
        raise TemplateError("the .fkp has no entities under it")
    return ents


def _machine(spec: MSpec, path, kind, duty):
    return Machine(_join(path, spec.local), path, kind, spec.prototype, spec.recipe,
                   dict(spec.needs), dict(spec.makes), spec.takes, spec.sink, spec.drain,
                   spec.source, duty, dict(spec.extra))


@dataclass
class _Pending:
    net: lang.Net
    scope: str
    src: str


def _resolve(flat, ref, scope):
    names = flat.scopes.get(scope, {})
    node = names.get(ref.parts[0])
    if node is None:
        return None, []
    for part in ref.parts[1:]:
        if node.scope is not None and part in node.scope:
            node = node.scope[part]
            continue
        key = _join(node.path, part)
        if node.scope is None and key in flat.machines:
            return None, [key]
        return None, []
    return node, list(node.machines)


def _resolve_nets(flat):
    pending = list(flat.nets.items())
    work = {}
    out_hold, in_hold = {}, {}

    def machines_of(p, ref):
        _node, keys = _resolve(flat, ref, p.scope)
        if not keys:
            raise ElabError(p.src, ref.line, f"net {p.net.name}: {ref} names nothing")
        return keys

    for name, p in pending:
        work[name] = {"items": list(p.net.items) if p.net.items else None,
                      "drivers": [], "consumers": []}

    def add_drivers(name, p, ref, free_only):
        w = work[name]
        added = 0
        for key in machines_of(p, ref):
            for item in flat.machines[key].makes:
                if w["items"] is not None and item not in w["items"]:
                    continue
                if free_only and (key, item) in out_hold:
                    continue
                if (key, item) in w["drivers"]:
                    continue
                w["drivers"].append((key, item))
                out_hold.setdefault((key, item), []).append(name)
                added += 1
        if not added:
            flat.checks.append(Check("TYPE", f"net {name}", f"driver {ref} makes no "
                                     + _items_text(w["items"]) + (" that is still free"
                                                                  if free_only else ""),
                                     ref.line))

    def add_consumers(name, p, ref, free_only):
        w = work[name]
        added = 0
        for key in machines_of(p, ref):
            m = flat.machines[key]
            for item in w["items"]:
                if not m.accepts(item):
                    continue
                if free_only and (key, item) in in_hold:
                    continue
                if (key, item) in w["consumers"]:
                    continue
                w["consumers"].append((key, item))
                in_hold.setdefault((key, item), []).append(name)
                added += 1
        if not added:
            flat.checks.append(Check("TYPE", f"net {name}", f"consumer {ref} takes no "
                                     + _items_text(w["items"]) + (" that is still free"
                                                                  if free_only else ""),
                                     ref.line))

    for star in (False, True):
        for name, p in pending:
            for ref in p.net.drivers:
                if ref.star == star:
                    add_drivers(name, p, ref, star)
    for name, p in pending:
        w = work[name]
        if w["items"] is None:
            items = []
            for _key, item in w["drivers"]:
                if item not in items:
                    items.append(item)
            w["items"] = items
        else:
            made = {item for _key, item in w["drivers"]}
            for item in w["items"]:
                if item not in made:
                    flat.checks.append(Check("TYPE", f"net {name}",
                                             f"expects {item} but no driver makes it", p.net.line))
    for star in (False, True):
        for name, p in pending:
            for ref in p.net.consumers:
                if ref.star == star:
                    add_consumers(name, p, ref, star)

    for name, p in pending:
        w = work[name]
        flat.nets[name] = FlatNet(name, w["items"], w["drivers"], w["consumers"],
                                  p.net.items is not None, p.net.line)
    flat._out_hold, flat._in_hold = out_hold, in_hold


def _items_text(items):
    if items is None:
        return "item"
    return items[0] if len(items) == 1 else "{" + ", ".join(items) + "}"


def _group(rows):
    """[(inst, item, machine)] -> [(inst, item, count)] in first-seen order."""
    out = {}
    for inst, item, _m in rows:
        out[(inst, item)] = out.get((inst, item), 0) + 1
    return [(inst, item, n) for (inst, item), n in out.items()]


#: chests that put what reaches them into the logistic network
_STORES = ("provider", "storage")
#: the 1.1 check lines about limited production (tests of other things leave them out)
ADVICE = ("CLOG", "UNLIMITED", "SHARED_SINK")


def _unlimited(m):
    return m.sink and m.extra.get("role") in _STORES and m.extra.get("limit") is None


def _clog_checks(flat, in_hold, fed):
    """1.1 (Rory, 2026-10-20): in the game, production is never shared out in proportion.

    - ``CLOG``: a sushi net (two or more items on one belt), or a chest fed two or more items by
      any nets: whatever comes faster than it is used fills the belt or the chest, and the other
      items stop behind it. Only limited production keeps it running (each item no faster than it
      is used), or one net and one chest per item.
    - ``UNLIMITED``: a provider or storage chest without ``limit=``: everything that reaches it goes
      into the logistic network, without end (the 0534 run's network held 4800 iron and 5300
      copper plates).
    - ``SHARED_SINK``: such a chest on a net with machines: whichever stands first on the belt gets
      its fill, and an unlimited chest takes all it is given, so the machines after it can starve
      (the 0534 run's red science stood at 0% behind a copper chest).
    """
    for name, net in flat.nets.items():
        if net.sushi:
            flat.checks.append(Check(
                "CLOG", f"net {name}",
                f"{', '.join(net.items)} share one belt: an item that comes faster than it is used "
                "fills the belt and stops the others. Make each no faster than it is used, or give "
                "each its own net", net.line))
    items = {}
    for (key, item), nets in in_hold.items():
        items.setdefault(key, {})[item] = nets
    for key, got in items.items():
        m = flat.machines[key]
        nets = sorted({n for ns in got.values() for n in ns})
        if m.sink and m.takes is None and len(got) > 1 and len(nets) > 1:
            flat.checks.append(Check(
                "CLOG", m.inst,
                f"takes {', '.join(sorted(got))} from nets {', '.join(nets)}: whichever comes faster "
                "fills it and the others stop. Give each item a chest of its own with limit="))
    for key, m in flat.machines.items():
        if _unlimited(m) and key in fed:
            flat.checks.append(Check(
                "UNLIMITED", m.inst,
                "everything that reaches it goes into the logistic network, without end: limit=N "
                "(slots) stops what feeds it once it holds that much"))
    for name, net in flat.nets.items():
        chests = sorted({flat.machines[k].inst for k, _i in net.consumers
                         if _unlimited(flat.machines[k])})
        machines = sorted({flat.machines[k].inst for k, _i in net.consumers
                           if not flat.machines[k].sink})
        if chests and machines:
            flat.checks.append(Check(
                "SHARED_SINK", f"net {name}",
                f"{', '.join(chests)} takes without limit from the net {', '.join(machines)} also "
                "takes from: whoever stands first on the belt gets its fill, so the machines can "
                "starve. Give the chest limit=, or a net of its own", net.line))


def _endpoint_checks(flat):
    out_hold, in_hold = flat._out_hold, flat._in_hold
    for side, hold in (("out", out_hold), ("in", in_hold)):
        for (key, item), nets in hold.items():
            if len(nets) > 1:
                flat.checks.append(Check("DOUBLE", key, f"{item} ({side}) is on {len(nets)} "
                                         "nets: " + ", ".join(nets)))
    fed = {key for key, _item in in_hold}
    unfed, unconsumed = [], []
    for key, m in flat.machines.items():
        for item in m.needs:
            if (key, item) not in in_hold:
                unfed.append((m.inst, item, key))
        if m.sink and key not in fed:
            unfed.append((m.inst, "anything", key))
        for item in m.makes:
            if (key, item) not in out_hold:
                unconsumed.append((m.inst, item, key))
    for inst, item, n in _group(unfed):
        flat.checks.append(Check("UNFED", inst, f"{item} has no net"
                                 + (f" ({n} machines)" if n > 1 else "")))
    for inst, item, n in _group(unconsumed):
        flat.checks.append(Check("UNCONSUMED", inst, f"{item} goes on no net"
                                 + (f" ({n} machines)" if n > 1 else "")))
    for name, net in flat.nets.items():
        if not net.sushi:
            continue
        rows = []
        for key, _item in net.consumers:
            m = flat.machines[key]
            if m.takes is None:
                continue
            missing = [i for i in net.items if i not in m.takes]
            if missing and all(r[2] != key for r in rows):
                rows.append((m.inst, ", ".join(missing), key))
        for inst, missing, n in _group(rows):
            flat.checks.append(Check("SUSHI_SINK", f"net {name}",
                                     f"{inst} does not take {missing}"
                                     + (f" ({n} machines)" if n > 1 else ""), net.line))
    _clog_checks(flat, in_hold, fed)
    seen = set()
    driving = {key for key, _item in out_hold}
    for key, m in flat.machines.items():
        if m.source and m.inst not in seen and key in driving:
            seen.add(m.inst)
            item = next(iter(m.makes))
            flat.checks.append(Check("UNBOUNDED", m.inst, f"{item} from the logistic network has "
                                     "no rate; everything downstream of it is unbounded"))
