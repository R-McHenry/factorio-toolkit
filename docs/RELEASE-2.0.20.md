# Toolkit 2.0.20: a flying robot is a working robot

The 1035 player read `fk stock` after a build and saw the fleet collapse: "construction robots
dropped to 2! And logistic robots to 4." Three steps of Lua probes and the alert panel later it
worked out that 46 of them were in the air: a stock read that counts only roboport slots makes a
busy fleet look lost, which is the opposite of what the command is for.

- `fk stock` counts robots in the air as their own bucket: `50 (46 flying, 4 in roboports, 0 in
  chests)`. A robot in a chest is still called out as idle, since that one really is doing nothing.
- "no robots in any roboport" is only said when nothing is in a roboport *and* nothing is flying.

Tests: `tests/test_stock.py` (flying robots are not lost robots). The Lua read the live map: 50
logistic robots, all 50 in the air.
