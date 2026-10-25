"""fkcore.freereads: the free reads of decision 11, production statistics and the charted map.

A player sees both from anywhere (the production panel, the map), so the agent may read them
anywhere and at any time, when it chooses to, like a player opening the panel (CORE-V1 §6.5).
**No automated alert is ever derived from them**: nothing here keeps state, compares with a line
or pushes, and ``fkcore.alerts.track`` refuses anything but an alert-panel read.

- ``stats(r, force, surface, items=None, window="1min")`` -> ``StatsRead``: per item, the flow
  counts of ``LuaForce.get_item_production_statistics(surface)`` over the window (made and used
  per minute, and as counts) and the totals since the map began;
- ``chart(r, force, surface)`` -> ``ChartRead``: how many of the surface's generated chunks the
  force has charted, and their bounding box;
- ``stock(r, force, surface)`` -> ``StockRead``: what the base holds per item, in chests and in
  roboports apart (a robot in a chest is an item, and flies only from a roboport).

``python -m fkcore stats GAME [--items a,b] [--window 1min|10min|1h]`` and ``chart GAME`` print
them for the game's surface and its mode's force (lab -> ``lab``, play -> ``player``). The
``*_lines`` functions are pure; ``stats`` and ``chart`` use the game link (``FK_LINK=on``).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import link

__all__ = ["StatsRead", "ChartRead", "StockRead", "stats", "chart", "stock", "stats_from",
           "chart_from", "stock_from", "stats_lines", "chart_lines", "stock_lines", "WINDOWS"]

WINDOWS = link.WINDOWS
CHUNK = 32


@dataclass(frozen=True)
class StatsRead:
    force: str
    surface: str
    tick: int
    window: str
    items: tuple            # ({name, made_per_min, used_per_min, made, used, made_total,
                            #   used_total} | {name, unknown: True}, ...) sorted by name


@dataclass(frozen=True)
class StockRead:
    """What the base holds: items in chests (idle until something moves them) and in roboports
    (robots in the robot slots, repair packs in the material slots), per item."""
    force: str
    surface: str
    tick: int
    chest: tuple            # ((name, count), ...) sorted by name
    port: tuple

    def total(self, name):
        return dict(self.chest).get(name, 0) + dict(self.port).get(name, 0)


@dataclass(frozen=True)
class ChartRead:
    force: str
    surface: str
    tick: int
    charted: int            # charted chunks
    chunks: int             # generated chunks on the surface
    box: tuple | None       # (cx0, cy0, cx1, cy1) chunk coordinates, inclusive


def _list(v):
    return list(v.values()) if isinstance(v, dict) else list(v or [])


def stats_from(raw) -> StatsRead:
    rows = sorted(_list(raw.get("items")), key=lambda r: str(r.get("name")))
    return StatsRead(str(raw.get("force")), str(raw.get("surface")), int(raw.get("tick") or 0),
                     str(raw.get("window")), tuple(rows))


def chart_from(raw) -> ChartRead:
    box = raw.get("box")
    return ChartRead(str(raw.get("force")), str(raw.get("surface")), int(raw.get("tick") or 0),
                     int(raw.get("charted") or 0), int(raw.get("chunks") or 0),
                     tuple(int(v) for v in _list(box)) if box else None)


def stats(r, force, surface, items=None, window="1min") -> StatsRead:
    return stats_from(link.stats(r, force, surface, items, window))


def chart(r, force, surface) -> ChartRead:
    return chart_from(link.chart(r, force, surface))


def stock_from(raw) -> StockRead:
    def rows(v):
        return tuple(sorted((str(k), int(n)) for k, n in (v or {}).items()))
    return StockRead(str(raw.get("force")), str(raw.get("surface")), int(raw.get("tick") or 0),
                     rows(raw.get("chest")), rows(raw.get("port")))


def stock(r, force, surface) -> StockRead:
    return stock_from(link.stock(r, force, surface))


def stock_lines(st: StockRead):
    """What the base holds, largest first. Robots get their own line: one in a chest is an item
    and does nothing until an inserter puts it into a roboport."""
    chest, port = dict(st.chest), dict(st.port)
    names = sorted(set(chest) | set(port),
                   key=lambda n: (-(chest.get(n, 0) + port.get(n, 0)), n))
    total = sum(chest.values()) + sum(port.values())
    out = [f"stock {st.surface}: force {st.force}, tick {st.tick}: {len(names)} kinds, {total} "
           f"items in chests and roboports (a free read: never an alert)"]
    for n in names:
        c, p = chest.get(n, 0), port.get(n, 0)
        line = f"  {n:<30} {c + p:>7}"
        if n.endswith("-robot"):
            line += f"  ({p} in roboports, {c} in chests)"
            if c:
                line += " - the ones in chests are idle: an inserter into a roboport starts them"
        elif c and p:
            line += f"  ({c} in chests, {p} in roboports)"
        out.append(line)
    if not any(n.endswith("-robot") and port.get(n) for n in port):
        out.append("  no robots in any roboport: nothing flies until one is loaded")
    return out


def _n(v):
    f = float(v or 0)
    return f"{f:.0f}" if f.is_integer() or abs(f) >= 100 else f"{f:.2f}"


def stats_lines(st: StatsRead):
    known = [r for r in st.items if not r.get("unknown")]
    out = [f"stats {st.surface}: force {st.force}, window {st.window}, tick {st.tick}: "
           f"{len(known)} items (a free read: never an alert)"]
    if known:
        out.append(f"  {'item':<28} {'made/min':>10} {'used/min':>10} {'made':>8} {'used':>8} "
                   f"{'made total':>11} {'used total':>11}")
    for r in known:
        out.append(f"  {r['name']:<28} {_n(r.get('made_per_min')):>10} "
                   f"{_n(r.get('used_per_min')):>10} {_n(r.get('made')):>8} "
                   f"{_n(r.get('used')):>8} {_n(r.get('made_total')):>11} "
                   f"{_n(r.get('used_total')):>11}")
    out += [f"  {r['name']}: not an item" for r in st.items if r.get("unknown")]
    return out


def chart_lines(ch: ChartRead):
    head = (f"chart {ch.surface}: force {ch.force}, tick {ch.tick}: {ch.charted} of {ch.chunks} "
            f"generated chunks charted (a free read: never an alert)")
    if not ch.box:
        return [head]
    x0, y0, x1, y1 = ch.box
    return [head, f"  chunks x {x0}..{x1}, y {y0}..{y1}; tiles {x0 * CHUNK},{y0 * CHUNK} to "
                  f"{(x1 + 1) * CHUNK},{(y1 + 1) * CHUNK} "
                  f"({(x1 - x0 + 1) * CHUNK}x{(y1 - y0 + 1) * CHUNK})"]
