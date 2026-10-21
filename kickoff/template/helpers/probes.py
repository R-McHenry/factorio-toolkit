"""The seed features: reads the first players wrote again and again (2026-10-19..21)."""
from __future__ import annotations

from . import feature, game


@feature
def grids():
    """The electric networks by pole count, and every roboport without power."""
    return game.lua("grids")


@feature
def machines(*status):
    """Each machine with its recipe and status; only the given statuses (e.g. no_power)."""
    return game.lua("machines", ONLY=",".join(status))


@feature
def stock(*items):
    """How many of each item the robot network holds."""
    return game.lua("stock", ITEMS=",".join(items or ("iron-plate", "copper-plate")))


@feature
def labs():
    """What the labs wait for, pack by pack."""
    return game.lua("labs")
