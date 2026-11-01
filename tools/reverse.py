"""reverse: a published blueprint into fk designs, the first rungs of PLAN-3.0 §3g (3.0).

    python tools/reverse.py POST.json "LABEL SUBSTRING" OUT_DIR [--furnace-recipe iron-plate]

Takes one blueprint out of a factorioprints post (a book's page whose label holds the
substring), and builds it four ways with the toolkit's own build (offline, no game: elaborate,
place, route, write_layout), each in its own game folder under OUT_DIR:

- ``literal``: the whole blueprint as one ``Literal``: exact at once, understood not at all;
- ``held``: each machine a ``Machine`` (or ``Lab``, ``Chest``) at its place, the nets the walker
  infers from the entities (fkcore.walk, the same inference as on a live base), the belts and
  inserters of each net held as the original (a ``held`` net file), the belts where a net enters
  or leaves the blueprint as one-belt Literals with a named belt;
- ``seeded``: the same, each net seeded with its original inserters, the router lays the belts;
- ``routed``: the same with nothing held: the router lays every net.

Each build's layout is scored against the original, entity by entity (``score``): machines
exact / moved or other / missing, carriers (belts, undergrounds, splitters, inserters, pipes)
exact / other carriers on its tiles / missing, and what the build added. Poles, lamps and
combinators are counted apart (power is its own step). OUT_DIR/score.txt has the table and each
rung's own route and check lines. Pre-2.0 blueprints are read as the game reads them: directions
doubled, renamed prototypes renamed.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import sys
import time
import zlib
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from fkcore import design, fkp, flow, walk  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402

CAT = Catalog.load()
MARGIN = 6
#: 1.x names the 2.0 game renames on import
RENAME = {"stack-inserter": "bulk-inserter", "filter-inserter": "fast-inserter",
          "stack-filter-inserter": "bulk-inserter",
          "logistic-chest-passive-provider": "passive-provider-chest",
          "logistic-chest-active-provider": "active-provider-chest",
          "logistic-chest-requester": "requester-chest", "logistic-chest-storage": "storage-chest",
          "logistic-chest-buffer": "buffer-chest"}
MACHINES = walk.MACHINE_KINDS
CARRIERS = fkp.CARRIER_TYPES
SCRIPT = """read_surface    nauvis
read_terrain    none
elaborate
place           --keep pinned
route           --only stale --retry-failed changed --failed keep --effort normal --group-budget 10 --hand any
report_checks
write_layout
stop_on         invariant
"""


def blueprints(post):
    """[(label, version, entities)] of a factorioprints post JSON."""
    s = post["blueprintString"]
    doc = json.loads(zlib.decompress(base64.b64decode(s[1:])))
    out = []

    def walk_(o):
        if "blueprint_book" in o:
            for b in o["blueprint_book"].get("blueprints", []):
                walk_(b)
        elif "blueprint" in o:
            bp = o["blueprint"]
            out.append((bp.get("label", ""), bp.get("version", 0), bp.get("entities", [])))
    walk_(doc)
    return out


def normalise(version, ents):
    """-> [{name, x, y, direction, recipe?, ug?}] as 2.0 has them, top-left tile at 0,0, and the
    names the catalog doesn't know."""
    major = (version >> 48) & 0xffff
    rows, unknown = [], set()
    for e in ents:
        name = RENAME.get(e["name"], e["name"])
        if not CAT.has_entity(name):
            unknown.add(name)
            continue
        d = int(e.get("direction") or 0) * (2 if major < 2 else 1)
        row = {"name": name, "x": e["position"]["x"], "y": e["position"]["y"], "direction": d}
        if e.get("recipe"):
            row["recipe"] = RENAME.get(e["recipe"], e["recipe"])
        if CAT.kind(name) == "underground-belt":
            row["ug"] = {"input": "in", "output": "out"}.get(e.get("type"), "in")
        rows.append(row)
    # some pre-2.0 strings put every centre half a tile up-left (a 1x1 at a whole number)
    ones = [r for r in rows if _size(r) == (1, 1)]
    if ones and sum(r["x"] % 1 == 0 for r in ones) > len(ones) / 2:
        for r in rows:
            r["x"], r["y"] = r["x"] + 0.5, r["y"] + 0.5
    x0 = min(math.floor(r["x"] - _size(r)[0] / 2) for r in rows)
    y0 = min(math.floor(r["y"] - _size(r)[1] / 2) for r in rows)
    for r in rows:
        r["x"], r["y"] = r["x"] - x0, r["y"] - y0
    return rows, sorted(unknown)


def _size(r):
    w, h = CAT.size(r["name"])
    return (h, w) if r.get("direction", 0) in (4, 12) else (w, h)


