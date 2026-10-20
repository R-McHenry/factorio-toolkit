"""fkcore.templates: the built-in templates, as the machines they contribute to the netlist.

A template is a pure function ``(params, catalog) -> [MSpec]``: the machines one instance adds,
with the endpoints the rate model and the checks need. Geometry (the Fragment of CORE-V1.md §5:
carriers, roles, attach points) is added per template in ``fkcore.fragments``; the machine locals
here (``m0``, ``m1``...) are the keys the fragment uses for the same machines.

Endpoints come from the recipe (ingredients in, products out), plus the fuel of a burner machine,
the resource of a drill and every science pack for a lab. Pure, stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import FUEL_USE_W, FUEL_VALUE_J, MINING_TIME

__all__ = ["MSpec", "TemplateError", "TEMPLATES", "COMMON_PARAMS", "machines", "science_packs"]

INF = float("inf")

#: Parameters every instance may carry; the elaborator reads them, the templates ignore them.
COMMON_PARAMS = ("duty", "inserter")


class TemplateError(ValueError):
    """Malformed template parameters: no machines can be produced (an invariant, not a check)."""


@dataclass
class MSpec:
    local: str                     # key below the instance: m0, m1, c0
    prototype: str
    recipe: str | None
    needs: dict                    # item -> items/s at full speed (ingredients and fuel)
    makes: dict                    # item -> items/s at full speed (INF for an unbounded source)
    takes: frozenset | None        # items it accepts as a consumer; None = anything (a chest)
    sink: bool = False             # takes whatever reaches it beyond its needs (chest, lab)
    drain: float | None = None     # a sink's cap in items/s (None = unlimited)
    source: bool = False           # an unbounded source (a requester chest with no rate)
    extra: dict = field(default_factory=dict)


def science_packs(cat):
    return frozenset(r["name"] for r in cat.recipes() if r["name"].endswith("-science-pack"))


# -- helpers --------------------------------------------------------------------------------------
def _int(params, key, default=None):
    v = params.get(key, default)
    if v is None:
        raise TemplateError(f"needs {key}=")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if not isinstance(v, int) or v < 1:
        raise TemplateError(f"{key} must be a positive whole number, got {v!r}")
    return v


def _word(params, key, default=None):
    v = params.get(key, default)
    if v is None:
        raise TemplateError(f"needs {key}=")
    if not isinstance(v, str):
        raise TemplateError(f"{key} must be one name, got {v!r}")
    return v


def _rate(params, key, default=None):
    v = params.get(key, default)
    if v is None:
        return None
    if not isinstance(v, (int, float)) or v < 0:
        raise TemplateError(f"{key} must be a rate (e.g. 0.5/s), got {v!r}")
    return float(v)


def _only(params, allowed):
    extra = sorted(set(params) - set(allowed) - set(COMMON_PARAMS))
    if extra:
        raise TemplateError("unknown parameter%s %s (allowed: %s)" % (
            "s" if len(extra) > 1 else "", ", ".join(extra), ", ".join(allowed) or "none"))


def _crafter(cat, local, machine, recipe, fuel=None):
    if not cat.has_recipe(recipe):
        raise TemplateError(f"unknown recipe {recipe}")
    if not cat.has_entity(machine):
        raise TemplateError(f"unknown machine {machine}")
    speed = cat.entity(machine).get("crafting_speed")
    if speed is None:
        raise TemplateError(f"{machine} does not craft")
    needs, makes = cat.recipe_rates(recipe, speed)
    if fuel is not None:
        needs[fuel] = needs.get(fuel, 0.0) + _fuel_rate(machine, fuel)
    return MSpec(local, machine, recipe, needs, makes, frozenset(needs))


def _fuel_rate(machine, fuel):
    if machine not in FUEL_USE_W:
        raise TemplateError(f"{machine} burns no fuel")
    if fuel not in FUEL_VALUE_J:
        raise TemplateError(f"{fuel} is not a fuel")
    return FUEL_USE_W[machine] / FUEL_VALUE_J[fuel]


# -- templates ------------------------------------------------------------------------------------
def asm_row(params, cat):
    """``AsmRow<n, recipe, machine=assembling-machine-1>``: n assemblers on one recipe."""
    _only(params, ("n", "recipe", "machine"))
    n = _int(params, "n")
    recipe = _word(params, "recipe")
    machine = _word(params, "machine", "assembling-machine-1")
    return [_crafter(cat, f"m{k}", machine, recipe) for k in range(n)]


def assembler(params, cat):
    """``Assembler<recipe, machine=assembling-machine-1>``: one machine."""
    _only(params, ("recipe", "machine"))
    return [_crafter(cat, "m0", _word(params, "machine", "assembling-machine-1"),
                     _word(params, "recipe"))]


def _smelt_recipe(params, cat):
    if "recipe" in params:
        return _word(params, "recipe")
    ore = _word(params, "ore")
    try:
        return cat.smelting_recipe(ore)
    except KeyError:
        raise TemplateError(f"no smelting recipe takes {ore}") from None


def smelter_row(params, cat):
    """``SmelterRow<n, recipe | ore, fuel=coal, machine=stone-furnace>``: n furnaces, ore + fuel in."""
    _only(params, ("n", "recipe", "ore", "fuel", "machine"))
    n = _int(params, "n")
    recipe = _smelt_recipe(params, cat)
    machine = _word(params, "machine", "stone-furnace")
    fuel = _word(params, "fuel", "coal") if machine in FUEL_USE_W else None
    return [_crafter(cat, f"m{k}", machine, recipe, fuel) for k in range(n)]


def furnace(params, cat):
    """``Furnace<recipe | ore, fuel=coal, machine=stone-furnace>``: one furnace."""
    _only(params, ("recipe", "ore", "fuel", "machine"))
    machine = _word(params, "machine", "stone-furnace")
    fuel = _word(params, "fuel", "coal") if machine in FUEL_USE_W else None
    return [_crafter(cat, "m0", machine, _smelt_recipe(params, cat), fuel)]


def miner_row(params, cat):
    """``MinerRow<n, resource, drill=electric-mining-drill, fuel=coal>``: n drills on a patch."""
    _only(params, ("n", "resource", "drill", "fuel"))
    n = _int(params, "n")
    resource = _word(params, "resource")
    drill = _word(params, "drill", "electric-mining-drill")
    if resource not in MINING_TIME:
        raise TemplateError(f"unknown resource {resource}")
    speed = cat.entity(drill).get("mining_speed")
    if speed is None:
        raise TemplateError(f"{drill} does not mine")
    out = []
    for k in range(n):
        needs = {}
        if drill in FUEL_USE_W:
            fuel = _word(params, "fuel", "coal")
            needs[fuel] = _fuel_rate(drill, fuel)
        out.append(MSpec(f"m{k}", drill, None, needs, {resource: speed / MINING_TIME[resource]},
                         frozenset(needs), extra={"resource": resource}))
    return out


def pumpjack(params, cat):
    """``Pumpjack<n=1, rate=30/s>``: crude oil at the well's rate (a property of the well)."""
    _only(params, ("n", "rate"))
    n = _int(params, "n", 1)
    rate = _rate(params, "rate", 30.0)
    return [MSpec(f"m{k}", "pumpjack", None, {}, {"crude-oil": rate}, frozenset(),
                  extra={"resource": "crude-oil"}) for k in range(n)]


