# Toolkit 2.0.54: a net on both lanes, and the lane a net ends on

Rory, 2026-10-28: "The furnaces should not all drop on the same lane, the router should be able to
find a belting solution that gets half on one side of a lane and half on the other without
prescribing a solution." And: the router should not split a line it laid, but take in where every
building stands and choose a grouping; the test is done without the Stack primitive, so the router
gets no help from cell geometry; and a side pin says which lane the material goes to where the net
leads, not the belt a drop lands on.

## Both lanes

A net that carries more than one lane (7.5/s on yellow) goes on both lanes of its belt. The
router (`route._widen`) splits the net's drivers into two groups. It splits along the axis they
spread on, where the two groups' rates come closest. It lays the net as a pair of itself
(`fkcore.pairs`): each group's tree to its side of a join tile, side-loaded onto that lane, then
one route of both lanes (`net=X|X`) to every consumer. `net NAME width 2:` asks for it outright.

- "More than a lane" is what the drivers make or what the consumers take, whichever is less. A
  chest without a rate counts as one fast inserter, so a mall's products into one chest stay on
  one lane.
- One driver brings one lane, since its own belt is what it is. A two-sided MinerRow is the
  exception: it fills both. `width 2` with one driver says so (`width`).
- When no join routes, the net is laid on one lane as before, and the route report says
  `one lane: no join for both lanes routes (...)`.
- A first route is trimmed to what serves an end, the rule a rebuild keeps a committed route by,
  so an unchanged rebuild keeps it byte for byte.

Measured on paper (`tests/test_width2.py`), with 24 electric furnaces placed one by one and no
Stack, ore from six chests, plates into six gear assemblers:

| layout | before | 2.0.54 |
|---|---|---|
| one row | 11.25 plates/s (one lane full at a merge) | 15.0, ore 15.0, both lanes |
| two facing rows | 11.9 | 15.0 |
| `games/v2-bench/join-big` (three works of 16) | 7.5 | 12.5 |

join-big's three equal works split one against two, so the two-work lane is asked 10/s. Sharing
one work across both lanes through a splitter would bring the last 2.5/s. That is not built.

## The lane a net ends on

`net NAME lane L:` (or `R`) puts the net's items on that lane, looking downstream, where it ends on
a belt. The router lays it through the same join: every driver onto the pinned side, and an empty
one-tile stub belt (`~NAME/z0`) on the other side. With a belt on both sides the join is a
side-load: a belt fed from one side only would be a turn, which keeps its lanes. A rebuild keeps
the stub. `lane` does nothing on a fluid's net, on a width-2 net, or on a net in a `lanes A | B`
pair, and a `width` line says so.

## Ports

A sealed module's port is as wide as the belt just inside it carries its item. Both lanes there
make it a both-lane port, `item | item` written or not, so a two-sided cell's plate port no longer
reads 15/s through a 7.5/s port. A port pinned to one lane (`@e4L`) stays that lane, since the pin
is the promise.

## Not changed

- The live starterbus run: none of its nets carries more than a lane with two drivers, so none of
  its routes changes.
- More than two lanes (several belts, the main bus) is still 2.1.

## Tests

`tests/test_width2.py` (12): both stress lines connected at 15/s on both lanes with no too-thin,
an unchanged rebuild byte for byte, the lane pin both ways with its stub, the syntax, the one-driver
check, and a pair refused as width 2. `tests/test_join.py`'s join-big now expects the join and 12.5/s.
`tests/test_ports2.py`: an unpinned one-item port fed both lanes carries 15/s; a lane-pinned one is still flagged.