def as_dump(rows, at=0):
    """A walker read of entity rows (no live state): the same inference as on a live base."""
    out = []
    for i, r in enumerate(rows):
        w, h = _size(r)
        x, y = r["x"] + at, r["y"] + at
        row = {"n": r["name"], "t": CAT.kind(r["name"]), "x": x, "y": y, "d": r["direction"],
               "u": i, "box": [x - w / 2, y - h / 2, x + w / 2, y + h / 2]}
        if r.get("recipe"):
            row["rc"] = r["recipe"]
        if r.get("ug"):
            row["ug"] = {"in": "input", "out": "output"}[r["ug"]]
        out.append(row)
    return {"rows": out, "area": None, "protos": {}, "recipes": {}}


# -- the design of a rung ------------------------------------------------------------------------
def _num(v):
    v = float(v)
    return int(v) if v.is_integer() else v


def design_rung(rows, w, rung, furnace_recipe, gdir):
    """-> (main.fk text, {net: [fkp.Entity]} to hold, {net: [Entity]} to seed, notes)."""
    notes = []
    if rung == "literal":
        with open(os.path.join(gdir, "piece.json"), "w", encoding="utf-8") as fh:
            json.dump({"entities": rows}, fh)
        return f'blk = Literal<file="piece.json"> @({MARGIN}, {MARGIN})\n', {}, {}, notes
    lines, inst = [], {}
    k = 0
    for key, e in w.ents.items():
        kind = e.row["t"]
        if kind not in MACHINES:
            continue
        k += 1
        name = f"m{k}"
        w_, h_ = (abs(e.row["box"][2] - e.row["box"][0]), abs(e.row["box"][3] - e.row["box"][1]))
        tx, ty = math.floor(e.x - w_ / 2 + 0.01), math.floor(e.y - h_ / 2 + 0.01)
        if kind in ("assembling-machine", "furnace", "chemical-plant", "oil-refinery"):
            rc = e.row.get("rc")
            if not rc and kind == "furnace":
                rc = furnace_recipe
                notes.append(f"{name}: a blueprint furnace has no recipe; took {rc}")
            if not rc:
                notes.append(f"{name} {e.name}: no recipe in the blueprint, left out")
                continue
            lines.append(f"{name} = Machine<entity={e.name}, recipe={rc}> @({tx}, {ty})")
        elif kind == "lab":
            lines.append(f"{name} = Lab @({tx}, {ty})")
            if e.name != "lab":
                notes.append(f"{name}: {e.name} as a plain lab")
        elif kind in ("container", "logistic-container"):
            lines.append(f"{name} = Chest<plain> @({tx}, {ty})")
            notes.append(f"{name}: {e.name} as Chest<plain> (an iron chest)")
        else:
            notes.append(f"{name}: {e.name} ({kind}) has no kind here, left out")
            continue
        inst[key] = name
    # the belts where a net enters or leaves the blueprint: one-belt Literals with a named belt
    held, seeds, edge = {}, {}, {}
    nets = []
    ne = 0
    for nname, net in sorted(w.nets.items(), key=lambda kv: fkp._natural_key(kv[0])):
        if net.fluid:
            notes.append(f"{nname}: a fluid net, left out")
            continue
        drv = [inst[d] for d in net.drivers if d in inst]
        con = [inst[c] for c in net.consumers if c in inst]
        if not drv and not con:
            continue
        g = w.graph
        if not drv:
            heads = [c for c in net.carriers if not g.pred.get(c)]
            for hk in heads[:2]:
                ne += 1
                lit = _edge_lit(w, hk, f"e{ne}", gdir, lines, edge, True, notes)
                if lit:
                    drv.append(lit)
        if not con:
            tails = [c for c in net.carriers if not g.succ.get(c)]
            for tk in tails[:2]:
                ne += 1
                lit = _edge_lit(w, tk, f"e{ne}", gdir, lines, edge, False, notes)
                if lit:
                    con.append(lit)
        if not drv or not con:
            notes.append(f"{nname}: no end the language can name on one side, left out")
            continue
        # an edge-fed net carries what its consumers take that nothing in the piece makes
        made_here = {p for k_ in inst for p in walk._products(w.ents[k_], {}, CAT)}
        items = sorted(set(net.wanted) - made_here)
        itxt = f" items {', '.join(items)}" if items and drv[0].startswith("e") else ""
        nets.append(f"net {nname}{itxt}: {', '.join(dict.fromkeys(drv))} -> "
                    f"{', '.join(dict.fromkeys(con))}")
        hands = sorted({v for m, lst in w.ins.items() for n_, v in lst if n_ == nname} |
                       {v for m, lst in w.outs.items() for n_, v in lst if n_ == nname})
        mine = [c for c in net.carriers if c not in edge] + hands
        held[nname] = [_entity(w, c, nname, i) for i, c in enumerate(mine)]
        # fk seed pins belts, undergrounds and splitters only (an inserter is refused): seed the
        # net's own splitters and undergrounds
        pins = [c for c in net.carriers if c not in edge and g.nodes[c].kind in
                ("splitter", "underground-belt")]
        if pins:
            seeds[nname] = [_entity(w, c, nname, i, "p") for i, c in enumerate(pins)]
    # hand links machine -> machine
    nh = 0
    for m, lst in w.outs.items():
        for n_, v in lst:
            if n_.startswith("hand:") and m in inst and n_[5:] in inst:
                nh += 1
                hn = f"h{nh}"
                nets.append(f"net {hn}: {inst[m]} -> {inst[n_[5:]]}")
                held[hn] = [_entity(w, v, hn, 0)]
    text = "\n".join(lines) + "\n\n" + "\n".join(nets) + "\n"
    return text, held, seeds, notes


