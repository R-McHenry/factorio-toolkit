"""fkcore.avail: what the factory can build now, for a tier a design leaves to the toolkit.

A design or a build script may name a *family* instead of one prototype: ``inserter=any`` on an
instance, ``route --hand any``, ``cover power --pole any``, ``floorplan --bridge-power any``
(``auto`` and ``whatever`` say the same). :func:`choose` answers with one prototype of that family:

1. the best one **robots can build now** (``supply.ghost_state``: the network holds as many as the
   design needs, so no ghost stalls), best first;
2. else the best one that is not LOCKED (it can be made; SHORT says how far off it is);
3. else the family's default, with the reason (the design's norm, as before: a fast inserter; a
   blind pick, and the note says so).

Best first is the tier Rory asks for where it is affordable: a fast inserter over a plain one, a
medium pole over a small one. So ``any`` moves a design up by itself once the network holds the
better tier, and never lays a ghost the network cannot build. That is the 2026-10-25 run: 4 fast
inserters pasted LOCKED (research at 81%, none in the network) while 50 plain inserters sat in the
kit, and the burner row they fueled stood dead; the same run's script had to say ``--hand inserter``
by hand to get plain ones everywhere.

The read is the snapshot ``out/avail.json``. A play build designs on the laptop, where there is no
game link (``agent/fk.py`` splits the script at ``diff``), so a host step writes it: ``report_bom
--stock live`` every build, and ``fk avail --save`` before the first one. Like ``out/force.json``
it is the last read, and every choice's note says what it saw.

Pure apart from one snapshot per process (:func:`use`), as ``route``'s ``--hand`` is.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import supply

__all__ = ["HANDS", "POLES", "FAMILIES", "DEFAULT", "ANY", "CANDIDATES", "Snapshot", "is_any",
           "buildable", "choose", "drain", "install", "load", "save", "snapshot", "use"]

#: short hands, best first: a fast inserter where the network can build one, else a plain one
HANDS = ("fast-inserter", "inserter")
#: coverage poles, best first: the biggest supply area a 1x1 pole has, then the cheapest. A big pole
#: and a substation are 2x2 and are not coverage poles: ``--pole`` names them by hand.
POLES = ("medium-electric-pole", "small-electric-pole")
FAMILIES = {"hand": HANDS, "pole": POLES}
#: what ``any`` is when nothing was read at all: the design's own norm, exactly what the toolkit
#: laid before it could tell (a fast inserter, a medium pole), and the note says it is blind. A run
#: always has a read (``report_bom --stock live``, and the wrapper's ``fk avail --save`` before the
#: first build); a lab or a rate report has none, and must not silently get the slow tier either.
DEFAULT = {"hand": "fast-inserter", "pole": "medium-electric-pole"}
#: the words that ask for a family
ANY = frozenset({"any", "auto", "whatever"})
#: what one snapshot reads: every prototype a family may choose
CANDIDATES = tuple(dict.fromkeys(HANDS + POLES))
_FILE = "avail.json"


def is_any(word):
    """True for the words that ask for a family instead of a prototype (``any``, ``auto``)."""
    return isinstance(word, str) and word.strip().lower() in ANY


@dataclass
class Snapshot:
    """The last read of what the game can build: a :class:`fkcore.supply.Supply`, and when."""
    sup: object = None                    # fkcore.supply.Supply, or None: never read
    tick: int = 0
    when: str = ""

    def known(self, name):
        return self.sup is not None and name in self.sup.entities


_snapshot = Snapshot()
_notes = []


def snapshot():
    """The snapshot this process uses (empty when nothing was read)."""
    return _snapshot


def install(sup, when="", tick=0):
    """Use ``sup`` as this process's snapshot (``report_bom --stock live`` and ``fk avail``)."""
    global _snapshot
    _snapshot = Snapshot(sup, int(tick or getattr(sup, "tick", 0) or 0), str(when))
    return _snapshot


def load(root):
    """The snapshot in ``<root>/out/avail.json``, else an empty one."""
    try:
        with open(os.path.join(root, "out", _FILE), encoding="utf-8") as fh:
            raw = json.load(fh)
        return Snapshot(supply.from_raw(raw), int(raw.get("tick") or 0), str(raw.get("when") or ""))
    except (OSError, ValueError, TypeError, KeyError):
        return Snapshot()


def use(root):
    """Read ``<root>/out/avail.json`` into this process's snapshot; -> the snapshot."""
    global _snapshot
    _snapshot = load(root)
    return _snapshot


def save(root, sup, when=""):
    """Write ``sup`` as ``<root>/out/avail.json`` (what a later, linkless build reads), and make it
    this process's snapshot. -> the path."""
    raw = {"tick": sup.tick, "force": sup.force, "surface": sup.surface, "networks": sup.networks,
           "when": when, "entities": list(sup.entities.values()),
           "recipes": list(sup.recipes.values()), "research": sup.research}
    out = os.path.join(root, "out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, _FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(raw, fh, indent=0, sort_keys=True)
        fh.write("\n")
    install(sup, when, sup.tick)
    return path


def choose(family, name=None, need=1):
    """(prototype, note) for ``name``: as given when it names one, else the family's choice now.

    ``need``: how many of them the design wants, so a tier the network holds only one or two of is
    not chosen for forty (that is a SHORT ghost rather than a LOCKED one, and no better). The note
    is None for a name given, and one report line for a choice (it goes to the build log once).
    """
    if family not in FAMILIES:
        raise ValueError(f"avail: family is one of {', '.join(sorted(FAMILIES))}, got {family!r}")
    if not is_any(name):
        return name, None
    names = FAMILIES[family]
    need = max(int(need or 1), 1)
    snap = _snapshot
    if snap.sup is None:
        got = DEFAULT[family]
        return got, _say(f"{family}=any: {got} (no stock read yet: out/{_FILE} comes from the game "
                         f"host, by report_bom --stock live or fk avail --save)")
    unread, short, locked = [], [], []
    for got in names:
        if not snap.known(got):
            unread.append(got)
            continue
        state, why = supply.ghost_state(snap.sup, got, need)
        if state is None:
            return got, _say(f"{family}=any: {got} ({why})")
        (locked if state == "LOCKED" else short).append((got, why))
    if short:
        got, why = short[0]
        return got, _say(f"{family}=any: {got} (SHORT, so it can be made: {why})")
    if locked:
        got, why = locked[0]
        return got, _say(f"{family}=any: {got} (LOCKED: {why})")
    got = DEFAULT[family]
    return got, _say(f"{family}=any: {got} (not read: {', '.join(unread)}; report_bom --stock live "
                     f"writes out/{_FILE})")


def buildable(name, need=1):
    """True when robots can build ``name`` now (SHORT or LOCKED is False; nothing read: False):
    what a standing route's inserter is judged by before it is given another hand."""
    snap = _snapshot
    if snap.sup is None or not snap.known(name):
        return False
    return supply.ghost_state(snap.sup, name, max(int(need or 1), 1))[0] is None


def _say(line):
    if line not in _notes:
        _notes.append(line)
    return line


def drain():
    """The notes of the choices made since the last drain, each once: the build log's lines."""
    global _notes
    out, _notes = _notes, []
    return out
