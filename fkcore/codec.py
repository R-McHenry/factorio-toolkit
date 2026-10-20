"""fkcore.codec: keyed layout rows <-> a Factorio blueprint string, and .fkp <-> blueprint.

``blueprint`` / ``read_blueprint`` are copied from C:\\fk-lead\\repo\\fk\\trace.py (d6018d3): the same
deterministic serialisation (sorted keys, compact separators, zlib level 9, base64, a leading
"0") and the same parse. Extended for V1:

- ``direction`` is written only when the row has one (a pole or a chest has none), so a row
  without a direction comes back without one;
- an underground's ``ug=in|out`` is the game's ``type: input|output``;
- every other game field of an entity (a requester's ``request_filters``, an inserter's or a
  reactor's ``control_behavior``, ...) rides in its ``config`` attr as canonical JSON (sorted keys,
  compact, ASCII) and is written back verbatim. V1 has no circuit model: only a Literal sets them;
- a circuit wire is the ``wire`` attr of the end whose key sorts first, ``<connector>,<other end's
  local name>,<connector>`` (``;`` between wires), the other end under the same owner (a Literal's
  wires never leave it). Connectors are ``defines.wire_connector_id``: 1 red, 2 green (a
  combinator's input; 3 and 4 its output). The blueprint's ``wires`` carry them with entity
  numbers remapped; a wire whose other end is not among the rows is left out;
- the row's key rides in ``tags.src`` (as before), its net in ``tags.net``, and any attribute the
  game has no field for in ``tags.fkp``;
- the layout's record lines (header, size, inst, cover, plot, claim, mark) ride in the blueprint
  ``description``, so ``.fkp -> blueprint -> .fkp`` is byte-identical;
- copper wires between poles are **derived**, not stored: ``pole_wires`` is a minimum spanning
  tree over the poles within wire reach (at most 5 wires a pole), written as the blueprint's
  ``wires`` (``[[a, 5, b, 5]]``, 5 = ``defines.wire_connector_id.pole_copper``). The first in-game
  test (2026-10-20) showed a blueprint without wires builds every pole unwired: 40 poles, 40
  electric networks. Reading a blueprint drops copper wires again (a power switch's too: V1
  has none), so the round trip holds.

Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import base64
import json
import zlib

from . import fkp as fkpmod

__all__ = ["CodecError", "BLUEPRINT_VERSION", "rows_of", "blueprint", "read_blueprint",
           "parse_blueprint", "fkp_to_blueprint", "blueprint_to_fkp", "pole_wires",
           "circuit_wires", "wire_attrs", "POLE_COPPER"]

#: defines.wire_connector_id.pole_copper (read from the game, 2.0.77)
POLE_COPPER = 5
#: the connectors that carry power, not signals: pole_copper = power_switch_left_copper (5),
#: power_switch_right_copper (6)
COPPER = frozenset({5, 6})
#: copper wires one pole takes
MAX_POLE_WIRES = 5

#: The Factorio blueprint version the harness emits (an opaque 2.0.77 format marker).
BLUEPRINT_VERSION = 562949954076673

_UG = {"in": "input", "out": "output"}
_UG_BACK = {v: k for k, v in _UG.items()}
#: blueprint entity fields the codec writes from the row itself; ``config`` holds every other one
_OWN = ("entity_number", "name", "position", "direction", "tags")


class CodecError(ValueError):
    """A malformed blueprint string."""


def rows_of(lay):
    """The layout's entities as codec rows, in canonical key order."""
    out = []
    for key in sorted(lay.entities, key=fkpmod.natural_key):
        e = lay.entities[key]
        out.append({"src": e.key, "name": e.name, "x": e.x, "y": e.y, "direction": e.dir,
                    "attrs": dict(e.attrs)})
    return out


def _entity_json(row, number):
    entity = {
        "entity_number": number,
        "name": row["name"],
        "position": {"x": float(row["x"]), "y": float(row["y"])},
    }
    if row.get("direction") is not None:
        entity["direction"] = int(row["direction"])
    attrs = dict(row.get("attrs") or {})
    recipe = attrs.pop("recipe", None)
    if recipe:
        entity["recipe"] = recipe
    ug = attrs.pop("ug", None)
    if ug is not None:
        if ug not in _UG:
            raise CodecError(f"{row.get('src')}: ug must be in or out, got {ug!r}")
        entity["type"] = _UG[ug]
    attrs.pop("wire", None)                    # blueprint() writes it into the wires
    config = attrs.pop("config", None)
    if config is not None:
        entity.update(_config(row, config, entity))
    tags = {}
    if row.get("src") is not None:
        tags["src"] = row["src"]
    net = attrs.pop("net", None)
    if net is not None:
        tags["net"] = net
    if attrs:
        tags["fkp"] = attrs
    if tags:
        entity["tags"] = tags
    return entity