def _edge_lit(w, key, name, gdir, lines, edge, head, notes):
    """A Literal of the belts where a net enters (``head``) or leaves the piece, named at its
    first plain belt: only a belt can be a named net end, so a splitter or an underground at
    the edge goes into the Literal with the belts up to the first plain one."""
    g = w.graph
    chain, k = [key], key
    while g.nodes[k].kind != "transport-belt" and len(chain) < 6:
        nxt = [b for b, v in (g.succ if head else g.pred).get(k, ()) if b in w.net_of
               and b not in chain]
        if not nxt:
            break
        k = nxt[0]
        chain.append(k)
    if g.nodes[k].kind != "transport-belt":
        notes.append(f"{name}: no plain belt near the edge at {key} to name")
        return None
    if len(chain) > 1:
        notes.append(f"{name}: the edge {g.nodes[key].kind} {key} can't be a named end; the "
                     f"Literal takes {len(chain)} carriers and names {k}")
    ents = [w.ents[c] for c in chain]
    x0 = min(math.floor(e.row["box"][0] + 0.01) for e in ents)
    y0 = min(math.floor(e.row["box"][1] + 0.01) for e in ents)
    rows = []
    for e in ents:
        row = {"name": e.name, "x": _num(e.x - x0), "y": _num(e.y - y0), "direction": e.dir}
        if e.attrs.get("ug"):
            row["ug"] = e.attrs["ug"]
        rows.append(row)
        edge[e.key] = name
    with open(os.path.join(gdir, f"{name}.json"), "w", encoding="utf-8") as fh:
        json.dump({"entities": rows, "names": {"b": len(chain) - 1}}, fh)
    lines.append(f'{name} = Literal<file="{name}.json"> @({x0}, {y0})')
    return f"{name}.b"


def _entity(w, key, net, i, pre="h"):
    e = w.ents[key]
    attrs = {"net": net}
    if e.attrs.get("ug"):
        attrs["ug"] = e.attrs["ug"]
    return fkp.Entity(f"~{net}/{pre}{i}", e.name, _num(e.x), _num(e.y), e.dir, attrs)


# -- build and score ------------------------------------------------------------------------------
def build(gdir, fk_text, held, seeds, size):
    with open(os.path.join(gdir, "main.fk"), "w", encoding="utf-8") as fh:
        fh.write(fk_text)
    with open(os.path.join(gdir, "nauvis.surface"), "w", encoding="utf-8") as fh:
        fh.write("surface nauvis\nmode play\nterrain none\ncatalog base\n"
                 f"place main = main plot 0,0 {size[0]}x{size[1]}\n")
    script = os.path.join(gdir, "nauvis.build.fkb")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(SCRIPT)
    out = os.path.join(gdir, "out")
    for net, ents in held.items():
        design.write_net(out, "main", net, "held", ents)
    for net, ents in seeds.items():
        design.write_net(out, "main", net, "unrouted", [], "seeded by reverse.py")
        design.seed(out, "main", net, ents)
    log = []
    t = time.time()
    code, _ctx = flow.run(script, cat=CAT, echo=log.append, to="write_layout")
    took = time.time() - t
    lay = None
    path = os.path.join(gdir, "main.fkp")
    if os.path.exists(path):
        lay = fkp.load(path)
    return code, took, lay, log


