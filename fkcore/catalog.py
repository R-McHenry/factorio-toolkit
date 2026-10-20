"""Prototype facts, read from fkcore/data/catalog.json.

Copied from C:\\fk-lead\\repo\\fk\\catalog.py (d6018d3) with its measured fixture fk/catalog-v5.json
(Factorio 2.0 + Space Age prototypes). Added for V1: a default path, ``load()`` with no argument,
``kind`` (the entity type), ``recipe_rates`` (per-second ingredients and products, fluids included)
and the few base-game facts the fixture does not carry (``FUEL_USE_W``, ``FUEL_VALUE_J``,
``MINING_TIME``). Every other module takes a Catalog instance instead of opening the fixture itself.
Pure, stdlib only.
"""
from __future__ import annotations

import json
import math
import os

__all__ = ["Catalog", "DEFAULT_PATH", "FUEL_USE_W", "FUEL_VALUE_J", "MINING_TIME"]

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "catalog.json")

# Base-game facts the measured fixture does not record (Factorio 2.0 prototype values).
#: Burner energy use in watts, for machines whose endpoints include a fuel input.
FUEL_USE_W = {"stone-furnace": 90e3, "steel-furnace": 90e3, "burner-mining-drill": 150e3,
              "boiler": 1.8e6}
#: Fuel value in joules.
FUEL_VALUE_J = {"coal": 4e6, "wood": 2e6, "solid-fuel": 12e6, "rocket-fuel": 100e6}
#: Mining time per resource (an electric drill at mining speed 0.5 makes 0.5/s of a time-1 ore).
MINING_TIME = {"iron-ore": 1.0, "copper-ore": 1.0, "coal": 1.0, "stone": 1.0, "uranium-ore": 2.0}

# Entity types that are powered by electricity. Inserters, mining drills and furnaces hold burner
# and electric prototypes alike, so there the burners are named: every other inserter, drill
# (pumpjack, big drill) and furnace (electric furnace, recycler) runs on the grid.
_ELECTRIC_TYPES = frozenset({"assembling-machine", "lab", "roboport", "beacon", "radar", "lamp",
                             "electric-turret", "pump"})
_MIXED_TYPES = frozenset({"inserter", "mining-drill", "furnace"})
_BURNERS = frozenset({"burner-inserter", "burner-mining-drill", "stone-furnace", "steel-furnace"})