def _config(row, text, entity):
    try:
        fields = json.loads(text)
    except ValueError:
        raise CodecError(f"{row.get('src')}: config is not JSON: {text!r}") from None
    if not isinstance(fields, dict):
        raise CodecError(f"{row.get('src')}: config must be a JSON object, got {text!r}")
    clash = sorted(k for k in fields if k in _OWN or k in entity)
    if clash:
        raise CodecError(f"{row.get('src')}: config sets {', '.join(clash)}, which the codec "
                         f"writes from the row")
    return fields


def config_text(fields):
    """Game fields as the canonical ``config`` attr: sorted keys, compact, ASCII JSON."""
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _owner(key):
    return key.rsplit("/", 1)[0] if "/" in key else ""


def parse_wire(text, where="wire"):
    """A ``wire`` attr -> [(connector, the other end's local name, its connector)]."""
    out = []
    for part in text.split(";"):
        bits = part.split(",")
        if len(bits) != 3 or not bits[0].isdigit() or not bits[2].isdigit() or not bits[1]:
            raise CodecError(f"{where}: wire must be <connector>,<local name>,<connector>[;...], "
                             f"got {text!r}")
        out.append((int(bits[0]), bits[1], int(bits[2])))
    return out


def circuit_wires(rows):
    """[(i, ci, j, cj)] row indices: the rows' ``wire`` attrs resolved under each row's owner, the
    lower (index, connector) end first. A wire whose other end is not among the rows is left out.
    Sorted, no duplicates."""
    index = {r["src"]: i for i, r in enumerate(rows) if r.get("src") is not None}
    out = set()
    for i, row in enumerate(rows):
        text = (row.get("attrs") or {}).get("wire")
        if not text or row.get("src") is None:
            continue
        owner = _owner(row["src"])
        for mine, local, theirs in parse_wire(text, row["src"]):
            j = index.get(f"{owner}/{local}" if owner else local)
            if j is not None:
                out.add(min((i, mine, j, theirs), (j, theirs, i, mine)))
    return sorted(out)


def wire_attrs(keys, wires):
    """{row index: ``wire`` attr} for circuit wires [(i, ci, j, cj)] between rows keyed ``keys``.
    Each wire goes on the end whose (key, connector) sorts first and names the other end by its
    local name; a wire with an end that has no key, or with ends under two owners, is left out."""
    links = {}
    for i, ci, j, cj in wires:
        a, b = keys[i], keys[j]
        if a is None or b is None or _owner(a) != _owner(b):
            continue
        if (fkpmod.natural_key(b), cj) < (fkpmod.natural_key(a), ci):
            i, ci, j, cj, b = j, cj, i, ci, a
        links.setdefault(i, set()).add((ci, b.rsplit("/", 1)[-1], cj))
    return {i: ";".join(f"{c},{k},{d}" for c, k, d in
                        sorted(ls, key=lambda w: (w[0], fkpmod.natural_key(w[1]), w[2])))
            for i, ls in links.items()}


def pole_wires(rows, cat):
    """[(i, j)] row indices to wire: a minimum spanning forest over the electric poles, an edge
    only within both poles' wire reach, at most MAX_POLE_WIRES per pole. Deterministic."""
    poles = [i for i, r in enumerate(rows) if cat.has_entity(r["name"])
             and cat.kind(r["name"]) == "electric-pole"]
    edges = []
    for a in range(len(poles)):
        for b in range(a + 1, len(poles)):
            i, j = poles[a], poles[b]
            ri, rj = rows[i], rows[j]
            d2 = (float(ri["x"]) - float(rj["x"])) ** 2 + (float(ri["y"]) - float(rj["y"])) ** 2
            reach = min(cat.pole_reach(ri["name"]), cat.pole_reach(rj["name"]))
            if d2 <= reach * reach + 1e-9:
                edges.append((d2, i, j))
    edges.sort()
    parent = {i: i for i in poles}
    degree = dict.fromkeys(poles, 0)

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    out = []
    for _d2, i, j in edges:
        ri, rj = find(i), find(j)
        if ri == rj or degree[i] >= MAX_POLE_WIRES or degree[j] >= MAX_POLE_WIRES:
            continue
        parent[max(ri, rj)] = min(ri, rj)
        degree[i] += 1
        degree[j] += 1
        out.append((i, j))
    return out


