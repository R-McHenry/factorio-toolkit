"""fkcore.pack: the run's mod pack (env ``FK_PACK``) and the facts about it that are not prototypes.

A pack lives in ``fkcore/data/packs/<pack>/``: ``catalog.json`` and ``fluidboxes.json`` (dumped
from its game, ``tools/dump_catalog.lua``) and ``pack.json``, written by hand:

    {"landfill": "landfill"}     the tile (and the item that lays it) that makes water ground

Sea Block's world is water: with ``landfill`` set, water is ground that costs landfill (the
terrain stops blocking it, SHORT counts it, and a single ghost on water gets landfill under it,
as a paste does by itself once the landfill recipe is unlocked). Unset pack: the base game.
Read at call time, so a test can set the variable. Pure, stdlib only.
"""
import json
import os

__all__ = ["name", "path", "facts", "landfill"]

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def name():
    """The pack's name, or None for the base game."""
    return os.environ.get("FK_PACK") or None


def path(*parts):
    """A file of the pack (or of the base game's ``data`` when there is no pack)."""
    n = name()
    return os.path.join(DATA, "packs", n, *parts) if n else os.path.join(DATA, *parts)


def facts():
    """The pack's ``pack.json``, {} for the base game or a pack without one."""
    p = path("pack.json") if name() else None
    if not p or not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def landfill():
    """The landfill tile that turns water into ground in this pack, or None (water blocks)."""
    return facts().get("landfill") or None
