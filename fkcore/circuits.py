"""fkcore.circuits: circuits in the source (2.0): signals, wire nets, gated nets, conditions, the
makers' limits and the recipe guard, checked on paper and then laid onto a factory's layout.

Rory (2026-10-21): "circuit wiring in the source, with all circuit and logic conditions in the .fk
code, inserter limits included", and "Recipe-switch smarts (inserters that don't carry the wrong
item) belong in circuits in the game, not in scripted toolkit actions". The draft is
drafts\\reactor-1.1\\CIRCUITS-1.1.md, with fnet's rules (CIRCUITS-ROADMAP.md): a wire net is one
colour; a signal is declared, pinned (``signal temp = signal-T``) or left to the build (``signal
x``: the first free virtual signal of fnet's auto pool, at normal quality); checks warn, never gate.

What the source says, and what the layout gets:

- ``wire W red: drivers -> consumers``: a net of signals. A driver is an instance that puts
  signals on it (a chest its contents, ``Reactor<read=temperature, signal=S>`` its temperature,
  ``Constant<signals=...>`` its signals, a crafter with ``guard`` its ingredients) or a net (one of
  its belts reads its contents, ``read=hold``). A consumer is an instance with a ``when`` on W, or
  a gated net. A ``when`` that reads W adds its net or instance to W's consumers.
- ``net N: ... when W.S < 550``: a gated net. Every inserter and pump that carries N (the route's
  and its rows' own) gets the condition (``if=S<550``) and joins W. ``when network.S < 100`` is a
  logistic condition (``logistic=S<100``, no wire); ``when I.S < 100`` reads instance I on a red
  wire of its own, ``I.signals``.
- ``x = Assembler<...> when ...``: the machine's own enable condition, the same three ways.
- ``keep=N`` on a maker: every inserter that takes its product out into a chest, straight in or
  onto the belt of a net that ends in a chest, runs while the logistic network holds fewer than
  N of it (``logistic=ITEM<N``, no wire). ``fill=N``: every inserter that takes it straight into a
  chest runs while that chest holds fewer than N (``if=ITEM<N`` and a red wire, the chest's
  ``.signals``). These are real limits; they don't silence ``CLOG`` (Rory, 2026-10-21: only one
  inserter from the source into each sink, or ``limited``, does).
- ``guard`` on a crafter: it reads its recipe's ingredients (``read=ingredients``) onto a red wire
  to every inserter that feeds it, which sets its filters from them (``filter=circuit``). A
  recipe changed in the game changes what they carry, with no script and no new paste of them.

The wires of a wire net are a minimum spanning tree over its entities, centre to centre, each
within both ends' reach (9 tiles, a pole's wire reach): a longer one is a ``WIRE_REACH`` line
(wires are not routed through poles yet). ``behave`` blocks keep their lines: a ``require`` with
numbers from the catalog is checked (``REQUIRE``), a gated net with no ``cycle`` on its wire is a
``GATED`` line (the rate model takes it as always open), ``expect`` lines are reported.

:func:`resolve` (elaborate, on paper) -> :class:`Circuit` and its check lines; :func:`lay` (the
build, before the floorplan composes) -> the layout with its circuit settings and ``wire`` / ``w``
records, laid again from the source on every build. Pure, stdlib only.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import codec
from . import fkp as fkpmod
from . import lang

__all__ = ["Circuit", "WireDef", "CondDef", "resolve", "lay", "NON_TRANSMITTING",
           "auto_pool", "FILTER_HANDS"]

#: signals the game accepts and never sends on a wire (fnet's signal_space.EXCLUDED, measured live)
NON_TRANSMITTING = frozenset({"signal-fluid-parameter", "signal-fuel-parameter",
                              "signal-item-parameter", "signal-signal-parameter",
                              "signal-unknown"})
_WILDCARDS = frozenset({"signal-each", "signal-everything", "signal-anything",
                        "signal-any-quality"})
#: inserters that can filter (2.0: the fast and bulk inserters took over the filter ones)
FILTER_HANDS = frozenset({"fast-inserter", "bulk-inserter", "stack-inserter"})
#: entity types a condition can enable
_ENABLE = frozenset({"inserter", "pump", "offshore-pump", "assembling-machine", "furnace",
                     "mining-drill", "lamp", "transport-belt"})
#: what a gated net's route enables: its inserters and pumps
_GATED = frozenset({"inserter", "pump"})
#: catalog facts a ``require`` line may read (2.0 prototype values)
FACTS = {"heat-exchanger": {"min_temperature": 500.0, "max_temperature": 500.0},
         "nuclear-reactor": {"max_temperature": 1000.0}}
#: an implicit wire's name: what instance I puts out, read by a ``when I.S``, ``fill`` or ``guard``
IMPLICIT = "{}.signals"
_CHEST_ROLES = ("provider", "storage", "buffer", "plain")


def auto_pool():
    """fnet's auto pool, at normal quality: the virtual signals that are not wildcards, letters,
    digits or reserved, sorted."""
    letters = {f"signal-{c}" for c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
    return [n for n in sorted(codec.VIRTUAL_SIGNALS)
            if n not in _WILDCARDS and n not in letters and n not in NON_TRANSMITTING]


@dataclass
class CondDef:
    kind: str                  # "wire" | "network"
    wire: str | None           # the wire net (an implicit one for I.S)
    signal: str                # the game signal
    op: str                    # a lang.COMPARATORS
    right: object              # int or a game signal (on the same wire)
    text: str                  # as written
    line: int

    def attr(self):
        """The .fkp setting: (``if`` | ``logistic``, ``S<N``)."""
        return ("logistic" if self.kind == "network" else "if",
                f"{self.signal}{self.op}{self.right}")


@dataclass
class WireDef:
    name: str
    colour: str
    drivers: list = field(default_factory=list)      # [("machine", key) | ("net", name)]
    consumers: list = field(default_factory=list)    # [("machine", key) | ("net", name)]
    line: int = 0
    implicit: bool = False
    signals: set | None = None   # what its drivers put on it, when every driver's is known


@dataclass
class Circuit:
    signals: dict = field(default_factory=dict)      # scoped name -> game signal
    autos: dict = field(default_factory=dict)        # scoped name -> game signal (the build's)
    wires: dict = field(default_factory=dict)        # name -> WireDef
    gates: dict = field(default_factory=dict)        # net -> CondDef
    enables: dict = field(default_factory=dict)      # instance path -> CondDef
    limits: list = field(default_factory=list)       # [(instance path, "keep" | "fill", N)]
    guards: list = field(default_factory=list)       # [instance path]
    settings: dict = field(default_factory=dict)     # machine key -> {attr: value}
    behaves: list = field(default_factory=list)      # [lang.Behave, with its scope]
    expects: list = field(default_factory=list)      # [lang.Expect]
    notes: list = field(default_factory=list)        # report lines from resolving

    @property
    def empty(self):
        return not (self.wires or self.gates or self.enables or self.limits or self.guards
                    or self.settings)


# -- on paper --------------------------------------------------------------------------------------
def _join(*parts):
    return "/".join(p for p in parts if p)


def _chain(scope):
    """``scope`` and every enclosing one, innermost first."""
    parts = scope.split("/") if scope else []
    return ["/".join(parts[:i]) for i in range(len(parts), -1, -1)]


def _known(name, cat):
    return name in codec.VIRTUAL_SIGNALS or cat.is_fluid(name) or cat.is_item(name)


class _Resolver:
    def __init__(self, flat, cat):
        from .elaborate import Check
        self.flat, self.cat, self.Check = flat, cat, Check
        self.c = Circuit()
        self.declared = {}                 # scoped name -> lang.Signal

    def check(self, code, where, msg, line=0):
        self.flat.checks.append(self.Check(code, where, msg, line))

    # signals
    def signals(self):
        taken = set()
        autos = []
        for sig, scope in self.flat.circuit_src.get("signals", ()):
            full = _join(scope, sig.name)
            if full in self.declared:
                self.check("SIGNAL", f"signal {full}", "declared twice", sig.line)
                continue
            self.declared[full] = sig
            if sig.game is None:
                autos.append(full)
                continue
            if not _known(sig.game, self.cat):
                self.check("SIGNAL", f"signal {full}", f"{sig.game} is no game signal (a virtual "
                           "signal like signal-T, an item or a fluid)", sig.line)
            elif sig.game in NON_TRANSMITTING:
                self.check("SIGNAL", f"signal {full}", f"{sig.game} never goes out on a wire "
                           "(the game takes it and sends nothing)", sig.line)
            self.c.signals[full] = sig.game
            taken.add(sig.game)
        pool = [n for n in auto_pool() if n not in taken]
        for k, full in enumerate(autos):
            if k >= len(pool):
                self.check("SIGNAL", f"signal {full}", "no free virtual signal left for it")
                continue
            self.c.signals[full] = self.c.autos[full] = pool[k]
        if self.c.autos:
            self.c.notes.append("signals the build picked: " + ", ".join(
                f"{n} = {g}" for n, g in sorted(self.c.autos.items())))

    def game(self, name, scope, where, line):
        """A signal as written -> its game name (a declared one, else the name itself)."""
        for s in _chain(scope):
            full = _join(s, name)
            if full in self.c.signals:
                return self.c.signals[full]
        if not _known(name, self.cat):
            self.check("SIGNAL", where, f"{name} is no declared signal and no game signal",
                       line)
        elif name in NON_TRANSMITTING:
            self.check("SIGNAL", where, f"{name} never goes out on a wire", line)
        return name

    # wires
    def member(self, ref, scope, where, line):
        """A wire end as written -> [("machine", key), ...] or [("net", name)]; [] and a WIRE
        line when it names nothing."""
        node, keys = self.flat.resolve_ref(ref, scope)
        if keys:
            return [("machine", k) for k in keys]
        if len(ref.parts) == 1:
            for s in _chain(scope):
                net = _join(s, ref.parts[0])
                if net in self.flat.nets:
                    return [("net", net)]
        self.check("WIRE", where, f"{ref} names no instance or net", line)
        return []

    def wires(self):
        for w, scope in self.flat.circuit_src.get("wires", ()):
            full = _join(scope, w.name)
            if full in self.c.wires:
                self.check("WIRE", f"wire {full}", "declared twice", w.line)
                continue
            d = WireDef(full, w.colour, line=w.line)
            for ref in w.drivers:
                d.drivers += self.member(ref, scope, f"wire {full}", w.line)
            for ref in w.consumers:
                d.consumers += self.member(ref, scope, f"wire {full}", w.line)
            self.c.wires[full] = d

    def wire_named(self, name, scope):
        for s in _chain(scope):
            full = _join(s, name)
            if full in self.c.wires:
                return full
        return None

    def implicit(self, path, keys):
        name = IMPLICIT.format(path)
        if name not in self.c.wires:
            self.c.wires[name] = WireDef(name, "red", [("machine", k) for k in keys],
                                         implicit=True)
        return name

    # conditions
    def cond(self, cond, scope, consumer, where):
        """lang.Cond -> CondDef (None when it can't be read), joining ``consumer`` to its wire."""
        left = cond.left
        if left.source == ["network"]:
            kind, wire = "network", None
        else:
            wire = self.wire_named(left.source[0], scope) if len(left.source) == 1 else None
            kind = "wire"
            if wire is None:
                node, keys = self.flat.resolve_ref(lang.Ref(left.source, False, cond.line), scope)
                if not keys:
                    self.check("SIGNAL", where, f"when {cond}: {'.'.join(left.source)} names no "
                               "wire, instance or network", cond.line)
                    return None
                wire = self.implicit(node.path if node is not None else keys[0], keys)
        sig = self.game(left.signal, scope, where, cond.line)
        right = cond.right
        if isinstance(right, lang.Operand):
            if right.source != left.source:
                self.check("SIGNAL", where, f"when {cond}: a condition compares two signals on "
                           "one wire", cond.line)
            right = self.game(right.signal, scope, where, cond.line)
        elif not isinstance(right, int):
            self.check("SIGNAL", where, f"when {cond}: the game compares with whole numbers",
                       cond.line)
            right = int(right)
        if kind == "network" and not self.cat.is_item(sig):
            self.check("SIGNAL", where, f"when {cond}: the logistic network counts items, and "
                       f"{sig} is none", cond.line)
        if wire is not None and consumer not in self.c.wires[wire].consumers:
            self.c.wires[wire].consumers.append(consumer)
        return CondDef(kind, wire, sig, cond.op, right, str(cond), cond.line)

    def conditions(self):
        for name, net in self.flat.nets.items():
            if net.when is not None:
                got = self.cond(net.when[0], net.when[1], ("net", name), f"net {name}")
                if got is not None:
                    self.c.gates[name] = got
        for path, inst in self.flat.insts.items():
            if inst.when is None:
                continue
            if inst.module is not None:
                self.check("SIGNAL", path, "a module instance has no condition of its own; "
                           "write when on its machines", inst.line)
                continue
            if not inst.machines:
                continue
            got = self.cond(inst.when[0], inst.when[1], ("machine", inst.machines[0]), path)
            if got is None:
                continue
            self.c.enables[path] = got
            if got.wire is not None:
                w = self.c.wires[got.wire]
                w.consumers += [("machine", k) for k in inst.machines[1:]
                                if ("machine", k) not in w.consumers]

    # settings, limits, guard
    def instance_settings(self):
        for path, inst in self.flat.insts.items():
            if inst.module is not None or not inst.machines:
                continue
            scope = path.rsplit("/", 1)[0] if "/" in path else ""
            p = inst.params
            if inst.kind == "Reactor" and p.get("read") == "temperature":
                sig = self.game(str(p.get("signal", "signal-T")), scope, path, inst.line)
                for key in inst.machines:
                    self.c.settings.setdefault(key, {}).update(read="temperature", signal=sig)
            if inst.kind == "Constant" and p.get("signals") is not None:
                rows = self.constant(str(p["signals"]), scope, path, inst.line)
                for key in inst.machines:
                    self.c.settings.setdefault(key, {})["signals"] = "|".join(
                        f"{s}:{n}" for s, n in rows)
            for kind in ("keep", "fill"):
                if p.get(kind) is None:
                    continue
                n = p[kind]
                if isinstance(n, float) and n.is_integer():
                    n = int(n)
                if not isinstance(n, int) or n < 1:
                    from .elaborate import ElabError
                    raise ElabError(self.flat.path, inst.line, f"{path}: {kind} is how many of "
                                    f"its product, a whole number from 1, got {n!r}")
                made = {i for k in inst.machines for i in self.flat.machines[k].makes}
                if not made:
                    self.check("LIMIT", path, f"{kind}={n}: {inst.kind} makes no item to limit",
                               inst.line)
                    continue
                self.c.limits.append((path, kind, n))
            if p.get("guard") is not None:
                if p["guard"] is not True:
                    self.check("GUARD", path, "guard is a flag: write it bare, Assembler<recipe=x, "
                               "guard>", inst.line)
                recipes = {self.flat.machines[k].recipe for k in inst.machines}
                if recipes == {None}:
                    self.check("GUARD", path, f"guard: {inst.kind} has no recipe to read",
                               inst.line)
                    continue
                self.c.guards.append(path)
                self.implicit(path, inst.machines)
                for key in inst.machines:
                    self.c.settings.setdefault(key, {})["read"] = "ingredients"

    def constant(self, text, scope, where, line):
        rows = []
        for part in [t.strip() for t in text.split(",") if t.strip()]:
            name, eq, count = part.partition("=")
            if not eq or not re.fullmatch(r"-?\d+", count.strip()):
                from .elaborate import ElabError
                raise ElabError(self.flat.path, line, f'{where}: signals="S=N, T=M", got {text!r}')
            rows.append((self.game(name.strip(), scope, where, line), int(count)))
        return rows

    # what each wire carries, and the paper checks
    def driven(self):
        for w in self.c.wires.values():
            sigs = set()
            for kind, ref in w.drivers:
                got = self.driver_signals(kind, ref)
                if got is None:
                    sigs = None
                    break
                sigs |= got
            w.signals = sigs

    def driver_signals(self, kind, ref):
        if kind == "net":
            return set(self.flat.nets[ref].items)
        m = self.flat.machines[ref]
        got = self.c.settings.get(ref, {})
        if got.get("read") == "temperature":
            return {got["signal"]}
        if got.get("signals"):
            return {p.rsplit(":", 1)[0] for p in got["signals"].split("|")}
        if got.get("read") == "ingredients" and m.recipe:
            return set(m.needs)
        return None                     # a chest: whatever it holds

    def paper_checks(self):
        behaved = {}
        for b, scope in self.flat.circuit_src.get("behaves", ()):
            wire = self.wire_named(b.wire, scope)
            if wire is None:
                self.check("WIRE", f"behave {b.name}", f"on {b.wire}: no such wire", b.line)
            behaved.setdefault(wire, []).append(b)
            self.c.behaves.append((b, scope))
            for kind, text, line in b.lines:
                if kind == "require":
                    self.require(b, text, scope, line)
        self.c.expects = [e for e, _scope in self.flat.circuit_src.get("expects", ())]
        for name, w in sorted(self.c.wires.items()):
            if w.implicit:
                continue
            if not w.drivers:
                self.check("WIRE", f"wire {name}", "nothing drives it", w.line)
            if not w.consumers:
                self.check("WIRE", f"wire {name}", "nothing reads it", w.line)
            for kind, ref in w.consumers:
                if kind == "net" and (ref not in self.c.gates or self.c.gates[ref].wire != name):
                    self.check("WIRE", f"wire {name}", f"net {ref} reads it but has no when on "
                               f"it (net {ref}: ... when {name}.SIGNAL < N)", w.line)
        for where, cd in [(f"net {n}", g) for n, g in self.c.gates.items()] + \
                         [(p, e) for p, e in self.c.enables.items()]:
            if cd.wire is None:
                continue
            sigs = self.c.wires[cd.wire].signals
            for s in [cd.signal] + ([cd.right] if isinstance(cd.right, str) else []):
                if sigs is not None and s not in sigs and s not in _WILDCARDS:
                    self.check("SIGNAL", where, f"when {cd.text}: no driver on {cd.wire} puts "
                               f"{s} on it (it carries {', '.join(sorted(sigs)) or 'nothing'})",
                               cd.line)
        for name, g in sorted(self.c.gates.items()):
            cycles = [t for b in behaved.get(g.wire, ()) for k, t, _l in b.lines if k == "cycle"]
            if cycles:
                self.c.notes.append(f"gated net {name} ({g.text}): " + "; ".join(cycles))
            else:
                self.check("GATED", f"net {name}", f"gated ({g.text}): the rate model takes it as "
                           "always open" + ("" if g.wire is None else
                                            f"; a behave block on {g.wire} with a cycle says how "
                                            "often it runs"), self.flat.nets[name].line)

    def require(self, b, text, scope, line):
        m = re.fullmatch(r"(\S+)\s*(<=|>=|!=|==|=|<|>)\s*(\S+)", text)
        vals = []
        for side in (m.group(1), m.group(3)) if m else ():
            vals.append(self.fact(side, scope))
        if not m or None in vals:
            self.c.notes.append(f"behave {b.name}: require {text}: checked in the game")
            return
        a, op, z = vals[0], m.group(2), vals[1]
        ok = {"<": a < z, ">": a > z, "<=": a <= z, ">=": a >= z, "=": a == z, "==": a == z,
              "!=": a != z}[op]
        if not ok:
            self.check("REQUIRE", f"behave {b.name}", f"require {text}: {a:g} {op} {z:g} does "
                       "not hold", line)
        else:
            self.c.notes.append(f"behave {b.name}: require {text}: holds ({a:g} {op} {z:g})")

    def fact(self, text, scope):
        try:
            return float(text)
        except ValueError:
            pass
        inst, dot, fact = text.rpartition(".")
        if not dot:
            return None
        node, keys = self.flat.resolve_ref(lang.Ref(inst.split("."), False, 0), scope)
        if not keys:
            return None
        return FACTS.get(self.flat.machines[keys[0]].prototype, {}).get(fact)


def resolve(flat, cat) -> Circuit:
    """The factory's circuits from its source (``flat.circuit_src``, the nets' and instances'
    ``when``, the instances' circuit parameters); check lines go to ``flat.checks``."""
    r = _Resolver(flat, cat)
    r.signals()
    r.wires()
    r.instance_settings()
    r.conditions()
    r.driven()
    r.paper_checks()
    return r.c


# -- on the layout ---------------------------------------------------------------------------------
def _distance(a, b):
    return math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))


