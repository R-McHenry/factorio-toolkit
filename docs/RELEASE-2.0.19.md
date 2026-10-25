# Toolkit 2.0.19: `fk stock` counts your pack too

The first thing a player carries is in its character's inventory, not in a chest: the 1035 run's
character held 1 burner drill, 1 stone furnace, 1 wood and 8 iron plates while `fk stock` said
nothing about them, so "what do you have" was still a `fk lua` question for the pack.

- `fk stock` sums the character's main inventory as a third bucket and names it: an item carried
  reads `8 carried` in its line, not silently nothing.

The Lua for it was run against the live map (the character's pack reads back exactly).
