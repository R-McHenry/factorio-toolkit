# Toolkit 2.1.1: facts into data

PLAN-2.1, phase 1 ("Game facts into data"). The game's facts move out of Python into two files
read from the game, and the catalog gets every placeable entity, so `Entity`, `Decider`,
`Arithmetic` and `PowerSwitch` have their data before they come. Nothing a design uses changes.

## Read from the game

`tools/read_facts.py` starts a laptop server of its own (`LaptopServer("facts")`: its own ports
and write-data, never the live game), Factorio 2.0.77 with base and Space Age. Each game call is
one short RCON command that writes its answer to script-output; nothing is registered. The whole
read takes about 5 s. Entities are created on a surface of the reader's own (`fk-facts`) to ask
for their wire connectors, and one constant combinator, wired to a pole, is given every signal.

It writes `fkcore/data/facts.json`:
- 145 placeable entities: energy source, W at full work, drain, burner fuel categories, mining
  speed and radius, crafting speed and categories, module slots and allowed effects, steam and
  heat values;
- 12 resources (mining time, category, results), 20 fuels (value, category), 12 modules (category,
  tier, effects), 33 fluids (heat capacity, temperatures) and 659 recipes (allowed effects: which
  take productivity);
- steam per second (boiler 60, heat exchanger 103.09, steam engine 30, turbine 60) and heat W
  (reactor 40 MW, heating tower 40 MW, exchanger 10 MW), worked out from the above;
- the circuit wire: the usual reach (9) and the six wire connector ids;
- every signal that can go on a wire, by type: 340 items, 33 fluids, 147 virtual signals, 659
  recipes, 1016 entities, 6 qualities, 8 space locations and 15 asteroid chunks. The combinator
  takes 2232 and puts 2224 on its wire: 8 virtual signals never transmit (`signal-everything`,
  `-anything`, `-each`, `-unknown` and the four parameter signals).

`fkcore.facts` reads the file (once) and answers questions about it.

## The catalog

`catalog.json` goes from 80 entities to 145: combinators, power switch, programmable speaker,
display panel, train stop, rail signals, rails, loaders, valves, rocket silo, Space Age's
buildings, vehicles and robots. Every row gets `placed_by` (the items that place it), `energy`
(source, W, drain, priority) and `circuit` (its wire connector ids and reach). The 80 measured
rows keep every value they had.

`catalog.py`'s own fallback rows go: the five combinator and infinity-chest rows (2.0, 2.0.71)
and the `infinity-pipe` row taken from `fluidboxes.json`. They now come from the game. Their
collision boxes are the game's (-0.34765625, not -0.35); nothing reads a collision box.

`Catalog.is_item` now takes an entity's items from `placed_by`, so a rail is the item `rail`, not
`straight-rail`. For every entity the catalog had, the answer is the same.

## The dicts are reads of the file

- `catalog.py`: `FUEL_USE_W`, `FUEL_VALUE_J`, `MINING_TIME`, `STEAM_PER_S`, `HEAT_W`,
  `REACTOR_FUEL_S`, `MINING_RADIUS`, `CIRCUIT_WIRE_REACH`, and `is_electric` (it went by entity
  type, with the burners named; it now asks whether the entity's energy source is electric and
  takes input).
- `templates.py`: `MODULE_SLOTS`, `MODULE_EFFECTS`.
- `elaborate.py`: `PRODUCTIVE`.

`TIERS`, the default furnace and the default inserter are choices, not facts. They stay in Python
until the prelude takes them.

## Where the game disagrees

The first commit keeps the old answer in each case, so every design comes out as it did:

- `FUEL_USE_W`: the game also has a chemical burner in the burner inserter (144 kW), burner
  generator (1 MW), heating tower (40 MW), car (150 kW), tank and locomotive (600 kW).
- `FUEL_VALUE_J`: the game has 12 more chemical fuels: biter egg, carbon, jelly, jellynut and its
  seed, nuclear fuel, pentapod egg, spoilage, tree seed, yumako, yumako mash and its seed.
- `MINING_TIME`: the game also has calcite (1 s), scrap (0.5 s) and tungsten ore (5 s).
- `HEAT_W`: the game also has the heating tower (40 MW).
- `MODULE_SLOTS`: the game also gives slots to the beacon (2), lab (2), biolab (4), big mining
  drill (4), biochamber (4), crusher (2), cryogenic plant (8), electromagnetic plant (5), foundry
  (4), recycler (4) and rocket silo (4).
- `MODULE_EFFECTS`: the game also has the three quality modules (speed -0.05).
- `PRODUCTIVE`: the game allows productivity in 85 more recipes: Space Age's (casting, asteroid
  crushing, the new science packs, ...), the ten parameter recipes, and the base game's
  uranium-fuel-cell, nuclear-fuel, kovarex and nuclear-fuel-reprocessing.
- `is_electric`: a biochamber and a captive biter spawner burn nutrients (the old rule said
  electric); a railgun turret takes power (the old rule said not).
- The circuit reach of a big electric pole is 32 in the game; the toolkit uses its copper reach,
  30.
- The hand-added `electric-energy-interface` row has a collision box of 0.9; the game's is
  0.8984375.

Every other value matches: burner W, fuel values, mining times and radii, steam, heat, reactor
fuel time, module slots and effects, wire reach, and all 80 measured catalog rows.

## The game's values, adopted

A second commit takes the game's answer in every case above: the dicts are the file's, whole
(`FUEL_USE_W`, `FUEL_VALUE_J`, `MINING_TIME`, `HEAT_W`, `MODULE_SLOTS`, `MODULE_EFFECTS`,
`PRODUCTIVE`), `is_electric` is the game's for every entity, `circuit_reach` is each row's own
(a big pole 32, a power switch 10, else 9), and the energy interface has the game's box.

Two guards come with it, so a wider `MINING_TIME` doesn't plan what can't be mined:
- `MinerRow` refuses a drill that doesn't mine its resource (`electric-mining-drill does not mine
  tungsten-ore`); before, tungsten ore was an unknown resource.
- `fk plan` counts a resource as mined only if its electric drill mines it (calcite and scrap
  yes, tungsten ore no), and lists the raw rows iron, copper, coal, stone, uranium first, as
  before.

What changes for a player: `fuel=` takes the 12 new chemical fuels, `modules=` goes into a lab,
foundry or any other machine with slots, the quality modules are known, productivity modules go
into Space Age's recipes and uranium fuel cells, the power cover leaves biochambers out and
powers railgun turrets, and `MinerRow` mines calcite, scrap and (with a big drill) tungsten.

## Checked

- Golden check (`tools/golden.py`, 54 files): 54 of 54 identical to 2.0.78, for the first commit
  and for the second. No design in the corpus uses what the game's values change.
- `fk plan` for ten items (electronic circuits to metallurgic science): identical text before and
  after the second commit.
- `tests/test_facts.py`: the file loads, the game's facts, the wide catalog, the dicts and the
  drill guard.
- `fkcore/__init__.py` says 2.1.1 (it said 2.0.43).
- `tools/read_facts.py` run twice writes the same two files, byte for byte.
- Full suite: 1164 tests OK after the first commit, 1166 after the second.