class _Layer:
    """One pass over a layout: the settings to write, the wires to lay, the report."""

    def __init__(self, flat, out, cat):
        from .elaborate import Check
        from . import connect
        self.flat, self.lay, self.cat, self.Check = flat, out, cat, Check
        self.c = flat.circuit
        self.wires = dict(self.c.wires)                # the declared and implicit, plus fill's
        self.lines, self.checks = [], []
        self.members = {}                              # wire -> [(entity key, port)]
        self.g = connect.graph(out, cat)

    def check(self, code, where, msg):
        self.checks.append(self.Check(code, where, msg))

    def kind(self, key):
        try:
            return self.cat.kind(self.lay.entities[key].name)
        except KeyError:
            return ""

    def set(self, key, attr, value, why):
        e = self.lay.entities[key]
        have = e.attrs.get(attr)
        if have is not None and have != value:
            self.check("CIRCUIT", key, f"{attr}={have} and {attr}={value} ({why}): the entity "
                       f"takes one; it keeps {attr}={have}")
            return False
        e.attrs[attr] = value
        return True

    def join(self, wire, key):
        got = self.members.setdefault(wire, [])
        if (key, None) not in got:
            got.append((key, None))

    def hops_out(self, key):
        """The inserters that pick from machine ``key``: [(inserter, what it drops into)]."""
        return [(k, self.drop(k)) for k, via in self.g.succ.get(key, ()) if via == "pickup"]

    def hops_in(self, key):
        return [k for k, via in self.g.pred.get(key, ()) if via == "drop"]

    def drop(self, ins):
        got = [k for k, via in self.g.succ.get(ins, ()) if via == "drop"]
        return got[0] if got else None

    def store(self, key):
        """Machine ``key`` is a chest that takes what reaches it."""
        m = self.flat.machines.get(key)
        return m is not None and m.sink and m.extra.get("role") in _CHEST_ROLES

    # the parts
    def machine_settings(self):
        for key, attrs in sorted(self.c.settings.items()):
            if key in self.lay.entities:
                for attr, value in attrs.items():
                    self.set(key, attr, value, "its instance")

    def gates(self):
        for net, cd in sorted(self.c.gates.items()):
            carriers = sorted((k for k, e in self.lay.entities.items()
                               if e.attrs.get("net") == net and self.kind(k) in _GATED),
                              key=fkpmod.natural_key)
            if not carriers:
                self.check("GATED", f"net {net}", f"gated ({cd.text}), but its route has no "
                           "inserter or pump to gate: it runs ungated")
                continue
            attr, value = cd.attr()
            for k in carriers:
                if self.set(k, attr, value, f"net {net}") and cd.wire:
                    self.join(cd.wire, k)
            self.lines.append(f"gated net {net}: {len(carriers)} carrier"
                              f"{'s' if len(carriers) != 1 else ''} {attr}={value}"
                              + (f" on {cd.wire}" if cd.wire else ""))

    def enables(self):
        for path, cd in sorted(self.c.enables.items()):
            attr, value = cd.attr()
            for key in self.flat.insts[path].machines:
                if key not in self.lay.entities:
                    continue
                if self.kind(key) not in _ENABLE:
                    self.check("CIRCUIT", path, f"when {cd.text}: a {self.lay.entities[key].name} "
                               "has no enable condition")
                    continue
                if self.set(key, attr, value, f"{path} when") and cd.wire:
                    self.join(cd.wire, key)
            self.lines.append(f"{path}: {attr}={value}" + (f" on {cd.wire}" if cd.wire else ""))

    def limits(self):
        for path, kind, n in self.c.limits:
            inst = self.flat.insts[path]
            done, onto_belt, shared = [], 0, set()
            for key in inst.machines:
                makes = self.flat.machines[key].makes
                for ins, dst in self.hops_out(key):
                    net = self.lay.entities[ins].attrs.get("net")
                    items = [i for i in makes if net in self.flat.nets
                             and i in self.flat.nets[net].items] or list(makes)
                    item = items[0]
                    if dst is not None and self.store(dst):
                        target = "chest"
                    elif dst is not None and self.kind(dst) in ("transport-belt", "splitter",
                                                                "underground-belt"):
                        net_ = self.flat.nets.get(net)
                        if net_ is None or not any(self.store(k) for k, _i in net_.consumers):
                            continue
                        target = "belt"
                        shared |= {self.flat.machines[k].inst for k, _i in net_.consumers
                                   if not self.store(k)}
                    else:
                        continue
                    if kind == "fill":
                        if target == "belt":
                            onto_belt += 1
                            continue
                        chest = self.flat.machines[dst].inst
                        wire = IMPLICIT.format(chest)
                        if wire not in self.wires:
                            self.wires[wire] = WireDef(wire, "red", [("machine", dst)],
                                                       implicit=True)
                        if self.set(ins, "if", f"{item}<{n}", f"{path} fill={n}"):
                            self.join(wire, dst)
                            self.join(wire, ins)
                            done.append(ins)
                    elif self.set(ins, "logistic", f"{item}<{n}", f"{path} keep={n}"):
                        done.append(ins)
            what = (f"the logistic network holds fewer than {n}" if kind == "keep"
                    else f"the chest holds fewer than {n}")
            if done:
                self.lines.append(f"{path} {kind}={n}: {len(done)} inserter"
                                  f"{'s run' if len(done) != 1 else ' runs'} while {what} "
                                  f"({', '.join(done[:4])}{' ...' if len(done) > 4 else ''})")
            if kind == "fill" and onto_belt:
                self.check("LIMIT", path, f"fill={n}: {onto_belt} of its inserters drop onto a "
                           "belt, not into a chest, so there is no chest to count; keep= counts "
                           "the logistic network")
            elif not done:
                self.check("LIMIT", path, f"{kind}={n}: no inserter takes its product into a chest "
                           "(straight in, or onto the belt of a net that ends in a chest), so "
                           "nothing is limited")
            if kind == "keep" and shared and done:
                self.lines.append(f"  {path} keep={n} also holds back what its belt carries to "
                                  f"{', '.join(sorted(shared))}")

    def guards(self):
        for path in self.c.guards:
            wire = IMPLICIT.format(path)
            hands, plain = 0, []
            for key in self.flat.insts[path].machines:
                if key not in self.lay.entities:
                    continue
                for ins in self.hops_in(key):
                    if self.lay.entities[ins].name not in FILTER_HANDS:
                        plain.append(ins)
                        continue
                    if self.set(ins, "filter", "circuit", f"{path} guard"):
                        self.join(wire, key)
                        self.join(wire, ins)
                        hands += 1
            self.lines.append(f"{path} guard: {hands} input inserter"
                              + ("s carry" if hands != 1 else " carries")
                              + " only what its recipe takes (filters from its ingredients)")
            if plain:
                self.check("GUARD", path, f"{', '.join(plain)}: a "
                           f"{self.lay.entities[plain[0]].name} can't filter; a fast inserter "
                           "can (the router's default hand)")

    def explicit(self):
        """The declared wires' members: their machines, the gated nets' carriers (joined by
        ``gates``), a driving net's belt."""
        for name, w in sorted(self.wires.items()):
            for side in (w.drivers, w.consumers):
                for kind, ref in side:
                    if kind == "machine" and ref in self.lay.entities:
                        self.join(name, ref)
            for kind, ref in w.drivers:
                if kind != "net":
                    continue
                belt = self.reader(ref, name)
                if belt is None:
                    self.check("WIRE", f"wire {name}", f"net {ref} has no belt to read")
                elif self.set(belt, "read", "hold", f"wire {name}"):
                    self.join(name, belt)

    def reader(self, net, wire):
        belts = [e for e in self.lay.entities.values()
                 if e.attrs.get("net") == net and self.kind(e.key) == "transport-belt"]
        if not belts:
            return None
        others = [self.lay.entities[k] for k, _p in self.members.get(wire, ())]
        if not others:
            return min(belts, key=lambda e: fkpmod.natural_key(e.key)).key
        return min(belts, key=lambda e: (min(_distance(e, o) for o in others),
                                         fkpmod.natural_key(e.key))).key

    def wire_up(self):
        for name in sorted(self.members, key=fkpmod.natural_key):
            ends = self.members[name]
            w = self.wires.get(name)
            colour = w.colour if w is not None else "red"
            if len(ends) < 2:
                continue
            self.lay.wirenets[name] = fkpmod.WireNet(name, colour)
            edges = []
            for i in range(len(ends)):
                for j in range(i + 1, len(ends)):
                    a, b = self.lay.entities[ends[i][0]], self.lay.entities[ends[j][0]]
                    edges.append((round(_distance(a, b), 6), fkpmod.natural_key(a.key),
                                  fkpmod.natural_key(b.key), i, j))
            edges.sort()
            parent = list(range(len(ends)))

            def find(k):
                while parent[k] != k:
                    parent[k] = parent[parent[k]]
                    k = parent[k]
                return k
            laid = 0
            for d, _ka, _kb, i, j in edges:
                ri, rj = find(i), find(j)
                if ri == rj:
                    continue
                parent[max(ri, rj)] = min(ri, rj)
                a, b = ends[i][0], ends[j][0]
                reach = min(self.cat.circuit_reach(self.lay.entities[a].name),
                            self.cat.circuit_reach(self.lay.entities[b].name))
                if d > reach + 1e-9:
                    self.check("WIRE_REACH", f"wire {name}", f"{a} to {b} is {d:.1f} tiles; a "
                               f"wire reaches {reach:g}: move them closer, or put a pole between")
                self.lay.wires.append(fkpmod.Wire(name, colour, a, b).canonical())
                laid += 1
            if w is not None and not w.implicit:
                self.lines.append(f"wire {name} {colour}: {len(ends)} entities, {laid} wire"
                                  f"{'s' if laid != 1 else ''}")
        self.lay.wires = fkpmod.sort_wires(self.lay.wires)

    def leaks(self):
        """``WIRE_LEAK``: two wire nets of one colour on one entity are one network in the game,
        so their signals add; a line when a consumer would see a driver its net doesn't have."""
        touch = {}
        for w in self.lay.wires:
            for end in (w.a, w.b):
                touch.setdefault((fkpmod.split_end(end)[0], w.colour), set()).add(w.net)
        drivers = {}
        for name, w in self.wires.items():
            drivers[name] = {ref for kind, ref in w.drivers if kind == "machine"}
        for (key, colour), nets in sorted(touch.items()):
            if len(nets) < 2:
                continue
            union = set().union(*(drivers.get(n, set()) for n in nets))
            if any(drivers.get(n, set()) != union for n in nets):
                self.check("WIRE_LEAK", key, f"the {colour} wires of {', '.join(sorted(nets))} "
                           "meet here, so they are one network and their signals add; give one "
                           "of them the other colour")


def lay(flat, layout, cat):
    """``layout`` (not changed) with the factory's circuits laid from its source: a new Layout,
    report lines and check lines. Every circuit setting and wire record is written again from
    the source, so a changed limit reaches the .fkp (and the next paste) on the next build; a
    Literal keeps its own settings (``config``) and wires."""
    import copy
    out = copy.deepcopy(layout)
    literal = {path for path, inst in flat.insts.items() if inst.kind == "Literal"}
    for e in out.entities.values():
        if e.owner in literal or any(e.owner.startswith(p + "/") for p in literal):
            continue
        for attr in codec.CIRCUIT_ATTRS:
            e.attrs.pop(attr, None)
    out.wirenets, out.wires = {}, []
    c = getattr(flat, "circuit", None)
    if c is None or c.empty:
        return out, [], []
    L = _Layer(flat, out, cat)
    L.machine_settings()
    L.gates()
    L.enables()
    L.limits()
    L.guards()
    L.explicit()
    L.wire_up()
    L.leaks()
    return out, c.notes + L.lines, L.checks
