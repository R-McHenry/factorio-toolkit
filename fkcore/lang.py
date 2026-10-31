"""fkcore.lang: tokenizer and parser for V1 factory source (.fk). Grammar: CORE.md "`.fk`".

    file    := (import | module | kind | 'size' WxH | stmt)*   # the top level is the factory body
    import  := 'import' Name (',' Name)* 'from' STRING     # a module or a kind of that file
    kind    := 'kind' Name '=' Kind ('<' param (',' param)* '>')?   # a name with defaults (2.1)
    tiers   := 'tiers' Name ':' word (',' word)*        # what machine=auto may pick (2.1)
    module  := 'module' Name ('size' WxH)? '{' stmt* '}'
    stmt    := inst | net | lanes | assert | cover | signal | wire | behave | expect | set | port
    port    := 'port' name ':' ('in' | 'out' | 'inout') items ('|' items)? '@' side (pos)? (lane)?
    inst    := name '=' Kind ('<' param (',' param)* '>')? hint* place ('when' cond)?
    place   := 'size' WxH | 'gap' num | 'retired' | 'temporary' [until ...] | hint   # its own line
    hint    := '@' '(' num ',' num (',' 'rot' num)? ')' | '@' 'patch' '(' word | STRING ')'
    net     := 'net' name ('items' item (',' item)*)? ('width' num)? ('lane' ('L' | 'R'))?
               'split'? 'limited'? ':' refs '->' refs ('when' cond)?
    lanes   := 'lanes' name '|' name    # two nets share every belt: left lane | right lane
    refs    := ref (',' ref)*          ref := name ('.' name)* ('.' '*')?
    assert  := 'assert' ref '.rate' op number '/' ('s' | 'min' | 'h')
    cover   := ('power' | 'robots') name ':' 'cover' ('all' | refs) (',' param)*
    param   := name '=' value | name                    # a bare name is a flag (Chest<provider>)
    value   := number ('/' unit)? | word ('|' word)* | STRING | 'auto' (number '..' number)?
    signal  := 'signal' name ('=' word)?                # pinned to a game signal, or auto
    wire    := 'wire' name ('red' | 'green') ':' refs ('->' refs)?
    cond    := operand op (operand | number)       op := '<' | '>' | '<=' | '>=' | '=' | '==' | '!='
    operand := name ('.' word)+                         # the last word is the signal
    behave  := 'behave' name 'on' name '{' line* '}'    # state | require | expect | cycle | fails
    expect  := 'expect' <the rest of the line>

The tokenizer is the one in C:\\fk-lead\\repo\\fkc\\lang.py (d6018d3), with ``*`` added for ``X.*``.
Words may contain dashes (item names); instance, module and net names may not. Every node keeps its
source line. ``n=auto`` (1.6) is a row count the build's ``size`` step chooses (``fkcore.size``):
an :class:`Auto`, ``auto LO..HI`` within those bounds. ``limited`` on a net (1.7, Rory 2026-10-21)
says the source limits what each maker puts on it: it silences the mixed-belt advice (``CLOG``)
and implements no limit. ``lanes A | B`` (2.0, Rory 2026-10-21: a net is one lane, so two nets can
share a belt) says nets A and B share every belt they are on, A on the left lane and B on the
right looking downstream: the router lays them as one pair (``fkcore.pairs``). ``split`` on a net
(2.0.76) gives each of its items a lane of its own: elaboration makes it one net per item and pairs
them two to a belt, each loaded by its own inserter filtered to its item.

Ports (2.0.28, lane-level in 2.0.29; PLAN-MODULES): a module body may declare
``port NAME : in|out|inout ITEM[, ITEM][ | ITEM[, ITEM]] @SIDE[POS][L|R]``, and the definition may
give ``size WxH``. A port is **a lane**, not a belt: its identity is the belt end's tile, direction
and lane (L or R looking downstream, as ``fkcore.lanes`` names them), so one tile and direction can
hold two ports, and ``A | B`` declares that pair (left = A, right = B, as ``lanes A | B``). A module
with ports is **sealed**: the nets written in its body are local, its only endpoints for the rest of
the design are its ports, and a ref that reaches past them (``gears.gears`` from outside) is refused
at elaboration. A module without ports is exactly as before, which is what every existing ``.fk``
is. Inside the body a port is an ordinary net endpoint (``net fe: iron -> gears``); outside it is the
module's endpoint (``net fe: bus -> gears.iron``), so one net in the source is one net that meets
itself at the port. ``@SIDE`` is ``n``, ``e``, ``s`` or ``w`` of the module's frame; ``@w4`` pins the
tile along that edge and ``@w4L`` its lane (without them the build chooses, facing the port's
partner).

Kinds (2.1, PLAN-2.1 "B. kind"): ``kind NAME = KIND<params>`` at a file's top level names an
existing kind (a core kind such as ``Machine``, a module, or another kind) with some parameters
set. An instance's own parameters override the kind's, and the instance keeps its own name. The
everyday kinds (``Assembler``, ``Furnace``, ``ChemPlant``, ``Refinery``) are declared this way in
the prelude (``fkcore/prelude.fk``, or a run's ``game/prelude.fk``), which every file gets without
an import (``fkcore.elaborate``); a file's own kind or module of the same name wins over it.
``tiers NAME: E1, E2, ...`` (2.1, "C. tiers") lists the entities ``machine=auto`` may pick for an
instance of kind NAME (or of a kind built on it): one footprint, one energy, one set of fluid boxes,
which elaboration checks.

The world design (2.0.43, PLAN-GLOBAL phase B): **a file's body is a module**, so
``import Outpost from "outpost.fk"`` needs no wrapping when ``outpost.fk`` declares no ``Outpost``
module; a top-level ``size WxH`` line is that body's frame. An instance line carries its placement
after the hints, on the same source line: ``size WxH`` (the frame of a sealed instance: what a plot
gets from its placement), ``gap N`` (tiles kept free around it for the root's routes), ``retired``
| ``temporary [until ...]`` (the lifecycles a surface ``place`` line has) and further ``@`` hints,
in any order. ``fkcore.root`` reads them into a surface's plot list.

Circuits (2.0, Rory 2026-10-21: "circuit wiring in the source, with all circuit and logic
conditions in the .fk code"; the draft is drafts\\reactor-1.1\\CIRCUITS-1.1.md): ``signal`` names a
game signal (``signal temp = signal-T``) or leaves it to the build; ``wire`` is a net of signals,
one colour; ``when`` gates a net (every inserter of its route) or enables a machine. A condition's
operand is ``W.S`` (signal S on wire W), ``network.S`` (the logistic network's count) or ``I.S``
(what instance I puts on a wire). ``behave`` and ``expect`` keep their lines as written, by line:
the tokenizer drops newlines, so a line is the tokens that share a line number. The circuit
meaning is ``fkcore.circuits``. Pure, stdlib only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["FkSyntaxError", "tokenize", "parse", "Ref", "Inst", "Net", "Lanes", "Assert", "Cover",
           "Module", "Port", "File", "Auto", "AUTO_TOP", "Signal", "Wire", "Cond", "Operand",
           "Behave", "Expect", "Props", "COMPARATORS", "Kind", "Tiers"]


class FkSyntaxError(Exception):
    def __init__(self, path, line, msg):
        super().__init__(f"{path}:{line}: {msg}")
        self.path, self.line, self.msg = path, line, msg


_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r]+) | (?P<nl>\n) | (?P<comment>\#[^\n]*)
  | (?P<string>"[^"\n]*")
  | (?P<dim>\d+x\d+)(?![A-Za-z0-9_])
  | (?P<num>-?\d+(?:\.\d+)?(?![A-Za-z_\-]))
  | (?P<op>->|>=|<=|==|!=|[{}()\[\]<>,:=|@./*])
  | (?P<word>[A-Za-z_](?:[A-Za-z0-9_]|-(?!>))*)
""", re.X)

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNITS = {"s": 1.0, "min": 60.0, "h": 3600.0}
_COVER_KINDS = ("power", "robots")
_COLOURS = ("red", "green")
#: a condition's comparators as written in the source (``==`` is ``=``)
COMPARATORS = ("<", ">", "<=", ">=", "=", "!=")
_BEHAVE = ("state", "require", "expect", "cycle", "fails")
#: the top of a plain ``n=auto``: a bound that never stops a real design, only a runaway one
AUTO_TOP = 100


