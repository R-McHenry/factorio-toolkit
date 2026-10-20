"""fkcore.codec: keyed layout rows <-> a Factorio blueprint string, and .fkp <-> blueprint.

``blueprint`` / ``read_blueprint`` are copied from C:\\fk-lead\\repo\\fk\\trace.py (d6018d3): the same
deterministic serialisation (sorted keys, compact separators, zlib level 9, base64, a leading
"0") and the same parse. Extended for V1:

- ``direction`` is written only when the row has one (a pole or a chest has none), so a row
  without a direction comes back without one;
- an underground's ``ug=in|out`` is the game's ``type: input|output``;
- the row's key rides in ``tags.src`` (as before), its net in ``tags.net``, and any attribute the
  game has no field for in ``tags.fkp``;
- the layout's record lines (header, size, inst, cover, plot, claim, mark) ride in the blueprint
  ``description``, so ``.fkp -> blueprint -> .fkp`` is byte-identical.

Pure, stdlib only, deterministic.
"""
from __future__ import annotations

import base64
import json
import zlib

from . import fkp as fkpmod

__all__ = ["CodecError", "BLUEPRINT_VERSION", "rows_of", "blueprint", "read_blueprint",
           "fkp_to_blueprint", "blueprint_to_fkp"]

#: The Factorio blueprint version the harness emits (an opaque 2.0.77 format marker).
BLUEPRINT_VERSION = 562949954076673

_UG = {"in": "input", "out": "output"}
_UG_BACK = {v: k for k, v in _UG.items()}


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


def blueprint(rows, description=None, label=None) -> str:
    """Rows -> a blueprint string; ``entity_number`` follows row order. Deterministic."""
    entities = [_entity_json(row, i + 1) for i, row in enumerate(rows or [])]
    bp = {"item": "blueprint", "entities": entities, "version": BLUEPRINT_VERSION}
    if description:
        bp["description"] = description
    if label:
        bp["label"] = label
    text = json.dumps({"blueprint": bp}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "0" + base64.b64encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")


def read_blueprint(s):
    """A blueprint string -> (rows ordered by ``entity_number``, description or None)."""
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
    rows = []
    for _i, entity in ordered:
        pos = entity.get("position") or {}
        tags = entity.get("tags") or {}
        attrs = {}
        if entity.get("recipe"):
            attrs["recipe"] = entity["recipe"]
        if "net" in tags:
            attrs["net"] = tags["net"]
        if entity.get("type") in _UG_BACK:
            attrs["ug"] = _UG_BACK[entity["type"]]
        attrs.update(tags.get("fkp") or {})
        rows.append({"src": tags.get("src"), "name": entity.get("name"),
                     "x": _num(pos.get("x", 0.0)), "y": _num(pos.get("y", 0.0)),
                     "direction": entity.get("direction"), "attrs": attrs})
    return rows, section.get("description")


def _num(v):
    v = float(v)
    return int(v) if v == int(v) else v


def fkp_to_blueprint(lay) -> str:
    return blueprint(rows_of(lay), description="\n".join(fkpmod.record_lines(lay)),
                     label=f"{lay.level} {lay.name}")


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
