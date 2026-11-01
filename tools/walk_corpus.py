"""walk_corpus: the net walker (fkcore.walk) on real bases, each on its own laptop server (3.0).

    python tools/walk_corpus.py SAVE.zip OUT_DIR [--mods space-age,quality,elevated-rails]
                                [--surface nauvis] [--radius 32] [--at=X,Y ...]

Loads the save on a laptop server (never the host), reads where the machines are and what state
they are in (one census call), picks roots: a smelter, a circuit build, a science assembler, a
starved assembler, a lab, a drill (or the --at points), and walks each: one read of the square
around it (timed: a game call stays under 5 s), the tree (--up 3 --down 1), kept as
OUT_DIR/<root>.json (the read) and .txt (the walk). OUT_DIR/census.json and walks.txt sum it up.
Saves are untrusted: their scenario runs on load, which is why this is the laptop's server.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fkcore import link, walk  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402
from laptop_server import LaptopServer  # noqa: E402

CENSUS = """
local s = game.get_surface({surface})
if not s then rcon.print('no surface') return end
local st = {{}}
for k, v in pairs(defines.entity_status) do st[v] = k end
local out = {{}}
for _, e in pairs(s.find_entities_filtered{{type = {{'assembling-machine', 'furnace', 'lab', 'mining-drill', 'rocket-silo'}}}}) do
  local r = nil
  if e.type == 'assembling-machine' or e.type == 'furnace' or e.type == 'rocket-silo' then
    local ok, x = pcall(e.get_recipe)
    if ok and x then r = x.name end
  end
  local ok, v = pcall(function() return e.status end)
  out[#out + 1] = {{n = e.name, t = e.type, x = e.position.x, y = e.position.y, r = r, s = ok and v and st[v] or nil}}
end
helpers.write_file('fk5/{tag}.json', helpers.table_to_json({{tick = game.tick, m = out}}), false)
rcon.print(#out)
"""


def census(r, surface):
    tag = f"census-{os.getpid()}"
    return link.read_output(r, CENSUS.format(surface=json.dumps(surface), tag=tag), tag, "census",
                            keep=False)


def _dense(ms, x, y, r=20):
    return sum(1 for m in ms if abs(m[2] - x) <= r and abs(m[3] - y) <= r)


def pick(ms):
    """[(label, x, y)]: one root per kind, in the densest spot each kind has."""
    ms = [(m["n"], m["t"], m["x"], m["y"], m.get("r"), m.get("s")) for m in ms]
    def best(pred):
        c = [m for m in ms if pred(m)]
        if not c:
            return None
        return max(c, key=lambda m: (_dense(ms, m[2], m[3]), -abs(m[2]) - abs(m[3])))
    kinds = [
        ("smelter", lambda m: m[1] == "furnace" and m[4] in ("iron-plate", "copper-plate")),
        ("circuit", lambda m: m[4] == "electronic-circuit"),
        ("science", lambda m: m[4] and m[4].endswith("science-pack")
         and m[4] != "automation-science-pack"),
        ("red-science", lambda m: m[4] == "automation-science-pack"),
        ("starved", lambda m: m[1] == "assembling-machine" and m[5] in walk.STARVED),
        ("blocked", lambda m: m[1] == "assembling-machine" and m[5] in walk.BLOCKED),
        ("lab", lambda m: m[1] == "lab"),
        ("drill", lambda m: m[1] == "mining-drill"),
    ]
    out, used = [], set()
    for label, pred in kinds:
        m = best(pred)
        if m and (m[2], m[3]) not in used:
            used.add((m[2], m[3]))
            out.append((label, m[2], m[3]))
    return out


def walk_text(label, x, y, dump, cat, took=0.0):
    """The walk of one kept read, as lines (the .txt)."""
    t = time.time()
    w = walk.infer(dump, cat)
    root = walk.find_root(w, f"{x},{y}")
    lines = walk.summary(w)
    body = walk.tree(w, root, 3, 1) if root else ["no root"]
    head = [ln for ln in lines if not ln.startswith("n") and not ln.startswith("f")]
    nets = [ln for ln in lines if ln not in head]
    return ([f"# {label} at {x},{y}: read {took:.2f} s ({len(dump['rows'])} rows), "
             f"walk {time.time() - t:.2f} s"] + head + [""] + body + ["", "## nets"] + nets)


def rewalk(out):
    """Walk every kept read in ``out`` again (no game): after a change to fkcore.walk."""
    cat = Catalog.load()
    for path in sorted(os.listdir(out)):
        if not path.endswith(".json") or path == "census.json":
            continue
        with open(os.path.join(out, path), encoding="utf-8") as fh:
            dump = json.load(fh)
        x, y = dump.get("walk", {}).get("at") or _centre(dump["area"])
        text = walk_text(path[:-5], x, y, dump, cat)
        with open(os.path.join(out, path[:-5] + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(text) + "\n")
        print(text[0])


def _centre(area):
    rad = (area[2] - area[0] - 1) // 2
    return area[0] + rad + 0.5, area[1] + rad + 0.5


def main(argv=None):
    if argv is None and len(sys.argv) == 3 and sys.argv[1] == "--rewalk":
        rewalk(sys.argv[2])
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("out")
    ap.add_argument("--mods", default="", help="space-age,quality,elevated-rails (default none)")
    ap.add_argument("--surface", default="nauvis")
    ap.add_argument("--radius", type=int, default=32)
    ap.add_argument("--at", action="append", default=[],
                    help="a root, repeated: --at=X,Y (the = keeps a negative X off the options)")
    ap.add_argument("--settle", type=float, default=3.0, help="seconds to let the map run first")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    cat = Catalog.load()
    mods = tuple(m for m in a.mods.split(",") if m)
    name = "walk-" + os.path.splitext(os.path.basename(a.save))[0][:24]
    summary = []
    t0 = time.time()
    with LaptopServer(name, save=os.path.abspath(a.save), mods=mods, boot_s=180) as srv:
        summary.append(f"server up in {time.time() - t0:.1f} s")
        with srv.rcon() as r:
            r.lua("game.tick_paused = false rcon.print(1)")
            time.sleep(a.settle)
            t = time.time()
            c = census(r, a.surface)
            summary.append(f"census: {len(c['m'])} machines at tick {c['tick']}, "
                           f"{time.time() - t:.2f} s")
            with open(os.path.join(a.out, "census.json"), "w", encoding="utf-8") as fh:
                json.dump(c, fh)
            roots = pick(c["m"])
            for i, xy in enumerate(a.at):
                x, y = (float(v) for v in xy.split(","))
                roots.append((f"at{i + 1}", x, y))
            for label, x, y in roots:
                rad = a.radius
                area = (int(x) - rad, int(y) - rad, int(x) + rad + 1, int(y) + rad + 1)
                t = time.time()
                try:
                    dump = walk.read(r, a.surface, area)
                except (link.LinkError, OSError) as exc:
                    summary.append(f"{label} {x},{y}: read failed: {exc}")
                    continue
                took = time.time() - t
                dump["walk"] = {"at": [x, y], "label": label, "save": os.path.basename(a.save)}
                with open(os.path.join(a.out, f"{label}.json"), "w", encoding="utf-8") as fh:
                    json.dump(dump, fh)
                text = walk_text(label, x, y, dump, cat, took)
                head = text[1:4]
                with open(os.path.join(a.out, f"{label}.txt"), "w", encoding="utf-8") as fh:
                    fh.write("\n".join(text) + "\n")
                summary.append(text[0])
                summary += ["  " + h for h in head]
    summary.append(f"total {time.time() - t0:.1f} s")
    with open(os.path.join(a.out, "walks.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(summary) + "\n")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
