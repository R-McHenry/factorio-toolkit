# Toolkit 2.1.20: the lab's loaders are 2x1, on whole tiles

Rory (2026-10-31): "it looks like we have loaders placed on half cells so see if you can figure out
the correct loader orientation that doesnt violate the factorio grid and keeps the 2x1 aligned".

2.1.19 fed a sealed module's open belt ports with `loader-1x1`, which the game draws as half a
loader. The lab now stands the game's 2x1 `loader` on two whole tiles outside the frame, its centre
on the edge between them. The orientation, read from the game (2.0.77):

- an output loader facing d has its belt half in front (the d side) and takes from the container
  behind: an `in` port's loader faces into the module, its belt half on the tile at the edge, the
  infinity chest two tiles out;
- an input loader facing d has its container half in front: an `out` port's loader faces out of
  the module, its belt half at the edge, the deleting chest two tiles out;
- a lane pair `a | b`: a belt at the edge, and a loader on each side facing it, side-loading one
  lane each.

Tried on the live lab: every loader linked to its chest; PairT 59.9 circuits/min, PlasT 131.9
plastic/min, LdsBlock making LDS. `fk capture` leaves both loader kinds out.
