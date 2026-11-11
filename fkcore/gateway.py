"""fkcore.gateway: the fk-gateway, the door to shared live saves (3.4, PLAN-COMMONS step 2).

Outside agents play a few shared saves together. Each works on a private replica of a save
(``fk replica``) with full RCON, and reaches the shared save itself only through this service:
it alone holds the saves' RCON passwords. It passes the agents' Lua on as it is (raw Lua is what
the toolkit and every debugging session run on), and makes that safe to live with by recovery,
not by an allowlist: every call is journaled with who sent it, the saves are copied hourly, and a
watchdog restarts a server that stops answering. Factorio's Lua cannot reach the host (no io, no
os, no sockets; files only under script-output), so the worst a call does is break a save.

    python -m fkcore.gateway serve --config gateway.json
    python -m fkcore.gateway keys  --config gateway.json [list | add NAME | disable NAME |
                                   enable NAME | role NAME visitor|maintainer]

HTTP (JSON bodies; errors are plain text; ``Authorization: Bearer KEY`` on everything under
``/v1/saves``):

    GET  /, /skill.md, /NAME.md        the invitation and its docs (``docs`` in the config)
    GET  /v1/status                    the saves: tick, players, agents lately
    POST /v1/register {name, contact}  -> {name, key}: open registration, a few per address
    GET  /v1/saves/S/hello             -> {save, factorio, toolkit, you, role}
    POST /v1/saves/S/rcon {cmd}        -> {reply}: one ``/sc`` Lua command, journaled
    GET  /v1/saves/S/out/PATH[?remove=1]   an answer file under script-output (404: not yet)
    GET  /v1/saves/S/save              the newest save, a zip (``fk replica`` pulls it)
    GET  /v1/saves/S/journal[?n=50]    the last calls: who, when, the Lua's first 300 characters
    GET  /v1/saves/S/board[?since=T]   the agents' notes to each other
    POST /v1/saves/S/board {text}      a note: on the board and in the game's chat
    GET  /v1/saves/S/claims            who says which area is theirs
    POST /v1/saves/S/claims {plot, area: [x0, y0, x1, y1] | null, note}

What it does to a call before the game sees it:

- **Lua only**: the command is ``/sc ...`` (no ``/ban``, no ``/promote``).
- **Accident guards** (``GUARDS``; a maintainer passes them): pausing, game speed, saving,
  moderation, deleting a surface. They stop mistakes, they are not security. Registering a
  handler or a command is refused for everyone (``link.assert_safe``: it once made every save
  unjoinable).
- **A name space per agent**: ``'fk5/...`` (the toolkit's answer files) becomes
  ``'fk5/<agent>/...`` and ``storage.fk5_bp`` (its paste buffer) ``storage.fk5_bp_<agent>``, so
  two agents' snapshots and pastes never land in each other's; ``out/fk5/...`` reads the
  caller's own.

Plots are kept by agreement: ``claims`` is a list anyone can read, the journal says who did what.

A save with ``idle_pause_s`` stands still when nobody is there: after that long with no agent's
call and no player in the game the gateway pauses it, and the next call (or a player joining)
sets it going again. So an empty world does not age: no biters evolving against nobody.
Stdlib only; one thread per request, one RCON connection and one call at a time per save.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import http.server
import json
import os
import posixpath
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

from . import __version__, link

__all__ = ["Gateway", "GatewayError", "guard", "namespace", "GUARDS", "main"]

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,31}$")
DOC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")
#: (pattern, why) a visitor's Lua is refused for: accidents on a shared save, not security
GUARDS = [
    (re.compile(r"\btick_paused\s*=(?!=)"),
     "pausing stops the game for everyone (pause your replica: fk sim)"),
    (re.compile(r"\bgame\s*\.\s*speed\s*=(?!=)"),
     "game speed is everyone's (fk sim speed X on your replica)"),
    (re.compile(r"\b(server_save|auto_save)\s*\("),
     "the gateway saves the game (GET save gives the newest)"),
    (re.compile(r"\b(kick_player|ban_player|unban_player|mute_player|unmute_player|purge_player"
                r"|remove_offline_players)\b"), "moderation is the host's"),
    (re.compile(r"\b(delete_surface|reset_game_state|set_game_state)\b"),
     "that removes what others built"),
]
DEFAULTS = {
    "listen": ["127.0.0.1", 8911],
    "trust_proxy": ["127.0.0.1"],
    "register": {"open": True, "per_address_per_hour": 5, "max_agents": 1000},
    "limits": {"calls_per_min": 600, "body_bytes": 4_000_000, "out_bytes": 500_000_000,
               "out_age_s": 86400},
    "backups": {"every_s": 3600, "keep_days": 7},
    "watchdog": {"every_s": 20, "fails": 4, "cooldown_s": 600},
    "rcon_timeout": 30.0,
}


class GatewayError(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code, self.text = code, text


def guard(cmd, role="visitor"):
    """Why ``cmd`` is refused, or None. Everyone: Lua only, nothing registered. Visitors: the
    accident guards."""
    if not (cmd.startswith("/sc ") or cmd.startswith("/silent-command ")):
        return "Lua only: a command is /sc LUA (the toolkit's link sends that)"
    try:
        link.assert_safe(cmd)
    except link.LinkError as exc:
        return str(exc)
    if role != "maintainer":
        for pat, why in GUARDS:
            if pat.search(cmd):
                return why
    return None


def ident(name):
    """An agent's name as a Lua identifier and a unique key: lower case, ``-`` as ``_``."""
    return name.lower().replace("-", "_")


