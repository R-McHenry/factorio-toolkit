# 43-mines: patches from the design, the drill filter, the smelting example (PLAN-ORGANIC M3, M4)

Branch `claude/43-mines`, cut from main 90e20a0 (3.1.4 + wave 1). Wave 2 of part M: M3 (patches
from the design), M4 (the smelting chapter's mixed patch), and wave 1's leftover (the drill filter
confirmed on a laptop server). Written 2026-11-09.

## For the territory agent: the patch reader (M3)

One plain function in `fkcore/placer.py`, pure, stdlib, nothing read from the world:

```python
from fkcore import placer

placer.patches(terrain, resource=None)   # -> [OrePatch], largest first per resource, n from 1
placer.patch(terrain, "iron-ore#2")      # -> OrePatch or None ("iron-ore" is #1)
placer.nearest_patch(terrain, "iron-ore", (x, y), need=0)   # nearest centroid with >= need tiles
```

`terrain` is any of: a `terrain.Terrain` (what `terrain.load(path)` gives), the path of the
`.terrain.json` the design names (`read-terrain`, `<name>.terrain.json`), that file's dict, a
`terrain.FrameGround` (then the tiles are in that plot's frame) or a `{resource: {tile: amount}}`
mapping. `OrePatch` is frozen: `resource`, `n` (the `#k`, 1 the largest: the same numbering
`terrain.patches` and the surface file's `place ... patch iron-ore#2` use), `tiles` (frozenset of
(x, y)), `amount`, `box` (x0, y0, x1, y1, half-open), `centroid` (the mean of the tile centres,
floats), `name` (`iron-ore#2`), `size`, `len()`.

## The drill filter (M1 leftover): confirmed, there is none

Measured 2026-11-09 05:55 on a laptop server (`tools/laptop_server.py`, scenario fk-play; the
laptop's Factorio is **2.1.24** now, base + space-age + quality + elevated-rails + recycler; the
live game was not touched):

| what | answer |
|---|---|
| `prototypes.entity[d].filter_count` for the four drills | `0` (a number, not nil) for electric-mining-drill, burner-mining-drill, big-mining-drill, pumpjack |
| `LuaEntity.filter_slot_count` on a placed electric drill | 0 |
| `set_filter(1, 'iron-ore')`, `set_filter(1, prototypes.entity['iron-ore'])` | "Callable only on entities that have filters." (a table gives "Invalid EntityID: expected LuaEntityPrototype, LuaEntity or string", so a drill filter would be a resource entity, not an item) |
| `mining_drill_filter_mode` | nil (settable, no effect) |
| a blueprint of the drill (`create_blueprint`, `export_stack`) | `{"entity_number", "name", "position"}` and nothing else |
| `import_stack` of a drill carrying `filter {filters, mode}` (the codec's guess), `filters [..]`, `use_filters + filters`, `filter_mode`, `mining_drill_filter_mode` | every one dropped: the entity comes back with name and position only |
| the facts read's entity row (`tools/read_facts.py`'s `_ENTITIES` Lua, 146 placeable entities) | `electric-mining-drill {'type': 'mining-drill', 'filter_count': 0, 'mining_drill_radius': 2.49, 'mining_speed': 0.5, 'resource_categories': ['basic-solid'], 'module_slots': 3}` |

So in 2.1.24 no drill has resource filter slots, and M1's fallback is the rule: on a mixed patch
the touching drills are **left out** and the `mixed-patch` line says so. The filtered path stays
behind `placer.filter_slots` (a drill's `filter_count` in facts.json): a modded drill with slots
would take it, with the codec's field shape still a guess (no game writes one, so none can be
read back). The facts line itself: `facts.json` keeps `filter_count` only when it is non-zero
(`read_facts.build_facts`), so the 2.0.77 row's missing key and the 2.1.24 read's `0` mean the
same thing.

`python tools/read_facts.py --dry` on the 2.1.24 server reads the entities and then fails in
`_THINGS`: `LuaRecipePrototype doesn't contain key category` (2.1 moved it); the facts.json re-read
is blocked by that reader line, which is not this part's. facts.json stays 2.0.77.

## Open

(being written)
