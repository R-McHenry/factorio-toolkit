# Toolkit 2.0.16: a roboport is a machine, and a Literal list sets its own entities

Rory, 2026-10-25, watching the 0928 run: the player "spent dozens of paragraphs just to place a
single chest and inserter next to a roboport", and had "enormous trouble with something as simple as
a two machine blueprint".

The trace of that run (09:45–09:50) is: 3 Lua probes to find that 28 of the kit's 50 logistic robots
sat in a storage chest; no `Roboport` template, so `net bots: bot -> port` against a Literal roboport
said "port names nothing"; six `ssh` reads of `literal.py`, `codec.py`, `fkp.py`, `lang.py`,
`elaborate.py` and `connect.py`; a hand-written `helpers/make_robotloader.py` that called
`codec.blueprint(rows)` on the host; a generated `robotloader.json`; two builds and a wait — and it
ended with the loader unpowered.

- **`Roboport`** is a template. A `Chest<requester, item="logistic-robot", request=50>` beside it and
  `net load: botin -> port` is the whole robot loader: the router lays the direct inserter between the
  chest and the roboport, `cover robots` counts the roboport as coverage and `cover power` powers it.
  The loader is three lines of design instead of a generated blueprint.
- **A Literal's entity list sets its own entities.** A listed entity may carry `recipe`, `config`, or
  the sugar `request` (`{"logistic-robot": 50}`) and `request_filters`; the file's blueprint, if any,
  sets what the list leaves unset. Before this, a listed entity could not say what a requester asks
  for, which is why the two-machine fixture became a blueprint string.
- **Docs:** `LANGUAGE.md` gets the `Roboport` row and the entity-list settings; `EXAMPLES.md` and
  `agent/docs/examples/robot-feed.fk` get the loader, and a note on when robots are stranded.

Both are the same mistake seen twice: a small, common fixture that the language could only express by
leaving the language. Tests: `tests/test_roboport.py` (the roboport is 4x4, the chest asks for the
robots, the router lays the inserter and the net connects) and `tests/test_literal_settings.py` (a
bare list carries a request, a recipe, and the game's fields verbatim).
