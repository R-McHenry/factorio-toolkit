"""join: join a shared save, as an agent on your own machine (3.4, PLAN-COMMONS).

    git clone https://github.com/R-McHenry/factorio-toolkit && cd factorio-toolkit
    python kickoff/join.py https://HOST/v1/saves/commons --name my-agent --run ~/commons

It asks the save's gateway for a key under NAME (registration is open; ``--contact`` says who
runs the agent, an owner's handle or address), and makes the run folder RUN:

  AGENTS.md            the brief (agent/prompts/commons-v1.md): read it first
  docs/                START.md, EXAMPLES.md, BUILDING.md, STRATEGY.md, FAIR-PLAY.md, TOOLKIT.md,
                       LANGUAGE.md, COMMONS.md
  bin/fk.py            your one command: ``python bin/fk.py <command>`` (fk.cmd on Windows)
  .toolkit/            the toolkit at this commit: the run keeps the version it joined with
  game/                your game codebase: your plot's design (world.fk), the world design that
                       places it (nauvis.fk), the surface file, the build script
  run.json             where the game is: the gateway's URL and your key file
  .gateway-key         your key. It is shown once and kept only here: back it up

``--key-file F`` joins with a key you already have (a second run folder, a new machine) instead
of registering. ``--plot X0,Y0,X1,Y1`` claims that ground as your plot ``main`` at once; without
it, look first (``fk commons claims``, ``fk chart``) and claim with ``fk commons claim``.

Needs git (the run's toolkit is ``git archive`` of this clone) and Python 3.10+. Stdlib only.
Optional, before joining: ``python tools/native_build.py`` builds the Rust router kernel (needs
cargo). The run takes it along, and routing is several times faster with it.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fkcore import commons, link  # noqa: E402
import new_run  # noqa: E402

#: the single-player start's own furniture: on a shared save it is nobody's design. The two
#: layouts go with it: they hold the kit and the plant as the run's own entities, and a build
#: whose design no longer has them would order the shared start taken up (the first rehearsal's
#: first build ordered 14 of its entities out)
NOT_YOURS = ("plant.fk", "kit.fk", "kit.json", "plant-w3.json", "nauvis.fkp", "world.fkp")
KEY_FILE = ".gateway-key"

WORLD = """\
# world.fk: your plot on the shared save. Coordinates here start at your plot's corner: a map
# tile x,y is this file's x-X0, y-Y0, with X0,Y0 the corner nauvis.fk places it at.
#
# The start at spawn (the kit's chests, the roboport and its robots, the reactor) is everyone's:
# it is in nobody's design, and its supplies are shared. Everything you add here is yours.
#
# Build each factory as a sealed module: `module NAME size WxH { ... }` with `port` lines on its
# edges, built alone on your replica first (docs\\BUILDING.md, docs\\COMMONS.md).
"""

NAUVIS = """\
# nauvis.fk: the world design, your part of it. One plot: the ground you claimed on the shared
# save (`fk commons claim main X0,Y0,X1,Y1` rewrites the line below). Outside it the map is other
# agents' and the shared start's: `fk commons claims` lists who has what.
import World from "world.fk"

world = World @({x}, {y}) size {w}x{h}{note}
"""


def plot_line(area):
    """nauvis.fk for the plot ``area`` (x0, y0, x1, y1), or the unclaimed placeholder."""
    if area is None:
        return NAUVIS.format(x=0, y=0, w=64, h=64, note="    # not claimed yet: fk commons claim")
    x0, y0, x1, y1 = area
    return NAUVIS.format(x=x0, y=y0, w=x1 - x0, h=y1 - y0, note="")


def shape_game(game, area=None):
    """The template's game folder as one agent's part of a shared world."""
    for name in NOT_YOURS:
        path = os.path.join(game, name)
        if os.path.exists(path):
            os.remove(path)
    for name, text in (("world.fk", WORLD), ("nauvis.fk", plot_line(area))):
        with open(os.path.join(game, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    path = os.path.join(game, "nauvis.surface")
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    head = ["# nauvis.surface: the shared save's surface, as your run sees it. Your plot is in",
            "# nauvis.fk; `terrain map` is map.terrain.json, which `fk read-terrain` writes for",
            "# your plot (docs\\COMMONS.md)."]
    body = [ln for ln in lines if not ln.startswith("#")]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(head + body) + "\n")


def join(url, name, run, contact="", key_file=None, area=None, sha="HEAD", log=print):
    """Register (or take ``key_file``'s key), make the run folder -> its run.json dict."""
    url = url.rstrip("/")
    commons.root(url)                                    # a save's URL, or CommonsError
    run = os.path.abspath(os.path.expanduser(run))
    if os.path.exists(run) and os.listdir(run):
        raise commons.CommonsError(f"{run} exists and is not empty")
    if key_file:
        with open(os.path.expanduser(key_file), encoding="utf-8") as fh:
            key = fh.read().strip()
    else:
        key = commons.register(url, name, contact)
        log(f"join: registered as {name}")
    try:
        with link.Relay(url, key, timeout=30) as r:
            hello = r.hello
    except (OSError, link.LinkError):
        if not key_file:
            log(f"join: your key is {key} (keep it: the gateway shows it once)")
        raise
    cfg = new_run.make(run, prompt="commons-v1", sha=sha,
                       local={"FK_LINK": "gateway", "FK_GATEWAY": url,
                              "FK_GATEWAY_KEY_FILE": KEY_FILE})
    path = os.path.join(run, KEY_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(key + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    shape_game(os.path.join(run, "game"), area)
    for kernel in ("fkroute.so", "fkroute.pyd"):         # this clone's own router kernel, if built
        src = os.path.join(new_run.ROOT, kernel)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(run, ".toolkit", kernel))
            log(f"join: the native router kernel ({kernel}) goes with the run")
    if area is not None:
        commons.claim("main", list(area), url=url, key=key)
        log(f"join: plot main claimed at {area[0]},{area[1]},{area[2]},{area[3]}")
    log(f"join: {hello['you']} on save {hello['save']} (Factorio {hello.get('factorio')}, "
        f"gateway toolkit {hello.get('toolkit')}); your run folder is {run}")
    log(f"join: read {os.path.join(run, 'AGENTS.md')} first; your command is "
        f"python {os.path.join(run, 'bin', 'fk.py')}")
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url", help="the shared save: https://HOST/v1/saves/NAME")
    ap.add_argument("--name", required=True, help="your agent's name on the save (3-32 of "
                    "A-Z a-z 0-9 _ -)")
    ap.add_argument("--run", required=True, help="the run folder to make")
    ap.add_argument("--contact", default="", help="who runs this agent (a handle or an address)")
    ap.add_argument("--key-file", help="join with this key instead of registering")
    ap.add_argument("--plot", help="X0,Y0,X1,Y1: claim this ground as your plot now")
    ap.add_argument("--sha", default="HEAD")
    a = ap.parse_args(argv)
    area = None
    if a.plot:
        try:
            area = tuple(int(v) for v in a.plot.split(","))
            assert len(area) == 4 and area[2] > area[0] and area[3] > area[1]
        except (ValueError, AssertionError):
            ap.error("--plot X0,Y0,X1,Y1 with X1 > X0 and Y1 > Y0")
    try:
        join(a.url, a.name, a.run, a.contact, a.key_file, area, a.sha)
    except (commons.CommonsError, link.LinkError, OSError) as exc:
        print(f"join: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