def score(rows, lay):
    """{category: {exact, other, missing}} plus extra: the original against the layout."""
    want = []
    for r in rows:
        want.append((r["name"], r["x"] + MARGIN, r["y"] + MARGIN, r.get("direction", 0),
                     r.get("ug")))
    got = []
    for e in (lay.entities.values() if lay else ()):
        got.append((e.name, float(e.x), float(e.y), int(e.dir or 0), e.attrs.get("ug")))
    tiles = {}
    for g in got:
        for t in _tiles(g):
            tiles[t] = g
    exact_set = set(got)
    res = defaultdict(lambda: defaultdict(int))
    matched = set()
    for wnt in want:
        cat = _cat(wnt[0])
        directional = cat == "carrier"
        hit = wnt in exact_set or (not directional and any(
            g[0] == wnt[0] and g[1] == wnt[1] and g[2] == wnt[2] for g in got))
        if hit:
            res[cat]["exact"] += 1
            matched.add(wnt[:3])
            continue
        on = {tiles.get(t) for t in _tiles(wnt)} - {None}
        if any(_cat(o[0]) == cat for o in on):
            res[cat]["other"] += 1
        else:
            res[cat]["missing"] += 1
    extra = defaultdict(int)
    for g in got:
        if g[:3] not in matched and g not in set(want):
            extra[_cat(g[0])] += 1
    return res, extra


def _cat(name):
    k = CAT.kind(name) if CAT.has_entity(name) else ""
    return "machine" if k in MACHINES else "carrier" if k in CARRIERS else "other"


def _tiles(t):
    name, x, y, d = t[0], t[1], t[2], t[3]
    w, h = CAT.size(name) if CAT.has_entity(name) else (1, 1)
    if d in (4, 12):
        w, h = h, w
    return {(math.floor(x - w / 2 + 0.01) + i, math.floor(y - h / 2 + 0.01) + j)
            for i in range(w) for j in range(h)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("post")
    ap.add_argument("label")
    ap.add_argument("out")
    ap.add_argument("--furnace-recipe", default="iron-plate")
    ap.add_argument("--rungs", default="literal,held,seeded,routed")
    a = ap.parse_args(argv)
    with open(a.post, encoding="utf-8") as fh:
        post = json.load(fh)
    bps = [b for b in blueprints(post) if a.label.lower() in b[0].lower()]
    if not bps:
        print("no blueprint with that label")
        return 2
    label, version, ents = bps[0]
    rows, unknown = normalise(version, ents)
    os.makedirs(a.out, exist_ok=True)
    w = walk.infer(as_dump(rows), CAT)
    size = (max(math.ceil(r["x"] + 1) for r in rows) + 2 * MARGIN,
            max(math.ceil(r["y"] + 1) for r in rows) + 2 * MARGIN)
    report = [f"# {post['title']}: {label} ({len(rows)} entities"
              + (f"; not in the catalog, dropped: {', '.join(unknown)}" if unknown else "") + ")",
              f"walker: {walk.summary(w)[0]}",
              f"nets: " + "; ".join(n.label() + f" {len(n.drivers)}->{len(n.consumers)}"
                                    for n in w.nets.values() if n.drivers or n.consumers)]
    wd = as_dump(rows, MARGIN)
    wm = walk.infer(wd, CAT)
    for rung in a.rungs.split(","):
        gdir = os.path.join(a.out, rung)
        shutil.rmtree(gdir, ignore_errors=True)
        os.makedirs(gdir)
        fk_text, held, seeds, notes = design_rung([dict(r) for r in rows], wm, rung,
                                                  a.furnace_recipe, gdir)
        if rung != "held":
            held = {}
        if rung != "seeded":
            seeds = {}
        code, took, lay, log = build(gdir, fk_text, held, seeds, size)
        res, extra = score(rows, lay)
        line = [f"## {rung}: build exit {code}, {took:.1f} s"]
        for cat in ("machine", "carrier", "other"):
            r = res.get(cat, {})
            tot = sum(r.values())
            if tot:
                line.append(f"  {cat}s {tot}: exact {r.get('exact', 0)}, "
                            f"other {r.get('other', 0)}, missing {r.get('missing', 0)}"
                            f" ({100 * r.get('exact', 0) / tot:.0f}% exact)")
        line.append("  extra: " + (", ".join(f"{k} {v}" for k, v in sorted(extra.items()))
                                   or "none"))
        line += [f"  note: {n}" for n in notes[:12]]
        if len(notes) > 12:
            line.append(f"  ... {len(notes) - 12} more notes")
        for fname in ("route.txt", "report_checks.txt"):
            p = os.path.join(gdir, "out", fname)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    first = [ln.rstrip() for ln in fh if ln.strip()][:4]
                line += [f"  {fname}: {ln[:200]}" for ln in first]
        errs = [ln for ln in log if re.search(r"error|refused|invariant|stop", str(ln), re.I)]
        line += [f"  log: {str(ln)[:200]}" for ln in errs[:5]]
        report += line
        print("\n".join(line), flush=True)
    with open(os.path.join(a.out, "score.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
