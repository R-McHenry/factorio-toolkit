"""fkcore.alerts: the game's alert panel, pushed to the agent (CORE-V1 §6.5, decisions 8 and 11).

Pushed alerts are exactly what the game's alert panel (the yellow triangle) shows: what the game
raises itself (entity destroyed or under attack, no material for construction, not enough robots,
no storage, turret out of ammo, ...) and programmable-speaker alerts (``custom``), the in-game way
to build one's own alerts from circuits. Beside ``nearby`` notify they are the only unasked
channel in play mode. Nothing is ever derived from the free reads (production statistics, the
chart: ``fkcore.freereads``): ``track`` takes only an ``AlertRead``, which only ``read`` makes.

**Alerts are per player.** The game keeps them in ``LuaPlayer.get_alerts``; ``LuaForce`` has no
``get_alerts`` (the lab bench, 2026-10-20). So a force's panel is the union of its players'
panels, connected or not, deduped (each player of a force sees the same alert), and a force with
no player has no panel to read: ``AlertRead.forces`` says how many players every force has. Each
alert is normalised to {type (the ``defines.alert_type`` name), surface, x, y, target (entity or
prototype name), message and icon (custom alerts only), tick}; its identity (``key``) is all of
that but the tick, which the game moves while an entity stays under attack.

``track(state, read, tick, remind_ticks)`` is pure: a new alert is pushed once; one that persists
gets a reminder every ``remind_ticks``; one that is gone is reported once as cleared. The cadence
is the surface file's ``remind`` (default 10min, **a placeholder: the default is still open with
Rory**). ``poll(r, game_dir)`` is what every agent command calls, as it reads the chat journal
today: read the panel of the surface mode's force (lab -> ``lab``, play -> ``player``), track it
with the state in ``<game>/out/alerts.json``, push the lines to game chat and the inbox when
notify is ``all`` (``fkcore.notify``), and return them. It never raises: a failed read is one
line. The game link is the caller's (``link.Rcon``, only with ``FK_LINK=on``).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import link
from . import notify as notifymod
from . import surface as surfacemod

__all__ = ["AlertRead", "Poll", "normalise", "key", "describe", "track", "lines", "age", "read",
           "check", "poll", "state_path"]

TICKS_PER_S = 60


@dataclass(frozen=True)
class AlertRead:
    """One read of a force's alert panel: the only input ``track`` takes."""
    force: str
    tick: int
    alerts: tuple                   # normalised alerts, deduped across players, sorted by key
    players: tuple = ()             # ({name, connected, alerts}, ...): the force's players
    forces: dict = field(default_factory=dict)    # {force: {players, connected}}: every force


def _list(v):
    """A JSON array from the game: Lua's empty table comes back as {} or []."""
    if isinstance(v, dict):
        return list(v.values())
    return list(v or [])


def _num(v):
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


def _fmt(v):
    return "?" if v is None else str(_num(v))


def _text(m):
    """A LocalisedString as text: a plain string as it is, ["", a, b] joined, anything else as
    JSON (a locale key the toolkit cannot translate)."""
    if m is None or isinstance(m, str):
        return m
    if isinstance(m, (int, float)):
        return str(m)
    if isinstance(m, list) and m and m[0] == "":
        return "".join(_text(x) or "" for x in m[1:])
    return json.dumps(m, sort_keys=True)


def normalise(raw) -> AlertRead:
    """The link's raw read (``link.alerts``) -> an AlertRead: one alert per identity, the
    earliest tick kept."""
    seen = {}
    for row in _list(raw.get("alerts")):
        a = {"type": str(row.get("type")), "surface": str(row.get("surface") or ""),
             "x": _num(row.get("x")), "y": _num(row.get("y")), "target": row.get("target"),
             "message": _text(row.get("message")), "icon": row.get("icon"),
             "tick": int(row.get("tick") or 0)}
        k = key(a)
        if k not in seen or a["tick"] < seen[k]["tick"]:
            seen[k] = a
    forces = raw.get("forces")
    return AlertRead(str(raw.get("force") or ""), int(raw.get("tick") or 0),
                     tuple(seen[k] for k in sorted(seen)), tuple(_list(raw.get("players"))),
                     dict(forces) if isinstance(forces, dict) else {})


def key(a):
    """An alert's identity: everything but its tick."""
    return "|".join([a["type"], a["surface"], f"{_fmt(a.get('x'))},{_fmt(a.get('y'))}",
                     a.get("target") or "", a.get("message") or "", a.get("icon") or ""])


def describe(a):
    """'entity_under_attack: wooden-chest at lab 385.5,520.5', or for a speaker
    'custom "text" [item/iron-plate]: programmable-speaker at lab 390.5,520.5'."""
    where = f"{a.get('target') or '?'} at {a['surface']} {_fmt(a.get('x'))},{_fmt(a.get('y'))}"
    if a["type"] != "custom":
        return f"{a['type']}: {where}"
    msg = f' "{a["message"]}"' if a.get("message") else ""
    icon = f" [{a['icon']}]" if a.get("icon") else ""
    return f"custom{msg}{icon}: {where}"