def namespace(cmd, name):
    """``cmd`` with the toolkit's shared names made the caller's own (module docstring)."""
    cmd = re.sub(r"(['\"])fk5/", lambda m: f"{m.group(1)}fk5/{name}/", cmd)
    return re.sub(r"\bstorage\.fk5_bp\b", f"storage.fk5_bp_{ident(name)}", cmd)


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def _write_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


class Keys:
    """The agents (``data/agents.json``): name -> {sha256, role, contact, created, address,
    disabled}. A key is shown once, at registration; only its hash is kept. The file is read
    again when it changes, so the ``keys`` command works on a running gateway."""

    def __init__(self, path, cfg):
        self.path, self.cfg = path, cfg
        self.lock = threading.Lock()
        self.mtime, self.agents, self.by_hash = None, {}, {}
        self.recent = collections.defaultdict(collections.deque)     # address -> register times

    def _load(self):
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            mtime = None
        if mtime != self.mtime or mtime is None:
            self.agents = _read_json(self.path, {}).get("agents", {}) if mtime else {}
            self.by_hash = {row["sha256"]: n for n, row in self.agents.items()}
            self.mtime = mtime

    def _save(self):
        _write_json(self.path, {"agents": self.agents})
        self.mtime = os.path.getmtime(self.path)

    def who(self, key):
        """-> (name, row) of a live key, else None."""
        with self.lock:
            self._load()
            name = self.by_hash.get(hashlib.sha256((key or "").encode()).hexdigest())
            row = self.agents.get(name)
            return (name, row) if row and not row.get("disabled") else None

    def add(self, name, contact="", address="", role="visitor"):
        """A new agent -> its key. ``GatewayError`` for a bad or taken name."""
        if not NAME.match(name or ""):
            raise GatewayError(400, "a name is 3-32 of A-Z a-z 0-9 _ - and starts with a letter "
                                    "or a digit")
        with self.lock:
            self._load()
            if any(ident(n) == ident(name) for n in self.agents):
                raise GatewayError(409, f"the name {name} is taken")
            key = secrets.token_hex(20)
            self.agents[name] = {"sha256": hashlib.sha256(key.encode()).hexdigest(), "role": role,
                                 "contact": str(contact)[:200], "address": address,
                                 "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            self.by_hash[self.agents[name]["sha256"]] = name
            self._save()
            return key

    def register(self, name, contact, address):
        """Open registration: ``add`` behind the config's limits."""
        reg = self.cfg["register"]
        if not reg.get("open"):
            raise GatewayError(403, "registration is closed: ask the host for a key")
        now = time.time()
        with self.lock:
            self._load()
            if len(self.agents) >= reg["max_agents"]:
                raise GatewayError(403, "the gateway has all the agents it takes for now")
            times = self.recent[address]
            while times and now - times[0] > 3600:
                times.popleft()
            if len(times) >= reg["per_address_per_hour"]:
                raise GatewayError(429, "too many registrations from this address: try in an hour")
        key = self.add(name, contact, address)
        with self.lock:
            self.recent[address].append(now)             # only a name that was given counts
        return key

    def set(self, name, **fields):
        with self.lock:
            self._load()
            if name not in self.agents:
                raise GatewayError(404, f"no agent {name}")
            self.agents[name].update(fields)
            self._save()


class Save:
    """One shared save: its RCON (one connection, one call at a time), its files, its health."""

    def __init__(self, name, cfg, gw):
        self.name, self.cfg, self.gw = name, cfg, gw
        self.lock = threading.Lock()
        self.rcon = self.probe_rcon = None
        self.health = {"ok": None, "tick": None, "players": None, "paused": None, "at": None}
        self.fails, self.restarted, self.announce = 0, 0.0, None
        self.touched = time.time()                       # the last agent call (or the start)
        self.last_backup, self.backed_mtime = 0.0, None
        self.active = {}                                 # agent -> time of its last call

    def _open(self, timeout=None):
        return link.Rcon(self.cfg.get("rcon_host", "127.0.0.1"), int(self.cfg["rcon_port"]),
                         self.cfg["pw_file"], timeout=timeout or self.gw.cfg["rcon_timeout"])

    def call(self, cmd):
        """The command to the game -> its reply. A failed call drops the connection."""
        with self.lock:
            try:
                if self.rcon is None:
                    self.rcon = self._open()
                return self.rcon.call(cmd)
            except (OSError, link.LinkError):
                self.drop()
                raise

    def drop(self):
        if self.rcon is not None:
            try:
                self.rcon.close()
            except OSError:
                pass
            self.rcon = None

    def drop_probe(self):
        if self.probe_rcon is not None:
            try:
                self.probe_rcon.close()
            except OSError:
                pass
            self.probe_rcon = None

    def out_path(self, rel, name):
        """The file ``rel`` under script-output (``fk5/...``: the caller's own), or None when
        the path leaves it."""
        rel = posixpath.normpath(rel.replace("\\", "/"))
        if not rel or rel.startswith(("/", "..")) or "\0" in rel or ":" in rel:
            return None
        parts = rel.split("/")
        if parts[0] == "fk5":
            parts[1:1] = [name]
        root = os.path.realpath(self.cfg["script_output"])
        full = os.path.realpath(os.path.join(root, *parts))
        return full if full.startswith(root + os.sep) else None

    def newest_save(self):
        """The newest finished save file, or None."""
        folder = self.cfg["saves"]
        best = None
        try:
            names = os.listdir(folder)
        except OSError:
            return None
        for f in names:
            if not f.endswith(".zip") or f.endswith(".tmp.zip"):
                continue
            path = os.path.join(folder, f)
            mtime = os.path.getmtime(path)
            if best is None or mtime > best[0]:
                best = (mtime, path)
        return best and best[1]


class Gateway:
    """The service: config, agents, saves, journal, the keeper thread and the HTTP server."""

    def __init__(self, cfg):
        self.cfg = _merge(DEFAULTS, cfg)
        self.data = self.cfg["data"]
        for sub in ("journal", "board", "claims", "backups"):
            os.makedirs(os.path.join(self.data, sub), exist_ok=True)
        self.keys = Keys(os.path.join(self.data, "agents.json"), self.cfg)
        self.saves = {n: Save(n, c, self) for n, c in self.cfg["saves"].items()}
        self.calls = collections.defaultdict(collections.deque)      # agent -> call times
        self.file_lock = threading.Lock()
        self.stop = threading.Event()
        self.server = None

    # -- journal, board, claims -------------------------------------------------------------------
    def journal(self, save, row):
        row = dict({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, **row)
        folder = os.path.join(self.data, "journal", save)
        with self.file_lock:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, row["t"][:10] + ".jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")

    def journal_tail(self, save, n=50):
        folder = os.path.join(self.data, "journal", save)
        rows = []
        try:
            days = sorted(os.listdir(folder), reverse=True)
        except OSError:
            return rows
        for day in days:
            with self.file_lock, open(os.path.join(folder, day), encoding="utf-8") as fh:
                lines = fh.readlines()
            for ln in reversed(lines):
                try:
                    row = json.loads(ln)
                except ValueError:
                    continue
                if "cmd" in row:
                    row["cmd"] = row["cmd"][:300]
                rows.append(row)
                if len(rows) >= n:
                    return rows[::-1]
        return rows[::-1]

    def board(self, save, since=0.0, n=100):
        path = os.path.join(self.data, "board", f"{save}.jsonl")
        try:
            with self.file_lock, open(path, encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
        except (OSError, ValueError):
            rows = []
        return [r for r in rows if r["at"] > since][-n:]

    def board_add(self, save, name, text):
        text = " ".join(str(text).split())[:500]
        if not text:
            raise GatewayError(400, "a note needs text")
        row = {"at": round(time.time(), 3), "name": name, "text": text}
        with self.file_lock:
            with open(os.path.join(self.data, "board", f"{save}.jsonl"), "a",
                      encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        shown = "".join(c if 32 <= ord(c) < 127 else "?" for c in f"[{name}] {text}")
        try:
            self.saves[save].call("/sc " + link.lua_say(shown))
        except (OSError, link.LinkError):
            pass                                         # the board has it; the chat is a courtesy
        return row

    def claims(self, save):
        return _read_json(os.path.join(self.data, "claims", f"{save}.json"), {})

    def claim(self, save, name, plot, area, note=""):
        if not NAME.match(str(plot or "")):
            raise GatewayError(400, "a plot's name is 3-32 of A-Z a-z 0-9 _ -")
        path = os.path.join(self.data, "claims", f"{save}.json")
        with self.file_lock:
            claims = _read_json(path, {})
            mine = claims.setdefault(name, {})
            if area is None:
                mine.pop(plot, None)
            else:
                try:
                    x0, y0, x1, y1 = (int(v) for v in area)
                except (TypeError, ValueError):
                    raise GatewayError(400, "an area is [x0, y0, x1, y1]") from None
                if x1 <= x0 or y1 <= y0:
                    raise GatewayError(400, "an area is [x0, y0, x1, y1] with x1 > x0 and y1 > y0")
                for other, plots in claims.items():
                    for pn, p in plots.items():
                        a = p["area"]
                        if other != name and x0 < a[2] and a[0] < x1 and y0 < a[3] and a[1] < y1:
                            raise GatewayError(409, f"that overlaps {other}'s plot {pn} at {a}: "
                                                    "pick other ground or ask on the board")
                if len(mine) >= 16 and plot not in mine:
                    raise GatewayError(400, "16 plots an agent: drop one first (area: null)")
                mine[plot] = {"area": [x0, y0, x1, y1], "note": str(note)[:200],
                              "at": round(time.time())}
            if not mine:
                claims.pop(name, None)
            _write_json(path, claims)
        return claims

    # -- the rcon call ------------------------------------------------------------------------------
    def rcon(self, save, name, role, cmd, address=""):
        """One agent's command: rate, guard, name space, game, journal -> the reply."""
        now = time.time()
        times = self.calls[name]
        while times and now - times[0] > 60:
            times.popleft()
        if len(times) >= self.cfg["limits"]["calls_per_min"]:
            raise GatewayError(429, f"{self.cfg['limits']['calls_per_min']} calls a minute at most")
        times.append(now)
        s = self.saves[save]
        why = guard(cmd, role)
        if why:
            self.journal(save, {"who": name, "from": address, "refused": why, "cmd": cmd})
            raise GatewayError(403, f"refused: {why}")
        s.touched = now
        if s.health.get("paused") and s.cfg.get("idle_pause_s"):
            self.pause(s, False, f"{name} called")
        sent = namespace(cmd, name)
        t0 = time.monotonic()
        try:
            reply = s.call(sent)
        except (OSError, link.LinkError) as exc:
            self.journal(save, {"who": name, "from": address, "cmd": cmd,
                                "error": f"{type(exc).__name__}: {exc}",
                                "ms": round((time.monotonic() - t0) * 1000)})
            raise GatewayError(504, f"the game did not answer ({type(exc).__name__}: {exc})") \
                from None
        s.active[name] = now
        self.journal(save, {"who": name, "from": address, "cmd": cmd, "reply": len(reply),
                            "ms": round((time.monotonic() - t0) * 1000)})
        return reply

    # -- the keeper: health, restart, backups, script-output ---------------------------------------
    def probe(self, s):
        """One health read, on a connection of its own that is kept (a hung call holds the
        save's; a new one every probe filled the server's log)."""
        try:
            if s.probe_rcon is None:
                s.probe_rcon = s._open(timeout=10.0)
            got = s.probe_rcon.lua("rcon.print(game.tick .. ' ' .. #game.connected_players .. "
                                   "' ' .. tostring(game.tick_paused))").split()
            s.health = {"ok": True, "tick": int(got[0]), "players": int(got[1]),
                        "paused": got[2:] == ["true"], "at": round(time.time())}
            s.fails = 0
        except (OSError, link.LinkError, ValueError, IndexError):
            s.fails += 1
            s.health = dict(s.health, ok=False)
            s.drop_probe()
        return s.health["ok"]

    def watch(self, s):
        """Probe; restart a server that stopped answering; say so once it is back."""
        wd = self.cfg["watchdog"]
        ok = self.probe(s)
        if ok and s.announce:
            last, s.announce = s.announce, None
            try:
                s.call("/sc " + link.lua_say(
                    f"[gateway] the server stopped answering and was restarted from its last "
                    f"save. The last calls before it were from: {last}"))
            except (OSError, link.LinkError):
                pass
        cmd = s.cfg.get("restart")
        if (not ok and cmd and s.fails >= wd["fails"]
                and time.time() - s.restarted > wd["cooldown_s"]):
            last = ", ".join(dict.fromkeys(
                r.get("who", "?") for r in self.journal_tail(s.name, 5) if "cmd" in r)) or "nobody"
            s.restarted, s.fails = time.time(), 0
            s.drop()
            s.drop_probe()
            try:
                done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                note = f"exit {done.returncode} {done.stderr.strip()[:200]}"
            except (OSError, subprocess.SubprocessError) as exc:
                note = f"{type(exc).__name__}: {exc}"
            self.journal(s.name, {"event": "restart", "why": f"no answer to {wd['fails']} probes",
                                  "last": last, "result": note})
            s.announce = last

    def idle(self, s):
        """Pause a save nobody is at; set it going when a player is there (an agent's call does
        that itself, in ``rcon``)."""
        after = s.cfg.get("idle_pause_s")
        h = s.health
        if not after or not h["ok"]:
            return
        if h["paused"] and h["players"]:
            self.pause(s, False, "a player is in the game")
        elif (not h["paused"] and not h["players"] and time.time() - s.touched > after):
            self.pause(s, True, f"no agent's call for {round(after / 60)} min and no player")

    def pause(self, s, on, why):
        try:
            s.call(f"/sc game.tick_paused = {'true' if on else 'false'} rcon.print('ok')")
        except (OSError, link.LinkError):
            return
        s.health = dict(s.health, paused=on)
        self.journal(s.name, {"event": "paused" if on else "resumed", "why": why})

    def backup(self, s):
        """An hourly copy of the newest save, kept ``keep_days``; only a changed save is copied."""
        b = self.cfg["backups"]
        now = time.time()
        if now - s.last_backup < b["every_s"]:
            return None
        s.last_backup = now
        folder = os.path.join(self.data, "backups", s.name)
        os.makedirs(folder, exist_ok=True)
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if now - os.path.getmtime(path) > b["keep_days"] * 86400:
                os.remove(path)
        src = s.newest_save()
        if not src or os.path.getmtime(src) == s.backed_mtime:
            return None
        dst = os.path.join(folder, time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + ".zip")
        shutil.copyfile(src, dst + ".part")
        os.replace(dst + ".part", dst)
        s.backed_mtime = os.path.getmtime(src)
        return dst

    def sweep(self, s):
        """script-output's answer files: the old ones out, then the oldest until it fits."""
        lim = self.cfg["limits"]
        root = os.path.join(s.cfg["script_output"], "fk5")
        files, now = [], time.time()
        for folder, _dirs, names in os.walk(root):
            for f in names:
                path = os.path.join(folder, f)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if now - st.st_mtime > lim["out_age_s"]:
                    _remove(path)
                else:
                    files.append((st.st_mtime, st.st_size, path))
        total = sum(f[1] for f in files)
        for _mtime, size, path in sorted(files):
            if total <= lim["out_bytes"]:
                break
            _remove(path)
            total -= size

    def keep(self):
        """The keeper thread: every save's watchdog, backup and sweep, until ``stop``."""
        while not self.stop.wait(self.cfg["watchdog"]["every_s"]):
            for s in self.saves.values():
                for job in (self.watch, self.idle, self.backup, self.sweep):
                    try:
                        job(s)
                    except Exception as exc:              # the keeper must outlive any one failure
                        self.journal(s.name, {"event": "keeper-error", "job": job.__name__,
                                              "error": f"{type(exc).__name__}: {exc}"})

    def status(self):
        now = time.time()
        return {"toolkit": __version__, "register": bool(self.cfg["register"].get("open")),
                "saves": {n: {"about": s.cfg.get("about", ""), "factorio": s.cfg.get("factorio"),
                              "ok": s.health["ok"], "tick": s.health["tick"],
                              "paused": s.health["paused"],
                              "players": s.health["players"],
                              "agents_last_hour": sorted(a for a, t in s.active.items()
                                                         if now - t < 3600),
                              "plots": sum(len(p) for p in self.claims(n).values())}
                          for n, s in self.saves.items()}}

    # -- serving ------------------------------------------------------------------------------------
    def serve(self, block=True, poll=0.5):
        host, port = self.cfg["listen"]
        gw = self

        class Handler(_Handler):
            gateway = gw
        self.server = http.server.ThreadingHTTPServer((host, int(port)), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.keep, daemon=True).start()
        if block:
            try:
                self.server.serve_forever(poll)
            finally:
                self.close()
        else:
            threading.Thread(target=self.server.serve_forever, args=(poll,), daemon=True).start()
        return self.server.server_address

    def close(self):
        self.stop.set()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        for s in self.saves.values():
            s.drop()
            s.drop_probe()


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


class _Handler(http.server.BaseHTTPRequestHandler):
    gateway = None
    timeout = 60                                         # a silent client is dropped
    server_version = f"fk-gateway/{__version__}"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # -- plumbing -----------------------------------------------------------------------------------
    def _address(self):
        addr = self.client_address[0]
        if addr in self.gateway.cfg["trust_proxy"]:
            fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            return fwd or addr
        return addr

    def _send(self, code, body, kind="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body, kind = body.encode(), "text/plain; charset=utf-8" if kind == "application/json" \
                else kind
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise GatewayError(400, "bad Content-Length") from None
        if n > self.gateway.cfg["limits"]["body_bytes"]:
            self.close_connection = True
            raise GatewayError(413, f"{self.gateway.cfg['limits']['body_bytes']} bytes a call at "
                                    "most (the toolkit sends a big paste in parts)")
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise GatewayError(400, "the body is JSON") from None
        if not isinstance(data, dict):
            raise GatewayError(400, "the body is a JSON object")
        return data

    def _who(self):
        auth = self.headers.get("Authorization") or ""
        got = self.gateway.keys.who(auth[7:].strip() if auth.startswith("Bearer ") else "")
        if got is None:
            raise GatewayError(401, "unknown key: POST /v1/register {name, contact} gives one "
                                    "(Authorization: Bearer KEY)")
        return got[0], got[1].get("role", "visitor")

    def _route(self, method):
        gw = self.gateway
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        path = urllib.parse.unquote(url.path)
        if method == "GET" and path in ("/", "/index.html"):
            path = "/skill.md"
        if method == "GET" and path.count("/") == 1 and DOC.match(path[1:]):
            docs = gw.cfg.get("docs")
            full = docs and os.path.join(docs, path[1:])
            if not full or not os.path.isfile(full):
                raise GatewayError(404, "no such page")
            with open(full, "rb") as fh:
                return self._send(200, fh.read(), "text/markdown; charset=utf-8")
        if method == "GET" and path == "/v1/status":
            return self._send(200, gw.status())
        if method == "POST" and path == "/v1/register":
            body = self._body()
            name = str(body.get("name") or "")
            key = gw.keys.register(name, body.get("contact") or "", self._address())
            return self._send(200, {"name": name, "key": key, "saves": sorted(gw.saves),
                                    "note": "keep the key: it is shown once"})
        parts = path.strip("/").split("/")
        if len(parts) < 4 or parts[:2] != ["v1", "saves"] or parts[2] not in gw.saves:
            raise GatewayError(404, "no such path (GET / says what is here; the saves: "
                                    + ", ".join(sorted(gw.saves)) + ")")
        name, role = self._who()
        save, verb, rest = parts[2], parts[3], "/".join(parts[4:])
        s = gw.saves[save]
        if method == "GET" and verb == "hello":
            return self._send(200, {"save": save, "factorio": s.cfg.get("factorio"),
                                    "mods": s.cfg.get("mods", ["base"]),
                                    "toolkit": __version__, "you": name, "role": role,
                                    "about": s.cfg.get("about", "")})
        if method == "POST" and verb == "rcon":
            cmd = self._body().get("cmd")
            if not isinstance(cmd, str) or not cmd:
                raise GatewayError(400, 'the body is {"cmd": "/sc LUA"}')
            return self._send(200, {"reply": gw.rcon(save, name, role, cmd, self._address())})
        if method == "GET" and verb == "out" and rest:
            full = s.out_path(rest, name)
            if full is None:
                raise GatewayError(400, "a path under script-output")
            if not os.path.isfile(full):
                return self._send(404, "not there (yet)")
            if query.get("remove") and rest.startswith("fk5/"):
                _remove(full)
                return self._send(200, {"removed": rest})
            return self._file(full)
        if method == "GET" and verb == "save":
            full = s.newest_save()
            if full is None:
                raise GatewayError(404, "no save yet")
            return self._file(full, "application/zip")
        if method == "GET" and verb == "journal":
            n = min(int((query.get("n") or ["50"])[0]), 500)
            return self._send(200, gw.journal_tail(save, n))
        if verb == "board":
            if method == "POST":
                return self._send(200, gw.board_add(save, name, self._body().get("text")))
            return self._send(200, gw.board(save, float((query.get("since") or ["0"])[0])))
        if verb == "claims":
            if method == "POST":
                body = self._body()
                return self._send(200, gw.claim(save, name, body.get("plot") or "main",
                                                body.get("area"), body.get("note") or ""))
            return self._send(200, gw.claims(save))
        raise GatewayError(404, f"no {method} {verb} (hello, rcon, out, save, journal, board, "
                                "claims)")

    def _file(self, full, kind="application/octet-stream"):
        size = os.path.getsize(full)
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(full, "rb") as fh:
            shutil.copyfileobj(fh, self.wfile)

    def _handle(self, method):
        try:
            self._route(method)
        except GatewayError as exc:
            self.close_connection = True              # the request's body may be unread
            self._send(exc.code, exc.text)
        except (ValueError, KeyError) as exc:
            self.close_connection = True
            self._send(400, f"bad request ({type(exc).__name__}: {exc})")
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fkcore.gateway", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--config", required=True)
    ks = sub.add_parser("keys")
    ks.add_argument("--config", required=True)
    ks.add_argument("verb", nargs="?", default="list",
                    choices=("list", "add", "disable", "enable", "role"))
    ks.add_argument("name", nargs="?")
    ks.add_argument("role", nargs="?", choices=("visitor", "maintainer"))
    a = ap.parse_args(argv)
    gw = Gateway(load(a.config))
    if a.cmd == "serve":
        host, port = gw.cfg["listen"]
        print(f"fk-gateway {__version__} on {host}:{port}: saves {', '.join(sorted(gw.saves))}; "
              f"registration {'open' if gw.cfg['register'].get('open') else 'closed'}", flush=True)
        try:
            gw.serve()
        except KeyboardInterrupt:
            pass
        return 0
    try:
        if a.verb == "list":
            gw.keys._load()
            for n, row in sorted(gw.keys.agents.items()):
                print(f"{n:32} {row.get('role', 'visitor'):10} "
                      f"{'DISABLED ' if row.get('disabled') else ''}{row.get('created', '')} "
                      f"{row.get('address', '')} {row.get('contact', '')}")
            print(f"{len(gw.keys.agents)} agents")
        elif not a.name:
            ap.error(f"keys {a.verb} NAME")
        elif a.verb == "add":
            print(gw.keys.add(a.name, contact="added by the host"))
        elif a.verb in ("disable", "enable"):
            gw.keys.set(a.name, disabled=a.verb == "disable")
            print(f"{a.name}: {a.verb}d")
        elif a.verb == "role":
            if not a.role:
                ap.error("keys role NAME visitor|maintainer")
            gw.keys.set(a.name, role=a.role)
            print(f"{a.name}: {a.role}")
    except GatewayError as exc:
        print(f"error: {exc.text}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
