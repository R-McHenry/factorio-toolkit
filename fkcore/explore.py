"""fkcore.explore: Go-Explore on the speedrun planner (2.0.64).

Rory, 2026-10-29: "define 'cells' as low resolution snapshot of a game state such as
floor(log(item)) foreach item in total items produced. Then each time you reach a new cell, you can
save the trajectory of actions that got there. The go explore loop is to return to a cell state,
explore to seek new cells, and when a new cell is reached save again, or if an existing cell is
reached more quickly, then the previous trajectory is replaced with the new way." And: "the
simplest way to implement the agent is its just a mode of the sim where ... there is just a switch
that the agent turns on and the sim picks [the state] by itself and gives the agent a goal cell",
the goal "at least some N distance in manhattan", go positions and targets impartial, and a prior,
if any, "based on the cells visited by our most successful runs".

The pieces:

- **A cell.** ``{item: floor(log_base(produced))}`` over every item the force has produced (the
  game's production statistics, cumulative). ``base`` is the resolution: 2 by default, smaller is
  finer. An item never produced has no entry, and counts as level -1 in a distance.
- **The archive** (``sim\\explore\\archive.json``). One entry per cell: its levels, the first tick it
  was reached at, the save state that holds it, and the trajectory that got there.
  - **The trajectory.** The actions from the start, each at its tick: a ``paste``, a ``decon``, or
    a ``game`` command (research, lua, decon).
  - **A faster way.** A cell reached at an earlier tick has its trajectory and its save replaced.
- **An episode** (``explore on`` / ``next``).
  - **Go.** A cell picked uniformly from the archive (or from the cells on the way to the best
    ones, with ``prior``), loaded from its save.
  - **The goal.** That cell plus ``dist`` steps of +1 level, each on an item picked uniformly from
    those the archive has seen produced and those the force can make there.
  - **Reaching it.** Reached when every one of those items stands at its goal level or above. The
    cells passed on the way go into the archive too.

The sim records the actions and checks the cell as the game runs (``fkcore.sim``). Stdlib only.
"""
from __future__ import annotations

import json
import math
import os
import random
import time

__all__ = ["cell", "key", "distance", "Archive", "LUA_MADE", "ExploreError"]

#: the production statistics (cumulative, every item made) and the items the force can make now
LUA_MADE = """
local f = game.forces['player']
local st = f.get_item_production_statistics('nauvis')
local made = {}
for name, n in pairs(st.input_counts) do made[name] = n end
local can = {}
for name, r in pairs(f.recipes) do
  if r.enabled and not r.hidden then
    for _, p in pairs(r.products) do if p.type == 'item' then can[p.name] = true end end
  end
end
local list = {}
for name in pairs(can) do list[#list + 1] = name end
rcon.print(helpers.table_to_json({tick = game.tick, made = made, can = list}))
"""


class ExploreError(RuntimeError):
    pass


def cell(made, base=2.0):
    """{item: count produced} -> {item: floor(log_base(count))}, every item made at least once."""
    out = {}
    for item, n in made.items():
        n = float(n)
        if n >= 1:
            # a hair over, so an exact power (1024 = 2^10) is its own level despite float rounding
            out[item] = int(math.floor(math.log(n, base) + 1e-9))
    return out


def key(levels):
    """A cell's archive key: ``item=level`` sorted, joined by commas."""
    return ",".join(f"{i}={levels[i]}" for i in sorted(levels))


def levels_of(k):
    return {p.split("=")[0]: int(p.split("=")[1]) for p in k.split(",") if p}


def distance(a, b):
    """Manhattan distance between two cells (an item missing from one is level -1 there)."""
    return sum(abs(a.get(i, -1) - b.get(i, -1)) for i in set(a) | set(b))


def reached(now, goal):
    """True when ``now`` stands at or above ``goal`` on every item of the goal."""
    return all(now.get(i, -1) >= lvl for i, lvl in goal.items())


def shortfall(now, goal):
    """{item: (now, goal)} for the goal's items not reached yet."""
    return {i: (now.get(i, -1), lvl) for i, lvl in sorted(goal.items()) if now.get(i, -1) < lvl}


def count_text(level, base):
    """A level as the count it stands for: level 10 at base 2 is 1024+, level -1 is none."""
    if level < 0:
        return "none"
    n = base ** level
    return f"{int(math.ceil(n - 1e-9)):,}+"