def blueprint(rows, description=None, label=None, wires=None) -> str:
    """Rows -> a blueprint string; ``entity_number`` follows row order. ``wires``: [(i, j)] row
    indices of poles to join by copper wire (see :func:`pole_wires`); the rows' own circuit wires
    (``wire`` attrs, see :func:`circuit_wires`) follow them. Deterministic."""
    rows = list(rows or [])
    entities = [_entity_json(row, i + 1) for i, row in enumerate(rows)]
    bp = {"item": "blueprint", "entities": entities, "version": BLUEPRINT_VERSION}
    out = [[i + 1, POLE_COPPER, j + 1, POLE_COPPER] for i, j in wires or ()]
    out += [[i + 1, ci, j + 1, cj] for i, ci, j, cj in circuit_wires(rows)]
    if out:
        bp["wires"] = out
    if description:
        bp["description"] = description
    if label:
        bp["label"] = label
    text = json.dumps({"blueprint": bp}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "0" + base64.b64encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")


def read_blueprint(s):
    """A blueprint string -> (rows ordered by ``entity_number``, description or None). Circuit
    wires come back as the rows' ``wire`` attrs, which needs the rows' ``tags.src`` keys."""
    rows, description, wires = parse_blueprint(s)
    for i, text in wire_attrs([r["src"] for r in rows], wires).items():
        rows[i]["attrs"]["wire"] = text
    return rows, description


def parse_blueprint(s):
    """A blueprint string -> (rows ordered by ``entity_number``, description or None, circuit
    wires [(i, ci, j, cj)] as row indices, the lower end first). Copper wires are dropped: the
    codec derives them."""
    if not isinstance(s, str) or not s.strip():
        raise CodecError("not a blueprint string")
    text = s.strip()
    if not text[0].isdigit():
        raise CodecError("a blueprint string starts with a version digit")
    body = text[1:]
    try:
        raw = zlib.decompress(base64.b64decode(body + "=" * (-len(body) % 4)))
        document = json.loads(raw.decode("utf-8"))
    except Exception:
        raise CodecError("payload is not base64(zlib(JSON))") from None
    section = document.get("blueprint") if isinstance(document, dict) else None
    if not isinstance(section, dict):
        raise CodecError("payload has no blueprint object")
    entities = section.get("entities") or []
    if not isinstance(entities, list):
        raise CodecError("blueprint entities is not a list")
    ordered = sorted(((i, e) for i, e in enumerate(entities) if isinstance(e, dict)),
                     key=lambda p: (p[1].get("entity_number", p[0]), p[0]))
    rows, number = [], {}
    for k, (_i, entity) in enumerate(ordered):
        if "entity_number" in entity:
            number[entity["entity_number"]] = k
        pos = entity.get("position") or {}
        tags = entity.get("tags") or {}
        extra = {f: v for f, v in entity.items() if f not in _OWN}
        attrs = {}
        if extra.get("recipe"):
            attrs["recipe"] = extra.pop("recipe")
        if "net" in tags:
            attrs["net"] = tags["net"]
        if extra.get("type") in _UG_BACK:
            attrs["ug"] = _UG_BACK[extra.pop("type")]
        if extra:
            attrs["config"] = config_text(extra)
        attrs.update(tags.get("fkp") or {})
        rows.append({"src": tags.get("src"), "name": entity.get("name"),
                     "x": _num(pos.get("x", 0.0)), "y": _num(pos.get("y", 0.0)),
                     "direction": entity.get("direction"), "attrs": attrs})
    wires = set()
    for w in section.get("wires") or []:
        if not (isinstance(w, list) and len(w) == 4 and all(isinstance(v, int) for v in w)):
            continue
        a, ca, b, cb = w
        if ca in COPPER or cb in COPPER or a not in number or b not in number:
            continue
        i, j = number[a], number[b]
        wires.add(min((i, ca, j, cb), (j, cb, i, ca)))
    return rows, section.get("description"), sorted(wires)


def _num(v):
    v = float(v)
    return int(v) if v == int(v) else v


def fkp_to_blueprint(lay, cat=None) -> str:
    """With ``cat``, the poles are wired (derived wires; reading drops them again)."""
    rows = rows_of(lay)
    return blueprint(rows, description="\n".join(fkpmod.record_lines(lay)),
                     label=f"{lay.level} {lay.name}", wires=pole_wires(rows, cat) if cat else None)


def blueprint_to_fkp(s, path="<blueprint>"):
    rows, description = read_blueprint(s)
    if not description:
        raise CodecError("the blueprint carries no .fkp records in its description")
    lay = fkpmod.loads(description, path)
    for row in rows:
        if row["src"] is None:
            raise CodecError(f"{row['name']} at {row['x']},{row['y']} has no tags.src key")
        lay.add(fkpmod.Entity(row["src"], row["name"], row["x"], row["y"], row["direction"],
                              row["attrs"]))
    return lay
