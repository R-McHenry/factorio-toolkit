# Toolkit 2.0.56: ore on the lab, and the world's patches copied into it

Rory, 2026-10-28: "The lab behavior with ore patches is not great either, making ore should be its
own first class command ... One that we should be able to do is copy the ore patches from the
world into the lab." (`assessment-20261028\PLAN-CELLS.md`, step 3.)

## Three commands on `fk lab`

```
fk lab NAME --copy-ore X0,Y0,X1,Y1 [--to X,Y]   the world's ore in that map area, shape and
                                                amounts, onto NAME's slot, its top-left at X,Y
                                                of NAME's plot (default 0,0)
fk lab NAME --ore RESOURCE --area X0,Y0,X1,Y1 [--amount N]
                                                that ore over that area of NAME's plot
fk lab NAME --clear-ore                         every ore tile of NAME's slot taken up
```

- Coordinates on the slot are the design's own: NAME's plot starts at the slot's corner.
- Each command replaces the ore in its target area: it takes up what is there first.
- The world is only read, never written. Reads and writes go in 32x32-tile batches, so every game
  call stays far under its 5 s.
- NAME needs a slot first (`fk lab NAME` once); a copy that would run past the slot is refused.

## A rebuild keeps the ore

`fk lab NAME` empties its slot of everything but resources, so copied ore stays across rebuilds.
The apply's seeding (100000 under each drill's tiles) now skips a tile that has ore. Before this,
the game stacked a second resource on it: on the live lab, a rebuild over the copied east patch
added 90 tiles of 100000 on top of 668 real ones.

## On the live lab

`lab-demos/drills` (slot 2000,800): a row of 10 drills on the east iron patch's shape.
`--copy-ore 272,-72,312,-40` copied 668 tiles and 2,365,853 ore (the patch is 2.4M). A rebuild then
seeded only the 11 drill tiles the patch leaves bare. `--ore copper-ore --area 30,0,36,6` put 36
tiles, and `--clear-ore` took up all of the slot's ore.

## Tests

`tests/test_lab_ore.py` (6): the Lua is safe and writes only the lab, a copy lands at the slot
offset after clearing there, a big area goes in batches, ore over an area, the refusals, and the
seeding guard.
