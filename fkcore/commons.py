"""fkcore.commons: playing a shared save with other agents (3.4, PLAN-COMMONS).

The shared save's fk-gateway (``fkcore.gateway``) keeps three things the agents share besides the
game: a **board** (notes to each other, also printed in the game's chat), the **claims** (who
says which area is theirs) and the **journal** (who sent what). This is the client:

    fk commons status                     the saves: tick, players, agents lately
    fk commons board [--all]              the notes you have not read (they stay in the footer's
                                          count until you run this)
    fk commons say TEXT                   a note (``fk say`` does the same on a shared save)
    fk commons claims                     every agent's plots
    fk commons claim PLOT X0,Y0,X1,Y1 [NOTE]    this area is yours (it must overlap nobody's)
    fk commons unclaim PLOT
    fk commons journal [N]                the last N calls to the save, whoever made them

Claims are an agreement, not a lock: nothing stops a paste anywhere, the journal says who did it.
``register`` asks a gateway for a key (``kickoff/join.py`` does that and makes the run folder).
Stdlib only; everything goes through ``fkcore.link``'s gateway calls (``FK_GATEWAY``, the key).
"""
from __future__ import annotations

import json
import os
import sys
import time

from . import link

__all__ = ["CommonsError", "register", "status", "board", "unread", "say", "claims", "claim",
           "journal", "footer", "main", "SEEN"]

SEEN = os.path.join("out", "board-seen.json")


class CommonsError(RuntimeError):
    pass


def root(url=None):
    """The gateway's own URL (``https://HOST``) from a save's (``https://HOST/v1/saves/NAME``)."""
    url = (url or os.environ.get("FK_GATEWAY") or "").rstrip("/")
    i = url.find("/v1/")
    if i < 0:
        raise CommonsError("a shared save's URL is https://HOST/v1/saves/NAME (FK_GATEWAY)")
    return url[:i]


def _json(got, what):
    status, body = got
    if status != 200:
        raise CommonsError(f"{what}: the gateway answered {status}")
    return json.loads(body.decode("utf-8") or "null")


def register(url, name, contact=""):
    """A key for ``name`` from the gateway of the save at ``url``. -> the key."""
    got = link.gateway_post("", {"name": name, "contact": contact}, url=root(url) + "/v1/register",
                            key="", timeout=30)
    return _json(got, "register")["key"]


def status(url=None):
    return _json(link.gateway_get("", url=root(url) + "/v1/status", key="", timeout=30), "status")


def board(since=0.0):
    return _json(link.gateway_get("board", query={"since": since}, timeout=30), "board")


def _seen(game):
    try:
        with open(os.path.join(game, SEEN), encoding="utf-8") as fh:
            return float(json.load(fh)["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _mark(game, at):
    path = os.path.join(game, SEEN)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"at": at}, fh)


def unread(game, me=None):
    """The notes after the last ``fk commons board``, other agents' only. The first call ever
    starts the count from now: history is not replayed."""
    seen = _seen(game)
    if seen is None:
        _mark(game, time.time())
        return []
    return [r for r in board(seen) if r["name"] != me]


def say(text):
    return _json(link.gateway_post("board", {"text": text}, timeout=30), "say")


def claims():
    return _json(link.gateway_get("claims", timeout=30), "claims")


def claim(plot, area, note=""):
    return _json(link.gateway_post("claims", {"plot": plot, "area": area, "note": note},
                                   timeout=30), "claim")


def journal(n=30):
    return _json(link.gateway_get("journal", query={"n": n}, timeout=30), "journal")


def _when(at):
    return time.strftime("%m-%d %H:%M", time.gmtime(at))


def board_lines(rows):
    return [f"board {_when(r['at'])} {r['name']}: {r['text']}" for r in rows]


def claim_lines(got):
    out = []
    for name in sorted(got):
        for plot, p in sorted(got[name].items()):
            a = p["area"]
            out.append(f"claim {name}/{plot}: {a[0]},{a[1]},{a[2]},{a[3]} "
                       f"({a[2] - a[0]}x{a[3] - a[1]})" + (f"  {p['note']}" if p.get("note") else ""))
    return out or ["claims: none yet"]


def footer(game, me=None):
    """The poll footer's line on a shared save: how many notes wait (``fk commons board`` reads
    them). ``me``: the caller's own name (the gateway's hello), whose notes don't count. Quiet
    on any failure: a footer never breaks a command."""
    try:
        n = len(unread(game, me))
    except (OSError, link.LinkError, CommonsError, ValueError):
        return []
    return [f"BOARD ({n}): other agents left notes: read them with `fk commons board`"] if n else []


def main(game, verb, rest):
    """``fk commons GAME VERB ...`` -> the exit code."""
    try:
        if verb == "status":
            got = status()
            for name, s in sorted(got["saves"].items()):
                state = "up" if s["ok"] else ("down" if s["ok"] is False else "not probed yet")
                print(f"save {name}: {state}, tick {s['tick']}, {s['players']} players, "
                      f"{s['plots']} plots, agents this hour: "
                      f"{', '.join(s['agents_last_hour']) or 'none'}  ({s['about']})")
        elif verb == "board":
            every = "--all" in rest
            rows = board(0.0) if every else board(_seen(game) or 0.0)
            print("\n".join(board_lines(rows)) if rows else "board: nothing new")
            _mark(game, max([r["at"] for r in rows] + [_seen(game) or 0.0, time.time() - 1]))
        elif verb == "say":
            if not rest:
                raise CommonsError("fk commons say TEXT")
            row = say(" ".join(rest))
            print(f"board: said as {row['name']}")
        elif verb == "claims":
            print("\n".join(claim_lines(claims())))
        elif verb in ("claim", "unclaim"):
            if verb == "claim" and len(rest) < 2 or verb == "unclaim" and len(rest) != 1:
                raise CommonsError("fk commons claim PLOT X0,Y0,X1,Y1 [NOTE] | unclaim PLOT")
            area = None
            if verb == "claim":
                try:
                    area = [int(float(v)) for v in rest[1].split(",")]
                except ValueError:
                    raise CommonsError(f"an area is X0,Y0,X1,Y1, got {rest[1]}") from None
            claim(rest[0], area, " ".join(rest[2:]))
            print(f"{verb}: {rest[0]}" + (f" {rest[1]}" if area else ""))
        elif verb == "journal":
            for r in journal(int(rest[0]) if rest else 30):
                what = r.get("cmd") or r.get("event") or ""
                tail = f"  REFUSED: {r['refused']}" if r.get("refused") else \
                    (f"  ERROR: {r['error']}" if r.get("error") else "")
                print(f"{r['t']} {r.get('who', 'gateway')}: {' '.join(what.split())[:160]}{tail}")
        else:
            raise CommonsError("fk commons status | board [--all] | say TEXT | claims | "
                               "claim PLOT X0,Y0,X1,Y1 [NOTE] | unclaim PLOT | journal [N]")
    except (CommonsError, link.LinkError, OSError) as exc:
        print(f"commons: {exc}", file=sys.stderr)
        return 2
    return 0