@dataclass
class Tok:
    kind: str
    text: str
    line: int


def tokenize(text, path="<fk>"):
    toks, line, pos = [], 1, 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise FkSyntaxError(path, line, f"unexpected character {text[pos]!r}")
        kind = m.lastgroup
        if kind == "nl":
            line += 1
        elif kind not in ("ws", "comment"):
            toks.append(Tok(kind, m.group(), line))
        pos = m.end()
    toks.append(Tok("eof", "", line))
    return toks


# -- AST ------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Auto:
    """``n=auto`` or ``n=auto LO..HI``: a count the build's ``size`` step chooses, the fewest
    machines that meet the targets, the asserts and what the row's consumers ask."""
    lo: int = 1
    hi: int | None = None          # None: AUTO_TOP

    @property
    def top(self):
        return AUTO_TOP if self.hi is None else self.hi

    def __str__(self):
        return "auto" if self.hi is None and self.lo == 1 else f"auto {self.lo}..{self.top}"


@dataclass
class Ref:
    parts: list          # ["mall", "belts"]
    star: bool           # X.* : X's free endpoints
    line: int

    def __str__(self):
        return ".".join(self.parts) + (".*" if self.star else "")


@dataclass
class Operand:
    """``W.S``, ``network.S`` or ``I.S``: ``source`` is everything before the last dot."""
    source: list         # ["fuel_ctl"], ["network"], ["iron", "box"]
    signal: str          # "temp", "signal-T", "iron-plate"

    def __str__(self):
        return ".".join(self.source + [self.signal])