def track(state, read, tick, remind_ticks):
    """-> (new, reminders, cleared, state). Each of the three lists holds entries {alert, first,
    pushed}: ``first`` is the tick the tracker first saw it, ``pushed`` the tick it was last
    pushed. ``state`` is the previous result's state (or None); ``remind_ticks`` 0 or None never
    reminds. Pure."""
    if not isinstance(read, AlertRead):
        raise TypeError("alerts.track takes only an alert-panel read (alerts.read); a free read "
                        f"({type(read).__name__}: statistics, chart) never becomes an alert")
    old = dict((state or {}).get("alerts") or {})
    now, new, reminders = {}, [], []
    for a in read.alerts:
        k = key(a)
        prev = old.get(k)
        if prev is None:
            e = {"alert": dict(a), "first": tick, "pushed": tick}
            new.append(e)
        else:
            e = {"alert": dict(a), "first": prev["first"], "pushed": prev["pushed"]}
            if tick < e["pushed"]:                      # the clock went back: an older save
                e["pushed"] = tick
            elif remind_ticks and tick - e["pushed"] >= remind_ticks:
                e["pushed"] = tick
                reminders.append(e)
        now[k] = e
    cleared = [old[k] for k in sorted(old) if k not in now]
    return new, reminders, cleared, {"force": read.force, "tick": tick, "alerts": now}


def age(ticks):
    """Ticks as '45s', '2min 5s', '1h 3min'."""
    s = max(0, int(ticks)) // TICKS_PER_S
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}min {s}s" if s else f"{m}min"
    h, m = divmod(m, 60)
    return f"{h}h {m}min" if m else f"{h}h"


def lines(new, reminders, cleared, tick):
    """The push lines: ALERT once, REMINDER while it persists, CLEARED once."""
    out = [f"ALERT {describe(e['alert'])} (raised at tick {e['alert']['tick']})" for e in new]
    out += [f"REMINDER {describe(e['alert'])}: still there, first seen {age(tick - e['first'])} "
            f"ago (tick {e['first']})" for e in reminders]
    out += [f"CLEARED {describe(e['alert'])} (seen for {age(tick - e['first'])})"
            for e in cleared]
    return out


# -- the game ---------------------------------------------------------------------------------
def read(r, force, tag="alerts") -> AlertRead:
    """The alert panel of ``force``: every player's, connected or not, deduped."""
    return normalise(link.alerts(r, force, tag))


def state_path(game_dir):
    return os.path.join(game_dir, "out", "alerts.json")


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path, states):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(states, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


@dataclass
class Poll:
    surface: str
    force: str
    remind: str
    notify: str
    read: AlertRead
    new: list
    reminders: list
    cleared: list
    lines: list
    pushed: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def report(self):
        """What ``python -m fkcore alerts`` prints: who has a panel, then the push lines."""
        rd = self.read
        out = [f"alerts {self.surface}: force {self.force}, tick {rd.tick}; remind every "
               f"{self.remind}; notify {self.notify}"]
        if rd.players:
            who = [f"{p.get('name')} ({'connected' if p.get('connected') else 'offline'}) "
                   f"{p.get('alerts', 0)} alerts" for p in rd.players]
            out.append(f"  players of {self.force}: {len(rd.players)} ("
                       f"{sum(1 for p in rd.players if p.get('connected'))} connected): "
                       + ", ".join(who))
        else:
            out.append(f"  players of {self.force}: 0: no alert panel to read (the game keeps "
                       "alerts per player)")
        out.append("  forces: " + ", ".join(
            f"{name} {f.get('players', 0)} player(s) ({f.get('connected', 0)} connected)"
            for name, f in sorted(rd.forces.items())))
        persisting = len(rd.alerts) - len(self.new)
        out.append(f"  panel: {len(rd.alerts)} alerts after dedupe; new {len(self.new)}, "
                   f"reminders {len(self.reminders)}, cleared {len(self.cleared)}, persisting "
                   f"{persisting}")
        out += self.lines
        if self.pushed:
            out.append(f"pushed {len(self.pushed)} line(s) to game chat and out/inbox.txt")
        out += [f"note: {n}" for n in self.notes]
        return out


def check(r, game_dir, force=None) -> Poll:
    """Read the panel, track it (state in ``<game>/out/alerts.json``), push when notify is all."""
    from .apply import force_for
    sf = surfacemod.load_game(game_dir)
    force = force or force_for(sf.mode)
    rd = read(r, force)
    path = state_path(game_dir)
    states = _load(path)
    new, reminders, cleared, st = track(states.get(force), rd, rd.tick, sf.remind_ticks)
    states[force] = st
    _save(path, states)
    out = lines(new, reminders, cleared, rd.tick)
    poll_ = Poll(sf.name, force, sf.remind, sf.notify_mode, rd, new, reminders, cleared, out)
    if out and sf.notify_mode == "all":
        try:
            poll_.pushed = notifymod.push(r, game_dir, sf.name, out, rd.tick, "alert")
        except (OSError, link.LinkError) as exc:
            poll_.notes.append(f"chat push failed ({type(exc).__name__}: {exc})")
    return poll_


def poll(r, game_dir, force=None):
    """The alert lines since the last poll (new, reminders, cleared); [] when nothing changed.
    Never raises: a failed read is one line."""
    try:
        return check(r, game_dir, force).lines
    except Exception as exc:          # a footnote must never break the command that asked
        return [f"alerts: not read ({type(exc).__name__}: {exc})"]
