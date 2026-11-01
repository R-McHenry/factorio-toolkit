# Toolkit 2.1.20: no side-load at a collector's merge; blueprints with an icon; lane images

## A collector keeps its own belts off its merges' spare outputs

A tree laid reversed (a collector, and the driver side of a hub) merges its branches in splitters
facing back. Each such splitter has a spare output, pointing at the tile beside the split's feed.
`Grid.keep_clear` already kept another net's belts off that tile; the tree's own later branches
were not kept off it. The hourglass bench's 16to16 hub ran a driver's branch through one, as a
turn: in the game the splitter feeds that belt from behind, so it runs straight and the branch
side-loads onto it (Rory saw it in the lane image).

`steiner.Tree.spare()` now holds those tiles. `free()` and the A* treat them as taken, no split is
made whose spare tile the tree already uses, a run that would cross its own new split's spare
tile is passed over, and `problems()` names any left (`SPARE_FEEDS`). m2m's merge runs keep their
own path off their splitter's spare output too.

The golden examples and the live design are unchanged (60 of 60 identical). The bench's m2m
layouts now side-load nowhere; the 16to16 one pays for it (cost 236 -> 287, 17 -> 25 splitters),
and the balancer's 8to8 and uneven hubs cost 9 more each.

## Blueprints carry an icon

`codec.blueprint` writes one icon (a transport belt). The game took a blueprint without one, but
fbe.teoxoy.com refused it ("could not be loaded"); with it, a `?source=` link opens the layout.

## Lane images (tools)

`python tools/hourglass_png.py OUT --lanes` draws each case lane by lane (`tools/lanes_png.py`):
two strips per belt coloured by the routed solver's load (grey empty, green to red full), turns
bent round the corner, tunnels dashed, splitters framed, side-loads as a white bar, a light arrow
on every belt, each panel cropped to its content.