class Catalog:
    """Immutable view over the measured prototype catalog."""

    def __init__(self, version, entities, recipes):
        self.version = version
        self._entities = entities
        self._recipes = recipes
        self._fluids = None

    # -- construction ---------------------------------------------------------------------
    @classmethod
    def load(cls, path=DEFAULT_PATH) -> "Catalog":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Catalog":
        entities = {}
        for row in data.get("entities", []):
            entities[row["name"]] = row
        recipes = {}
        for row in data.get("recipes", []):
            recipes[row["name"]] = row
        return cls(data.get("version"), entities, recipes)

    # -- prototypes -----------------------------------------------------------------------
    def entity(self, name) -> dict:
        try:
            return self._entities[name]
        except KeyError:
            raise KeyError(name) from None

    def recipe(self, name) -> dict:
        try:
            return self._recipes[name]
        except KeyError:
            raise KeyError(name) from None

    def recipes(self) -> list[dict]:
        """Every recipe row the fixture holds, in fixture order (a read-only copy)."""
        return list(self._recipes.values())

    def electric_poles(self) -> list[dict]:
        """Every electric-pole prototype, strongest first (supply area, then wire reach)."""
        rows = [row for row in self._entities.values()
                if row.get("type") == "electric-pole"]
        rows.sort(key=lambda row: (-float(row.get("supply_area_distance") or 0.0),
                                   -float(row.get("max_wire_distance") or 0.0),
                                   str(row.get("name"))))
        return rows

    def has_entity(self, name) -> bool:
        return name in self._entities

    def has_recipe(self, name) -> bool:
        return name in self._recipes

    def kind(self, name) -> str:
        """The prototype's entity type (``transport-belt``, ``inserter``, ``assembling-machine``...)."""
        return self.entity(name).get("type", "")

    def is_fluid(self, name) -> bool:
        """A fluid: a recipe names it with ``type: fluid``; water, steam and crude oil also come
        from machines without a recipe (offshore pump, boiler, pumpjack)."""
        if self._fluids is None:
            names = {"water", "steam", "crude-oil"}
            for rec in self._recipes.values():
                for row in list(rec.get("ingredients") or ()) + list(rec.get("products") or ()):
                    if row.get("type") == "fluid":
                        names.add(row["name"])
            self._fluids = frozenset(names)
        return name in self._fluids

    def recipe_rates(self, recipe, speed) -> tuple[dict, dict]:
        """``(needs, makes)`` per second for one machine crafting ``recipe`` at ``speed``.

        Items and fluids alike; a product with a probability or an amount range counts its mean.
        """
        rec = self.recipe(recipe)
        crafts = float(speed) / float(rec["energy"])
        needs, makes = {}, {}
        for ing in rec.get("ingredients", ()):
            needs[ing["name"]] = needs.get(ing["name"], 0.0) + ing["amount"] * crafts
        for prod in rec.get("products", ()):
            if "amount" in prod:
                amount = float(prod["amount"])
            else:
                amount = (float(prod.get("amount_min", 0)) + float(prod.get("amount_max", 0))) / 2
            amount *= float(prod.get("probability", 1.0))
            makes[prod["name"]] = makes.get(prod["name"], 0.0) + amount * crafts
        return needs, makes

    def smelting_recipe(self, ingredient) -> str:
        """The smelting recipe whose only ingredient is ``ingredient`` (iron-ore -> iron-plate)."""
        for rec in self._recipes.values():
            ings = rec.get("ingredients") or ()
            if rec.get("category") == "smelting" and len(ings) == 1 and ings[0]["name"] == ingredient:
                return rec["name"]
        raise KeyError(ingredient)

    def size(self, name) -> tuple[int, int]:
        row = self.entity(name)
        return (row["tile_width"], row["tile_height"])

    def tiles(self, name, x, y, direction=None) -> set[tuple[int, int]]:
        """Tiles occupied by an entity of `name` centred at (x, y).

        The footprint runs from floor(c - size/2) to floor(c + size/2) - 1 inclusive, so the centre
        must line up with the size: odd sizes sit on half-tile centres, even sizes on integers.
        East/west (direction 4/12) swap width and height. Without a direction, a centre that only
        lines up with the swapped size is taken as rotated (a 2x1 splitter facing east sits on
        (x.5, y), facing north on (x, y.5)): most callers do not pass the direction.
        """
        w, h = self.size(name)
        if direction is not None and int(direction) % 8 == 4:
            w, h = h, w
        elif direction is None and w != h:
            fits = _is_integer(x - w / 2) and _is_integer(y - h / 2)
            if not fits and _is_integer(x - h / 2) and _is_integer(y - w / 2):
                w, h = h, w
        lo_x = x - w / 2
        lo_y = y - h / 2
        if not _is_integer(lo_x) or not _is_integer(lo_y):
            raise ValueError(
                "centre (%r, %r) is inconsistent with size (%d, %d) of %s" % (x, y, w, h, name)
            )
        x0 = int(math.floor(lo_x))
        y0 = int(math.floor(lo_y))
        return {(x0 + dx, y0 + dy) for dx in range(w) for dy in range(h)}

    # -- gameplay facts -------------------------------------------------------------------
    def is_electric(self, name) -> bool:
        row = self.entity(name)
        etype = row.get("type")
        if etype in _ELECTRIC_TYPES:
            return True
        if etype in _MIXED_TYPES:
            return name not in _BURNERS
        return False

    def craft_rate(self, recipe, machine) -> dict[str, float]:
        """Products per second for one machine: amount * crafting_speed / energy."""
        rec = self.recipe(recipe)
        row = self.entity(machine)
        speed = row.get("crafting_speed")
        if speed is None:
            speed = row.get("mining_speed")
        if speed is None:
            raise KeyError(machine)
        energy = rec["energy"]
        rates = {}
        for product in rec.get("products", []):
            rates[product["name"]] = product["amount"] * speed / energy
        return rates

    def belt_throughput(self, name="transport-belt") -> float:
        """Items/s on a fully compressed belt, both lanes."""
        return self.entity(name)["belt_speed"] * 60 * 8

    def inserter_throughput(self, name="inserter"):
        """Items/s one inserter moves with hand size 1: ``60 * rotation_speed``.

        The rule ``fk.netlist`` already uses for an inserter link (contracts/netlist.md); ``None``
        when the prototype carries no rotation speed (a modded or unmeasured entity).  A basic
        inserter is 0.84/s and a fast inserter 2.40/s in the measured catalog.
        """
        row = self.entity(name)
        speed = row.get("rotation_speed")
        return None if speed is None else 60.0 * float(speed)

    def pole_supply(self, name) -> float:
        return self.entity(name)["supply_area_distance"]

    def pole_reach(self, name) -> float:
        return self.entity(name)["max_wire_distance"]


def _is_integer(value) -> bool:
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value) and value.is_integer()
    return float(value).is_integer()
