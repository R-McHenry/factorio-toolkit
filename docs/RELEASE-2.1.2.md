# Toolkit 2.1.2: vision (zoom, layers, images)

Draft for the 2.1 vision release (planned as 2.1.14; the integrator gives the number). Plan:
`assessment-20261031\PLAN-2.1.md`, "Vision", and phase 15 of "Order".

## What `fk look` does now

- `--zoom N` draws N tiles in a cell (1, 2, 4, 8, 16 or 32).
- `--layers NAME,...` or `--layers all` adds a panel for each layer, with legend lines.
- `--image [PATH]` writes a PNG instead of the text renders and prints its path.

At zoom 1 with no layer and no image, the look is 2.0.78's, byte for byte.
`tests/test_vision.py` checks this against four fixture captures, using lines written by
the 2.0.78 tree itself (`tests/data/vision/look-z1-2.0.78.json`).

## Zoom

- A cell shows what matters most in it, in a fixed order (`vision.decide`). A machine comes
  first, then a roboport, then a turret. Then belt, when at least half of the cell is belt, drawn
  as its main direction. Then tanks, chests, accumulators, solar panels, beacons and radars. Then
  any belt, pumps, inserters, combinators, pipes, poles, power switches and walls.
- From zoom 8 up, a plot is its outline, with its name and how many machines stand in it.
- A map look is zoom 8 and up, or an area of more than 65536 tiles. It reads counts per cell
  in the game (`link.lua_vision`), not every entity. It takes no snapshot and gives no verdicts.
- The game counts each entity once in every cell its bounding box touches, as `scene_cells`
  does for a snapshot. The class table goes to the Lua from `vision.py`, so both sides count the
  same way. A test checks the two give the same grid.
- Fair play: in play mode, a look above zoom 1 reads only chunks the force has charted. An
  uncharted chunk is blank, and it never counts as a difference. The lab is all charted.

## Layers

Each layer comes from one `Facts` record, and the game and the design fill the same record. The
game's facts come from `vision.facts_from_read`, the design's from `facts_from_design`.

- **robots:** each logistic network's area in its own key, construction areas, and robots per
  network (busy, idle, in flight, docked, charging). Ghosts outside every construction area are
  marked. The design's networks are roboports whose logistic areas touch.
- **power:** each electric network's supply area, machines with no power or low power, and power
  switches with their state. In the design, a network is a pole wire component.
- **defense:** turret ranges by type, with ammo and empty turrets. Also land mines, walls and
  gates, and walls outside every turret's range (a gap). Nests and worms too. The design uses
  `TURRET_RANGE`; the game gives its own range.
- **pollution:** each chunk's `get_pollution`, in four bands. Nests the pollution reaches are
  marked.
- **pipes:** each fluid segment has a letter, its fluid and how full it is. Pumps and tanks are
  marked, and so are machines with a fluid connection nothing meets.
- **recipes:** a short tag per machine, with its status. The tags are a data file,
  `fkcore/data/recipe-tags.json`, so the prelude can own it later. A recipe missing from the file
  gets a tag made from its name. Design and live share their keys.
- **tags:** the design's plot outlines and instances, from the `.fkp` files.

Pollution and pipes are the game's only, since the design doesn't know them.

## Images

`fkcore/png.py` writes the PNG with `zlib` and `struct`, so fkcore stays stdlib-only. It has an
embedded 5x7 font. The image has the design and the live render side by side. It draws cells in
colour, then layer tints, squares, circles and boxes, then labels, then the legend lines. The
default path is `<game>/out/look-X0_Y0_X1_Y1-zN.png`.

## The game read

`link.lua_vision` reads a batch of 64 chunks at a time (`VISION_CHUNKS_PER_CALL`).
`link.lua_vision_wide` reads what reaches into the area from outside it: roboports within 70
tiles, turrets within 40, and poles within 10. Both only read. They register nothing, and they
write their reply to script-output, as the snapshot does.

## Measured on a laptop server

`python tools/laptop_server.py vision` (Factorio 2.0.77, 2026-10-31) builds a test base. Its
outputs are in `out/vision-check/`.

- **The small base:** games/lab-sense, plus two power networks joined by an open switch, two
  roboports in two logistic networks with robots flying, and ghosts outside coverage. Also gun and
  laser turrets (one empty), a wall with a gap, land mines, a nest and a worm, pollution, two
  pipelines with a pump and a tank, and a chemical plant no pipe meets.
  - It was looked at with `--layers all` at zoom 1, 4 and 16, as text and as a PNG: 0.6, 0.15 and
    0.08 s.
  - Zoom 1 with no layer gives the same lines as the plain look over the same capture.
- **The big base:** 1024 x 1024 tiles with 87,040 entities, in 16 game calls, the longest
  0.1 s.

  | look | total |
  | --- | --- |
  | zoom 32 | 1.2 s |
  | zoom 16 | 1.4 s |
  | zoom 16, all layers | 2.7 s |
  | zoom 8 | 1.5 s |

- **Fair play:** on nauvis in play mode, a map look over two built chunks drew both blank, with
  no machine read.
  - A headless server with no player charts nothing, even after `force.chart`. So on a laptop
    server every play-mode chunk is uncharted. The unit tests cover a half-charted area.

## Not in this release

- Trains and player names (out of 2.1).
- A low-power machine is shown when the game says `low_power`. The check on the laptop server
  had none.
- A furnace with nothing to smelt has no recipe in the game, so its tag is `-`.