class Archive:
    """``sim\\explore\\archive.json``: the settings, the cells and the current episode."""

    def __init__(self, sim_root):
        self.root = os.path.join(sim_root, "explore")
        self.path = os.path.join(self.root, "archive.json")
        self.files = os.path.join(self.root, "files")
        self.data = {"settings": {}, "cells": {}, "episode": None, "episodes": 0, "next_id": 0,
                     "on": False}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                self.data.update(json.load(fh))

    def write(self):
        os.makedirs(self.root, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self.data, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    # -- settings ---------------------------------------------------------------------------------
    @property
    def on(self):
        return bool(self.data.get("on"))

    @property
    def settings(self):
        s = {"base": 2.0, "dist": 4, "budget": 36000, "chunk": 600, "prior": 0}
        s.update(self.data.get("settings") or {})
        return s

    @property
    def cells(self):
        return self.data["cells"]

    @property
    def episode(self):
        return self.data.get("episode")

    def new_id(self):
        self.data["next_id"] = int(self.data.get("next_id", 0)) + 1
        return f"x{self.data['next_id']}"

    # -- cells --------------------------------------------------------------------------------------
    def offer(self, levels, tick, traj, save_name_for):
        """A cell reached at ``tick`` by ``traj``: -> "new", "faster" or None (known, not faster).
        ``save_name_for(name)`` saves the game as that save state; it is called only when the
        cell is new or faster."""
        k = key(levels)
        have = self.cells.get(k)
        ep = self.episode or {}
        if have is not None and int(have["tick"]) <= tick:
            return None
        root = self.data.get("root", "x0")
        name = have["save"] if have is not None and have["save"] != root else self.new_id()
        save_name_for(name)
        self.cells[k] = {"levels": levels, "tick": tick, "save": name, "traj": list(traj),
                         "found": time.strftime("%Y-%m-%dT%H:%M:%S"),
                         "episode": ep.get("n"), "parent": ep.get("go"),
                         "visits": (have or {}).get("visits", 0),
                         "beaten": (have or {}).get("beaten", 0) + (1 if have else 0)}
        return "faster" if have is not None else "new"

    def best(self, k=1):
        """The ``k`` furthest cells: most levels in all, then the earliest tick."""
        ranked = sorted(self.cells.items(),
                        key=lambda kv: (-sum(kv[1]["levels"].values()), int(kv[1]["tick"])))
        return ranked[:k]

    def ancestry(self, k):
        """The cells on the way to ``k``: it, its parent (the go cell of the episode that found
        it), that one's, and so on."""
        out, seen = [], set()
        while k and k in self.cells and k not in seen:
            seen.add(k)
            out.append(k)
            k = self.cells[k].get("parent")
        return out

    def pick_go(self, rng):
        """The go cell: uniform over the archive, or with ``prior`` K over the cells on the way to
        the K furthest (Rory: a prior "based on the cells visited by our most successful runs")."""
        keys = sorted(self.cells)
        if not keys:
            raise ExploreError("the archive is empty (fk sim explore on starts it)")
        prior = int(self.settings["prior"] or 0)
        if prior > 0:
            pool = sorted({c for k, _row in self.best(prior) for c in self.ancestry(k)})
            if pool:
                keys = pool
        return rng.choice(keys)

    def pick_goal(self, go_levels, can, dist, rng):
        """``go_levels`` plus ``dist`` steps of +1, each on an item picked uniformly from the items
        the archive has seen made and the items the force can make (``can``). -> {item: level},
        the goal's items only."""
        seen = set()
        for row in self.cells.values():
            seen |= set(row["levels"])
        pool = sorted(seen | set(can))
        if not pool:
            raise ExploreError("no item to aim for: nothing made yet and no recipe enabled")
        goal = {}
        for _ in range(int(dist)):
            item = rng.choice(pool)
            goal[item] = goal.get(item, go_levels.get(item, -1)) + 1
        return goal

    def start_episode(self, go, goal, tick):
        self.data["episodes"] = int(self.data.get("episodes", 0)) + 1
        self.cells[go]["visits"] = int(self.cells[go].get("visits", 0)) + 1
        self.data["episode"] = {"n": self.data["episodes"], "go": go, "goal": goal,
                                "start": tick, "traj": list(self.cells[go]["traj"]),
                                "found": [], "faster": [], "reached": None}
        return self.data["episode"]

    def record(self, tick, verb, args):
        ep = self.episode
        if ep is None:
            raise ExploreError("no episode (fk sim explore on)")
        ep["traj"].append({"tick": int(tick), "verb": verb, "args": list(args)})

    def keep_file(self, path):
        """A copy of a file an action names, under ``explore\\files`` (by content), so a trajectory
        still plays when the player's file has changed. -> the copy's path."""
        import hashlib
        with open(path, "rb") as fh:
            data = fh.read()
        ext = os.path.splitext(path)[1]
        name = hashlib.sha1(data).hexdigest()[:12] + ext
        os.makedirs(self.files, exist_ok=True)
        dest = os.path.join(self.files, name)
        if not os.path.exists(dest):
            with open(dest, "wb") as fh:
                fh.write(data)
        return dest

    # -- reports ------------------------------------------------------------------------------------
    def plan(self, k, end_tick=None):
        """The trajectory of cell ``k`` as a playback script (``fkcore.sim.play_lines``)."""
        row = self.cells[k]
        lines = [f"# fk sim explore: the way to cell {row['save']} (tick {row['tick']}, "
                 f"{sum(row['levels'].values())} levels)",
                 f"from {self.data.get('root', 'x0')}", "speed 100"]
        for a in row["traj"]:
            lines.append(f"at {a['tick']}")
            if a["verb"] == "paste":
                lines.append(f"paste {a['args'][0]} @{a['args'][1]},{a['args'][2]}")
            elif a["verb"] == "decon":
                lines.append("decon " + ",".join(str(v) for v in a["args"]))
            elif a["verb"] == "game":
                args = [str(v) for v in a["args"]]
                if args[:1] == ["lua"] and len(args) == 2:
                    # a chunk of Lua is a file of its own: a playback line is one line of words
                    path = self._lua_file(args[1])
                    args = ["lua", "--file", path]
                lines.append("game " + " ".join(args))
        lines.append(f"at {end_tick if end_tick is not None else row['tick']}")
        return "\n".join(lines) + "\n"

    def _lua_file(self, text):
        import hashlib
        os.makedirs(self.files, exist_ok=True)
        path = os.path.join(self.files, hashlib.sha1(text.encode()).hexdigest()[:12] + ".lua")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        return path

    def goal_text(self, now=None):
        ep, base = self.episode, float(self.settings["base"])
        if ep is None:
            return "no episode"
        now = now if now is not None else self.cells[ep["go"]]["levels"]
        parts = []
        for item, (have, want) in shortfall(now, ep["goal"]).items():
            parts.append(f"{item} {count_text(want, base)} made (now {count_text(have, base)})")
        return "; ".join(parts) or "reached"