@dataclass
class Cond:
    left: Operand
    op: str              # one of COMPARATORS
    right: object        # Operand or a number
    line: int

    def __str__(self):
        return f"{self.left} {self.op} {self.right}"


@dataclass
class Inst:
    name: str
    kind: str
    params: dict
    hints: dict
    line: int
    when: Cond | None = None   # the machine's own enable condition
    conns: list | None = None  # [(name, Ref, kind)]: a Bus's connection list, in port order
    size: tuple | None = None  # a module instance's frame from its own line (2.0.43): (W, H)
    gap: int = 0               # tiles kept free around it, for the root's routes (2.0.43)
    lifecycle: str | None = None   # "retired" | "temporary ..." on the instance line (2.0.43)


@dataclass
class Net:
    name: str
    items: list | None   # declared items, or None (inferred from the drivers)
    drivers: list        # [Ref]
    consumers: list      # [Ref]
    line: int
    limited: bool = False  # the source says each maker on it is limited (silences CLOG only)
    when: Cond | None = None   # a gated net: its route's inserters move items while it holds
    width: int = 1         # 2.0.54: the lanes it takes, 1 or 2 (both lanes of one belt)
    lane: str | None = None    # 2.0.54: the lane (L or R) its items are on where it ends
    split: bool = False    # 2.0.76: one net per item, two to a belt (a lane each)


@dataclass
class Signal:
    name: str
    game: str | None     # the pinned game signal, or None: the build picks one
    line: int


@dataclass
class Wire:
    name: str
    colour: str          # "red" | "green"
    drivers: list        # [Ref]: instances that put signals on it (a net: its belt reads)
    consumers: list      # [Ref]: instances or gated nets that read it
    line: int


@dataclass
class Behave:
    """A control loop's states and what is normal in each, as written (CIRCUITS-1.1.md §4)."""
    name: str
    wire: str
    lines: list          # [(kind, text, line)], kind one of state, require, expect, cycle, fails
    line: int


@dataclass
class Expect:
    text: str
    line: int


@dataclass
class Lanes:
    left: str            # the net on the left lane, looking downstream
    right: str           # the net on the right lane
    line: int


@dataclass
class Assert:
    ref: Ref
    op: str
    rate: float          # items/s
    line: int


@dataclass
class Cover:
    kind: str            # "power" | "robots"
    name: str
    targets: list | None  # None = all
    params: dict
    line: int


@dataclass
class Module:
    name: str
    line: int
    insts: list = field(default_factory=list)
    nets: list = field(default_factory=list)
    asserts: list = field(default_factory=list)
    covers: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    wires: list = field(default_factory=list)
    behaves: list = field(default_factory=list)
    expects: list = field(default_factory=list)
    lanes: list = field(default_factory=list)      # [Lanes]: two nets that share a belt
    sets: list = field(default_factory=list)       # [Props]: properties on named objects (2.0.27)
    ports: list = field(default_factory=list)      # [Port]: the module's interface (2.0.28)
    size: tuple | None = None                      # (W, H) of its frame as written, or None
    stacks: list = field(default_factory=list)     # [(near, far, line)]: stack pairs (2.0.48)
    dnps: list = field(default_factory=list)       # [Ref]: `dnp A, B.c` (2.0.63), do not populate


@dataclass
class Port:
    """A port declaration (2.0.28, PLAN-MODULES; lane-level in 2.0.29): a port is a **lane** of a
    belt end, so ``(side, pos, lane)``. ``items`` is the left lane's items, ``right`` the right
    lane's when the declaration is the pair ``A | B`` (``items`` is then the left lane, and the same
    item on both lanes is one item on both lanes: V1's ``Belt[item]``); ``lane`` is the pinned lane of a
    one-lane port (``@s4L``), or None: the build chooses it facing the partner."""
    name: str
    dir: str             # "in" | "out" | "inout"
    items: list          # the left lane's items (several: a mixed lane)
    side: str            # "n" | "e" | "s" | "w"
    pos: int | None
    line: int
    lane: str | None = None    # "L" | "R" of a one-lane port, or None
    right: list | None = None  # the right lane's items: the port is the pair ``A | B``

    @property
    def all_items(self):
        return list(self.items) + list(self.right or ())


