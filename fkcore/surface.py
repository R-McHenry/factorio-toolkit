"""fkcore.surface: the surface file (`<surface>.surface`), CORE-V1.md §6.2 and §11.

    surface  <name>
    mode     play | lab
    force    <name>                           # whose the paste is (default: player in play, lab in lab)
    terrain  <name> | none                    # the bare world the layout is made against
    catalog  <name>
    place <factory> = <module> plot <x>,<y> <W>x<H> [rot <r>] [patch <resource>[#<n>]]
          [temporary until <condition or tick>] [retired]
    robots <name>: cover <factory>, ...
    claim <name> box <x0>,<y0> <x1>,<y1> [until <tick>] ["reason"]
    watch plots|sanctioned: keep | revert | strict | mark [<duration>]
    notify   nearby | all | off
    target   <item> <rate>/<unit>, ...

A ``#`` starts a comment at the start of a line or after a space. ``<module>`` is a factory file of the game codebase (``<module>.fk`` beside the surface file); its
layout record is ``<module>.fkp``. :func:`floorplan` turns the place and claim lines into the
surface's own .fkp (plots and claims); composing it with the factories' layouts is
``fkcore.compose``. The defaults follow CORE-V1.md §6.4/6.5: ``play`` mode, watch ``plots: keep``
and ``sanctioned: mark``, notify ``nearby`` in play and ``all`` in lab. Pure, stdlib only.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from . import fkp as fkpmod

__all__ = ["SurfaceError", "Place", "SurfaceFile", "loads", "load", "floorplan"]

_UNITS = {"s": 1.0, "min": 60.0, "h": 3600.0}


class SurfaceError(ValueError):
    pass


@dataclass
class Place:
    factory: str
    module: str
    x: int
    y: int
    w: int
    h: int
    rot: int = 0
    patch: str | None = None
    lifecycle: str = "placed"          # placed | temporary until ... | retired
    line: int = 0


@dataclass
class SurfaceFile:
    path: str
    name: str = ""
    mode: str = "play"
    terrain: str = "none"
    catalog: str = "base"
    places: dict = field(default_factory=dict)        # factory -> Place
    robots: dict = field(default_factory=dict)        # name -> [factory]
    claims: dict = field(default_factory=dict)        # name -> fkp.Claim
    watch: dict = field(default_factory=lambda: {"plots": "keep", "sanctioned": "mark"})
    notify: str | None = None
    force: str | None = None                          # the paste's force; None = by mode
    targets: dict = field(default_factory=dict)       # item -> items/s

    @property
    def notify_mode(self):
        return self.notify or ("all" if self.mode == "lab" else "nearby")


def _pair(s, where):
    try:
        x, y = s.split(",")
        return int(x), int(y)
    except ValueError:
        raise SurfaceError(f"{where}: expected x,y, got {s!r}") from None


def _strip(raw):
    """The line without its comment: a # at the start or after a space, outside quotes (so a
    patch name like iron-ore#2 survives)."""
    quoted = False
    for i, ch in enumerate(raw):
        if ch == '"':
            quoted = not quoted
        elif ch == "#" and not quoted and (i == 0 or raw[i - 1].isspace()):
            return raw[:i].strip()
    return raw.strip()


def loads(text, path="<surface>") -> SurfaceFile:
    sf = SurfaceFile(path)
    for n, raw in enumerate(text.splitlines(), 1):
        line = _strip(raw)
        if not line:
            continue
        where = f"{path}:{n}"
        t = shlex.split(line)
        head = t[0]
        try:
            if head in ("surface", "mode", "terrain", "catalog", "notify", "force") and len(t) == 2:
                if head == "mode" and t[1] not in ("play", "lab"):
                    raise SurfaceError(f"{where}: mode is play or lab")
                if head == "notify" and t[1] not in ("nearby", "all", "off"):
                    raise SurfaceError(f"{where}: notify is nearby, all or off")
                setattr(sf, "name" if head == "surface" else head, t[1])
            elif head == "place":
                if t[2] != "=" or t[4] != "plot":
                    raise SurfaceError(f"{where}: place <factory> = <module> plot x,y WxH ...")
                x, y = _pair(t[5], where)
                m = re.fullmatch(r"(\d+)x(\d+)", t[6])
                if not m:
                    raise SurfaceError(f"{where}: expected WxH, got {t[6]!r}")
                p = Place(t[1], t[3], x, y, int(m.group(1)), int(m.group(2)), line=n)
                rest = t[7:]
                while rest:
                    if rest[0] == "rot":
                        p.rot, rest = int(rest[1]) % 4, rest[2:]
                    elif rest[0] == "patch":
                        p.patch, rest = rest[1], rest[2:]
                    elif rest[0] == "temporary":
                        p.lifecycle, rest = " ".join(rest), []
                    elif rest[0] == "retired":
                        p.lifecycle, rest = "retired", rest[1:]
                    else:
                        raise SurfaceError(f"{where}: unknown place option {rest[0]!r}")
                if p.factory in sf.places:
                    raise SurfaceError(f"{where}: {p.factory} is placed twice")
                sf.places[p.factory] = p
            elif head == "robots":
                name = t[1].rstrip(":")
                if t[2] != "cover":
                    raise SurfaceError(f"{where}: robots <name>: cover <factory>, ...")
                sf.robots[name] = [w.strip(",") for w in t[3:] if w.strip(",")]
            elif head == "claim":
                lay = fkpmod.loads("fkp 1 surface s\n" + line, where)
                (c,) = lay.claims.values()
                sf.claims[c.name] = c
            elif head == "watch":
                region = t[1].rstrip(":")
                if region not in ("plots", "sanctioned") or not t[2:]:
                    raise SurfaceError(f"{where}: watch plots|sanctioned: <action>")
                if t[2] not in ("keep", "revert", "strict", "mark"):
                    raise SurfaceError(f"{where}: a watch action is keep, revert, strict or mark")
                sf.watch[region] = " ".join(t[2:])
            elif head == "target":
                for part in " ".join(t[1:]).split(","):
                    item, rate = part.split()
                    num, unit = rate.split("/")
                    sf.targets[item] = float(num) / _UNITS[unit]
            else:
                raise SurfaceError(f"{where}: unknown line {head!r}")
        except (IndexError, KeyError, ValueError) as exc:
            if isinstance(exc, SurfaceError):
                raise
            raise SurfaceError(f"{where}: malformed {head} line ({exc})") from None
    if not sf.name:
        raise SurfaceError(f"{path}: no surface line")
    return sf


def load(path) -> SurfaceFile:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read(), path)


def floorplan(sf: SurfaceFile, infra=None) -> fkpmod.Layout:
    """The surface's own .fkp: a plot per placed factory (retired ones free their plot), its
    claims, and ``infra`` (a surface Layout of shared infrastructure, kept as it is)."""
    lay = fkpmod.Layout("surface", sf.name)
    for name, p in sf.places.items():
        if p.lifecycle == "retired":
            continue
        params = {"module": p.module}
        if p.patch:
            params["patch"] = p.patch
        lay.plots[name] = fkpmod.Plot(name, p.x, p.y, p.rot, p.w, p.h, params)
    lay.claims.update(sf.claims)
    if infra is not None:
        lay.covers.update(infra.covers)
        lay.marks.update(infra.marks)
        for e in infra.entities.values():
            lay.add(e)
    return lay