def offshore_pump(params, cat):
    """``OffshorePump<rate=1200/s>``: water."""
    _only(params, ("rate",))
    return [MSpec("m0", "offshore-pump", None, {}, {"water": _rate(params, "rate", 1200.0)},
                  frozenset())]


def refinery(params, cat):
    """``Refinery<recipe=basic-oil-processing>``."""
    _only(params, ("recipe",))
    return [_crafter(cat, "m0", "oil-refinery", _word(params, "recipe", "basic-oil-processing"))]


def chem_plant(params, cat):
    """``ChemPlant<recipe, n=1>``."""
    _only(params, ("recipe", "n"))
    recipe = _word(params, "recipe")
    return [_crafter(cat, f"m{k}", "chemical-plant", recipe) for k in range(_int(params, "n", 1))]


def lab_row(params, cat):
    """``LabRow<n>``: n labs; each takes every science pack that reaches it (a sink)."""
    _only(params, ("n",))
    packs = science_packs(cat)
    return [MSpec(f"m{k}", "lab", None, {}, {}, packs, sink=True)
            for k in range(_int(params, "n"))]


_CHEST = {"provider": "passive-provider-chest", "storage": "storage-chest",
          "requester": "requester-chest", "buffer": "buffer-chest"}


def chest(params, cat):
    """``Chest<provider | storage | requester | buffer, item=, rate=, chest=>``: a boundary.

    provider / storage (the default is provider): the end of a net into the logistic network, a
    sink for whatever reaches it, up to ``rate``. requester: the logistic network feeding a net with
    ``item``, at ``rate`` or unbounded (an UNBOUNDED check line).
    """
    roles = [r for r in _CHEST if params.get(r) is True]
    if len(roles) > 1:
        raise TemplateError("one role only: " + ", ".join(roles))
    role = roles[0] if roles else "provider"
    _only(params, tuple(_CHEST) + ("item", "rate", "chest"))
    proto = _word(params, "chest", _CHEST[role])
    rate = _rate(params, "rate")
    if role == "requester":
        item = _word(params, "item")
        return [MSpec("c0", proto, None, {}, {item: INF if rate is None else rate}, frozenset(),
                      source=rate is None, extra={"role": role})]
    takes = None if "item" not in params else frozenset([_word(params, "item")])
    return [MSpec("c0", proto, None, {}, {}, takes, sink=True, drain=rate, extra={"role": role})]


def turret_row(params, cat):
    """``TurretRow<n, ammo=firearm-magazine>``: n gun turrets taking ammo (a sink)."""
    _only(params, ("n", "ammo"))
    ammo = _word(params, "ammo", "firearm-magazine")
    return [MSpec(f"m{k}", "gun-turret", None, {}, {}, frozenset([ammo]), sink=True)
            for k in range(_int(params, "n"))]


TEMPLATES = {
    "AsmRow": asm_row,
    "Assembler": assembler,
    "SmelterRow": smelter_row,
    "Furnace": furnace,
    "MinerRow": miner_row,
    "Pumpjack": pumpjack,
    "OffshorePump": offshore_pump,
    "Refinery": refinery,
    "ChemPlant": chem_plant,
    "LabRow": lab_row,
    "Chest": chest,
    "TurretRow": turret_row,
}


def machines(kind, params, cat):
    """The machines an instance of ``kind`` contributes (raises TemplateError)."""
    try:
        fn = TEMPLATES[kind]
    except KeyError:
        raise TemplateError(f"unknown template {kind}") from None
    return fn(params, cat)