@dataclass
class Props:
    """``set SEL: attr=value, ...`` (2.0.27, Rory 2026-10-25): a property on the objects a selector
    names. ``SEL`` is an instance (its machines), ``NAME.out`` / ``NAME.in`` (its hands), narrowed
    by ``-> NAME`` (the hand whose sink is that instance), as in
    ``set insm.out -> ibox: logistic=inserter<1000``."""
    target: str
    side: str | None          # None: the instance's machines; "out" / "in": its hands
    into: str | None          # the sink instance a hand must feed (``-> NAME``), or None
    attrs: dict               # attr -> value as written (a string; codec parses it)
    line: int
    wire: str | None = None   # the chest whose contents an ``if=`` reads (a lowered ``fill=``)


@dataclass
class Kind:
    """``kind NAME = TARGET<params>`` (2.1): TARGET with ``params`` set. ``path`` is the file it
    is declared in (its errors name it)."""
    name: str
    target: str
    params: dict
    line: int
    path: str = "<fk>"


@dataclass
class Tiers:
    """``tiers NAME: E1, E2, ...`` (2.1): the entities ``machine=auto`` picks from for kind NAME,
    in order (the first is the default pick)."""
    name: str
    entities: list
    line: int
    path: str = "<fk>"


@dataclass
class File:
    path: str
    body: Module
    modules: dict = field(default_factory=dict)    # Name -> Module
    imports: list = field(default_factory=list)    # [(names, file, line)]
    kinds: dict = field(default_factory=dict)      # Name -> Kind (2.1)
    tiers: dict = field(default_factory=dict)      # Name -> Tiers (2.1)


