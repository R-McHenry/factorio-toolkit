"""Turn the game's dump (tools/dump_catalog.lua) into a pack's catalog for the toolkit.

usage: python tools/dump_catalog.py PACK CATALOG_JSON FLUIDBOXES_JSON
  PACK              the pack's name: the files go to fkcore/data/packs/PACK/ (FK_PACK=PACK picks it)
  *_JSON            script-output/fk-catalog.json and fk-fluidboxes.json from the game

Run the Lua first as /sc in the pack's game (any RCON client; it builds each placeable entity once
on a scratch surface and deletes the surface). This side fixes what Lua's JSON writer can't say and
keeps the hand-measured fixture's conventions:
- an empty Lua table is written as {}: the list fields become [] again;
- a pipe-to-ground's underground reach is the measured one, one less than the prototype's
  (2.0.77: the prototype says 11, a pair spans at most 10 tiles end to end).
"""
import json
import os
import sys

LISTS = {"connectors", "placed_by", "crafting_categories", "resource_categories", "ingredients",
         "products", "boxes", "connections", "notes", "mods", "fuel_categories", "categories"}


def lists(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in LISTS and v == {}:
                node[k] = []
            else:
                lists(v)
    elif isinstance(node, list):
        for v in node:
            lists(v)
    return node


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    pack, cat_path, fb_path = argv[1:]
    cat = lists(json.load(open(cat_path, encoding="utf-8")))
    fb = lists(json.load(open(fb_path, encoding="utf-8")))
    for row in cat["entities"]:
        if row["type"] == "pipe-to-ground" and row.get("max_distance"):
            row["max_distance"] -= 1
    for row in fb["entities"].values():
        if row["type"] != "pipe-to-ground":
            continue
        for box in row["boxes"]:
            for c in box["connections"]:
                if c["type"] == "underground" and c.get("max_distance"):
                    c["max_distance"] -= 1
    fb["notes"] = ["at: the connection's point inside the entity (relative to its centre) for the "
                   "entity facing N, E, S, W; dir: the side it faces for an entity facing north",
                   "pipe-to-ground: max_distance is the prototype's less one (the measured pair "
                   "span, as in the vanilla fixture)",
                   "no recipes measured: catalog.py's recipe rule gives each recipe's live boxes"]
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "fkcore", "data", "packs", pack)
    os.makedirs(out, exist_ok=True)
    for name, data in (("catalog.json", cat), ("fluidboxes.json", fb)):
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
            fh.write("\n")
    print(f"{out}: {len(cat['entities'])} entities, {len(cat['recipes'])} recipes, "
          f"{len(fb['entities'])} with fluid boxes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