# -- parser ---------------------------------------------------------------------------------------
class _P:
    def __init__(self, toks, path):
        self.t, self.i, self.path = toks, 0, path

    def peek(self, k=0):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def err(self, msg, tok=None):
        tok = tok or self.peek()
        raise FkSyntaxError(self.path, tok.line, msg)

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def accept(self, text):
        if self.peek().text == text and self.peek().kind in ("op", "word"):
            return self.next()
        return None

    def expect(self, text):
        tok = self.next()
        if tok.text != text:
            self.err(f"expected {text!r}, got {tok.text or tok.kind!r}", tok)
        return tok

    def word(self, what="name"):
        tok = self.next()
        if tok.kind != "word":
            self.err(f"expected {what}, got {tok.text or tok.kind!r}", tok)
        return tok

    def name(self, what="name"):
        tok = self.word(what)
        if not _NAME.match(tok.text):
            self.err(f"{what} {tok.text!r} may not contain dashes", tok)
        return tok

    def number(self):
        tok = self.next()
        if tok.kind != "num":
            self.err(f"expected a number, got {tok.text or tok.kind!r}", tok)
        v = float(tok.text)
        return int(v) if v.is_integer() and "." not in tok.text else v

    def rate(self):
        n = self.number()
        if self.accept("/"):
            unit = self.word("a rate unit (s, min, h)").text
            if unit not in _UNITS:
                self.err(f"unknown rate unit {unit!r}")
            return float(n) / _UNITS[unit]
        return n

    # stmt-level
    def file(self):
        body = Module("<factory>", 1)
        f = File(self.path, body)
        while self.peek().kind != "eof":
            tok = self.peek()
            if tok.text == "import" and tok.kind == "word":
                f.imports.append(self.import_())
            elif tok.text == "module" and tok.kind == "word":
                mod = self.module()
                if mod.name in f.modules:
                    self.err(f"module {mod.name} defined twice", tok)
                if mod.name in f.kinds:
                    self.err(f"{mod.name} is both a kind and a module: name one otherwise", tok)
                f.modules[mod.name] = mod
            elif self.at_kind():
                k = self.kind_decl()
                if k.name in f.kinds:
                    self.err(f"kind {k.name} defined twice", tok)
                if k.name in f.modules:
                    self.err(f"{k.name} is both a kind and a module: name one otherwise", tok)
                f.kinds[k.name] = k
            elif self.at_tiers():
                t = self.tiers_decl()
                if t.name in f.tiers:
                    self.err(f"tiers {t.name} written twice", tok)
                f.tiers[t.name] = t
            elif tok.text == "size" and tok.kind == "word" and self.peek(1).kind == "dim":
                # 2.0.43 (PLAN-GLOBAL phase B): a factory file's own frame, so a file body can be
                # imported as a module as it is; the root's placement may give one instead
                self.next()
                dim = self.next()
                w, h = (int(v) for v in dim.text.split("x"))
                if body.size is not None:
                    self.err("the file's size is written twice", dim)
                body.size = (w, h)
            else:
                self.stmt(body)
        if body.ports:
            p = body.ports[0]
            raise FkSyntaxError(self.path, p.line,
                                f"port {p.name}: a port is a module's interface; declare it inside "
                                "`module NAME { ... }`")
        return f

    def at_kind(self):
        """``kind NAME = ...`` (an instance named ``kind`` is ``kind = ...``)."""
        return (self.peek().text == "kind" and self.peek().kind == "word"
                and self.peek(1).kind == "word" and self.peek(2).text == "=")

    def kind_decl(self):
        """``kind NAME = TARGET<params>`` (2.1, PLAN-2.1 "B. kind")."""
        line = self.expect("kind").line
        name = self.name("kind name").text
        self.expect("=")
        target = self.name("a kind or module").text
        params = {}
        if self.accept("<"):
            if not self.accept(">"):
                while True:
                    k, v = self.param()
                    if k in params:
                        self.err(f"parameter {k} given twice")
                    params[k] = v
                    if self.accept(">"):
                        break
                    self.expect(",")
        if self.peek().kind != "eof" and self.peek().line == line:
            self.err(f"kind {name}: a kind line is `kind NAME = KIND<params>` and nothing more")
        return Kind(name, target, params, line, self.path)

    def at_tiers(self):
        """``tiers NAME: ...`` (an instance named ``tiers`` is ``tiers = ...``)."""
        return (self.peek().text == "tiers" and self.peek().kind == "word"
                and self.peek(1).kind == "word" and self.peek(2).text == ":")

    def tiers_decl(self):
        """``tiers NAME: E1, E2, ...`` (2.1, PLAN-2.1 "C. tiers")."""
        line = self.expect("tiers").line
        name = self.name("kind name").text
        self.expect(":")
        ents = [self.word("an entity").text]
        while self.accept(","):
            ents.append(self.word("an entity").text)
        if len(set(ents)) != len(ents):
            self.err(f"tiers {name}: an entity is listed twice")
        if self.peek().kind != "eof" and self.peek().line == line:
            self.err(f"tiers {name}: a tiers line is `tiers KIND: ENTITY, ENTITY, ...`")
        return Tiers(name, ents, line, self.path)

    def import_(self):
        line = self.expect("import").line
        names = [self.name("module name").text]
        while self.accept(","):
            names.append(self.name("module name").text)
        self.expect("from")
        tok = self.next()
        if tok.kind != "string":
            self.err("expected a file name in quotes", tok)
        return names, tok.text[1:-1], line

    def module(self):
        line = self.expect("module").line
        mod = Module(self.name("module name").text, line)
        if self.accept("size"):
            tok = self.peek()
            if tok.kind != "dim":
                self.err("a module's frame is written `size WxH`, like size 24x10", tok)
            self.next()
            w, h = (int(v) for v in tok.text.split("x"))
            if w < 1 or h < 1:
                self.err(f"size {tok.text}: a frame is at least 1x1", tok)
            mod.size = (w, h)
        self.expect("{")
        while not self.accept("}"):
            if self.peek().kind == "eof":
                self.err(f"module {mod.name} is not closed")
            self.stmt(mod)
        return mod

    def port(self):
        """``port NAME : in|out|inout ITEM[, ITEM][ | ITEM[, ITEM]] @SIDE[POS][L|R]`` (2.0.29,
        PLAN-MODULES): a port is **one lane** of a belt end, or the pair ``A | B`` = the two lanes
        of one belt end (left = A, right = B, as ``lanes A | B``)."""
        line = self.expect("port").line
        name = self.name("port name").text
        self.expect(":")
        direction = self.word("in, out or inout").text
        if direction not in ("in", "out", "inout"):
            self.err(f"a port carries items in, out or inout, got {direction!r}")
        left = [self.word("item").text]
        while self.accept(","):
            left.append(self.word("item").text)
        right = None
        if self.accept("|"):                 # the pair: what comes before it is the left lane
            right = [self.word("item").text]
            while self.accept(","):
                right.append(self.word("item").text)
        self.expect("@")
        tok = self.word("a side: n, e, s or w, with a tile along it like w4, and L or R")
        text, rest = tok.text, tok.text[1:]
        lane = rest[-1].upper() if rest and rest[-1] in "LRlr" else None
        if lane is not None:
            rest = rest[:-1]
        if text[0] not in "nesw" or (rest and not rest.isdigit()):
            self.err(f"{text}: a port's side is n, e, s or w, with its tile along that edge like "
                     "w4, and its lane like w4L (or neither: the build chooses them)", tok)
        if right is not None and lane is not None:
            self.err(f"port {name}: a pair is both lanes, so drop the {lane} and place it at "
                     f"{text[0]}{rest}", tok)
        return Port(name, direction, left, text[0], int(rest) if rest else None, line, lane, right)

    def stack_pairs(self):
        """``stack NEAR -> FAR[, NEAR -> FAR ...]`` (2.0.48, Rory 2026-10-26): the module is a cell
        that stacks in a line. NEAR is a port on the edge toward the stack's head, FAR the port on
        the opposite edge that meets the next cell's NEAR; the items flow whichever way the ports'
        own directions say (a feed head to tail, a product tail to head)."""
        line = self.expect("stack").line
        out = []
        while True:
            near = self.name("port name").text
            self.expect("->")
            far = self.name("port name").text
            out.append((near, far, line))
            if not self.accept(","):
                break
        return out

    def stmt(self, mod):
        tok = self.peek()
        if tok.kind != "word":
            self.err(f"expected a statement, got {tok.text or tok.kind!r}")
        if tok.text == "net" and self.peek(1).kind == "word":
            mod.nets.append(self.net())
        elif tok.text == "lanes" and self.peek(1).kind == "word":
            mod.lanes.append(self.lanes())
        elif tok.text == "assert":
            mod.asserts.append(self.assert_())
        elif tok.text in _COVER_KINDS and self.peek(1).kind == "word" and self.peek(2).text == ":":
            mod.covers.append(self.cover())
        elif tok.text == "signal" and self.peek(1).kind == "word":
            mod.signals.append(self.signal())
        elif tok.text == "wire" and self.peek(1).kind == "word" and self.peek(2).text in _COLOURS:
            mod.wires.append(self.wire())
        elif tok.text == "behave" and self.peek(1).kind == "word" and self.peek(2).text == "on":
            mod.behaves.append(self.behave())
        elif tok.text == "set" and self.peek(1).kind == "word":
            mod.sets.append(self.props())
        elif tok.text == "port" and self.peek(1).kind == "word":
            mod.ports.append(self.port())
        elif tok.text == "stack" and self.peek(1).kind == "word" and self.peek(2).text == "->":
            mod.stacks += self.stack_pairs()
        elif tok.text == "dnp" and self.peek(1).kind == "word":
            # 2.0.63 (Rory, 2026-10-29): `dnp NAME[, A.B ...]`, do not populate: laid out and routed
            # as ever, but not built, and nothing of it in the model
            self.next()
            mod.dnps += self.refs()
        elif tok.text == "expect" and self.peek(1).text != "=":
            mod.expects.append(self.expect_line())
        elif self.at_kind():
            self.err("a kind is declared at a file's top level, not inside a module")
        elif self.at_tiers():
            self.err("tiers are declared at a file's top level, not inside a module")
        elif self.peek(1).text == "=":
            mod.insts.append(self.inst())
        else:
            self.err(f"expected an instance, net, assert or cover, got {tok.text!r}")

    def rest_of_line(self, line):
        """The tokens left on source line ``line``, joined as written (one space between)."""
        out = []
        while self.peek().kind != "eof" and self.peek().line == line:
            out.append(self.next().text)
        text = " ".join(out)
        return re.sub(r" ?([.,:]) ?", lambda m: m.group(1) + (" " if m.group(1) != "." else ""),
                      text).strip()

    def props(self):
        """``set SEL: attr=value, ...`` (2.0.27, Rory 2026-10-25): SEL is NAME (its machines),
        NAME.out / NAME.in (its hands), narrowed by ``-> NAME`` (the hand whose sink is that)."""
        line = self.expect("set").line
        target = self.name("an instance name").text
        side = None
        if self.accept("."):
            side = self.word("out or in").text
            if side not in ("out", "in"):
                self.err(f"set names hands NAME.out or NAME.in, got .{side}")
        into = None
        if self.accept("->"):
            into = self.name("the instance a hand feeds").text
        self.expect(":")
        attrs = {}
        while True:
            key = self.word("a property: logistic, if, filter, read, signal or signals").text
            if key in attrs:
                self.err(f"property {key} given twice")
            self.expect("=")
            attrs[key] = self.prop_value(line)
            if not self.accept(","):
                break
        return Props(target, side, into, attrs, line)

    def prop_value(self, line):
        """A property value as written, without the spaces around ``<``, ``>`` and ``=``
        (``inserter < 1000`` -> ``inserter<1000``)."""
        out = []
        while self.peek().kind != "eof" and self.peek().line == line and self.peek().text != ",":
            out.append(self.next().text)
        return re.sub(r" ?([<>=]) ?", r"\1", " ".join(out)).strip()

    def signal(self):
        line = self.expect("signal").line
        name = self.name("signal name").text
        game = None
        if self.accept("="):
            game = self.word("a game signal (signal-T, iron-plate)").text
        return Signal(name, game, line)

    def wire(self):
        line = self.expect("wire").line
        name = self.name("wire name").text
        colour = self.next().text
        self.expect(":")
        drivers = self.refs()
        consumers = self.refs() if self.accept("->") else []
        return Wire(name, colour, drivers, consumers, line)

    def operand(self):
        tok = self.name("a wire, network or instance")
        parts = [tok.text]
        if self.peek().text != ".":
            self.err(f"a condition reads W.no-signal, network.ITEM or INSTANCE.no-signal, got "
                     f"{tok.text!r}", tok)
        while self.accept("."):
            parts.append(self.word("a signal").text)
        return Operand(parts[:-1], parts[-1])

    def cond(self):
        line = self.peek().line
        left = self.operand()
        op = self.next()
        text = "=" if op.text == "==" else op.text
        if text not in COMPARATORS:
            self.err(f"expected a comparison ({', '.join(COMPARATORS)}), got {op.text!r}", op)
        right = self.number() if self.peek().kind == "num" else self.operand()
        return Cond(left, text, right, line)

    def behave(self):
        line = self.expect("behave").line
        name = self.name("behave name").text
        self.expect("on")
        wire = self.name("wire name").text
        self.expect("{")
        lines = []
        while not self.accept("}"):
            tok = self.next()
            if tok.kind == "eof":
                self.err(f"behave {name} is not closed", tok)
            if tok.text not in _BEHAVE:
                self.err(f"a behave line starts with {', '.join(_BEHAVE)}, got {tok.text!r}", tok)
            lines.append((tok.text, self.rest_of_line(tok.line), tok.line))
        return Behave(name, wire, lines, line)

    def expect_line(self):
        tok = self.expect("expect")
        return Expect(self.rest_of_line(tok.line), tok.line)

    def ref(self):
        tok = self.name("instance name")
        parts, star = [tok.text], False
        while self.peek().text == ".":
            self.next()
            if self.accept("*"):
                star = True
                break
            parts.append(self.name("instance name").text)
        return Ref(parts, star, tok.line)

    def refs(self):
        out = [self.ref()]
        while self.peek().text == "," and self.peek(1).kind == "word" and self.peek(2).text != "=":
            self.next()
            out.append(self.ref())
        return out

    def net(self):
        line = self.expect("net").line
        name = self.name("net name").text
        items = None
        if self.accept("items"):
            items = [self.word("item").text]
            while self.accept(","):
                items.append(self.word("item").text)
        width = 1
        if self.accept("width"):
            tok = self.peek()
            width = self.number()
            if width not in (1, 2):
                self.err(f"width {width}: a net takes 1 lane or 2 (both lanes of a belt); "
                         "more is 2.1's buses", tok)
        lane = None
        if self.accept("lane"):
            tok = self.word("lane")
            if tok.text not in ("L", "R"):
                self.err(f"lane {tok.text}: a lane is L or R (looking downstream)", tok)
            lane = tok.text
        split = self.accept("split") is not None
        limited = self.accept("limited") is not None
        self.expect(":")
        drivers = self.refs()
        self.expect("->")
        consumers = self.refs()
        when = self.cond() if self.accept("when") else None
        return Net(name, items, drivers, consumers, line, limited, when, width, lane, split)

    def lanes(self):
        line = self.expect("lanes").line
        left = self.name("net name").text
        if not self.accept("|"):
            self.err("two nets share a belt as lanes LEFT | RIGHT, like lanes ore | fuel")
        right = self.name("net name").text
        if right == left:
            self.err(f"lanes {left} | {right}: a net is one lane; name two nets")
        return Lanes(left, right, line)

    def assert_(self):
        line = self.expect("assert").line
        ref = self.ref()
        if ref.star or len(ref.parts) < 2 or ref.parts[-1] != "rate":
            self.err("assert needs <instance or net>.rate", self.t[self.i - 1])
        ref.parts = ref.parts[:-1]
        op = self.next()
        if op.text not in (">=", "<=", ">", "<", "=="):
            self.err(f"expected a comparison, got {op.text!r}", op)
        return Assert(ref, op.text, float(self.rate()), line)

    def cover(self):
        tok = self.next()
        name = self.name("coverage name").text
        self.expect(":")
        self.expect("cover")
        targets = None
        if not self.accept("all"):
            targets = self.refs()
        params = {}
        while self.accept(","):
            k, v = self.param()
            params[k] = v
        return Cover(tok.text, name, targets, params, tok.line)

    def inst(self):
        tok = self.name("instance name")
        self.expect("=")
        kind = self.name("template or module").text
        params, hints = {}, {}
        if self.accept("<"):
            if not self.accept(">"):
                while True:
                    k, v = self.param()
                    if k in params:
                        self.err(f"parameter {k} given twice")
                    params[k] = v
                    if self.accept(">"):
                        break
                    self.expect(",")
        conns = None
        if self.accept("("):                     # a Bus's connection list (2.0.32): name: ref, in order
            conns = []
            if not self.accept(")"):
                while True:
                    ckind = None
                    if (self.peek().text in ("dual", "left", "right")
                            and self.peek(2).text == ":"):   # left fg: rib.iron, not fg: left.thing
                        ckind = self.next().text
                    cname = self.name("a connection name").text
                    self.expect(":")
                    cref = self.ref()
                    if any(n == cname for n, _r, _k in conns):
                        self.err(f"connection {cname} given twice")
                    conns.append((cname, cref, ckind))
                    if self.accept(")"):
                        break
                    self.expect(",")
        while self.peek().text == "@":
            self.hint(hints)
        when = self.cond() if self.accept("when") else None
        size, gap, lifecycle = self.placement(tok.line, hints)
        return Inst(tok.text, kind, params, hints, tok.line, when, conns, size, gap, lifecycle)

    def hint(self, hints):
        """One ``@`` hint: ``@(x, y[, rot r])`` or ``@patch(resource)`` (a resource may be written
        as a string, so a patch number survives: ``@patch("iron-ore#2")``, 2.0.43)."""
        self.expect("@")
        if self.accept("patch"):
            self.expect("(")
            tok = self.next()
            if tok.kind not in ("word", "string"):
                self.err('expected a resource, or "resource#n" in quotes', tok)
            hints["patch"] = tok.text[1:-1] if tok.kind == "string" else tok.text
            self.expect(")")
            return
        self.expect("(")
        x = self.number()
        self.expect(",")
        y = self.number()
        rot = 0
        if self.accept(","):
            self.expect("rot")
            rot = self.number()
        self.expect(")")
        hints["at"] = (x, y, rot)

    def placement(self, line, hints):
        """The placement extras on an instance's own source line (2.0.43, PLAN-GLOBAL phase B):
        ``size WxH`` (the frame of a sealed instance: a plot's), ``gap N`` (tiles kept free around
        it for the root's routes), ``retired`` | ``temporary [until ...]`` (the lifecycles a
        surface ``place`` line has) and any ``@`` hint, in any order. They are that line's own
        words, so a statement on the next line — even one starting with ``size`` — is still read
        as a statement."""
        size, gap, lifecycle = None, 0, None
        while self.peek().line == line:
            word = self.peek().text
            if word == "@":
                self.hint(hints)
            elif word == "size" and self.peek(1).kind == "dim":
                self.next()
                dim = self.next()
                w, h = (int(v) for v in dim.text.split("x"))
                if w < 1 or h < 1:
                    self.err(f"size {dim.text}: a frame is at least 1x1", dim)
                size = (w, h)
            elif word == "gap" and self.peek(1).kind == "num":
                self.next()
                gap = self.number()
                if not isinstance(gap, int) or gap < 0:
                    self.err(f"gap {gap}: whole tiles, 0 or more")
            elif word == "retired":
                self.next()
                lifecycle = "retired"
            elif word == "temporary":
                self.next()
                rest = self.rest_of_line(line)
                lifecycle = ("temporary " + rest) if rest else "temporary"
            else:
                break
        return size, gap, lifecycle

    def param(self):
        key = self.name("parameter").text
        if not self.accept("="):
            return key, True
        tok = self.peek()
        if tok.kind == "num":
            return key, self.rate()
        if tok.kind == "string":
            self.next()
            return key, tok.text[1:-1]
        words = [self.word("value").text]
        if words[0] == "auto" and self.peek().text != "|":
            return key, self.auto()
        while self.accept("|"):
            words.append(self.word("value").text)
        return key, words[0] if len(words) == 1 else words

    def auto(self):
        """What follows ``auto``: nothing, or the bounds ``LO..HI``."""
        tok = self.peek()
        if tok.kind != "num":
            return Auto()
        lo = self.number()
        if not (self.accept(".") and self.accept(".")) or self.peek().kind != "num":
            self.err("a count's bounds are written auto LO..HI, like auto 1..30", tok)
        hi = self.number()
        if not (isinstance(lo, int) and isinstance(hi, int) and 1 <= lo <= hi):
            self.err(f"auto {lo}..{hi}: the bounds are whole numbers, 1 <= LO <= HI", tok)
        return Auto(lo, hi)


def parse(text, path="<fk>") -> File:
    return _P(tokenize(text, path), path).file()
