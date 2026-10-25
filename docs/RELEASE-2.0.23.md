# Toolkit 2.0.23: a beltless first cell works — tested in the lab

Rory, 2026-10-25: "can you try in lab to make some test factories that dont use any belts? Lets see
if the router can handle either being forced to use zero belts and only route with inserters, and
also just leave only 1 to 3 tile gaps between buildings so that inserters will be able to reach".

Ran in the lab on a laptop server (fk-play scenario), one chest-fed cell with every transfer a net
between two machines, at three spacings:

| gap | what the router laid | belts | ran |
|---|---|---|---|
| 1 tile | 4 fast inserters | **0** | red science 6.00/min vs 6.00 model (ratio 1.00) |
| 2 tiles | 1 fast + 3 long-handed | **0** | not measured |
| 3 tiles | 1 fast + 3 long-handed | **0** | red science 6.00/min vs 6.00 model (ratio 1.00) |

Every net connected, no `UNROUTED`, no belts anywhere: the router already does direct insertion for
machine-to-machine nets when the machines are 1-3 tiles apart, taking a fast inserter where it fits
and a long-handed one across two or three. So the "first factories: chests, no belt in or out" rule
in the brief is buildable as written.

- **`docs/examples/beltless.fk`**: the cell (13x7), documented in `EXAMPLES.md` — "give the machines
  1 to 3 free tiles between them and the whole cell routes itself".
- **`tests/test_beltless.py`**: all three spacings lay 0 belts with 4 direct inserters and every net
  connected; a one-tile gap takes short hands, a three-tile gap needs a long-handed one; the example
  file itself stays beltless.

No toolkit change was needed; the lab run is what showed it. (One thing for the next run: a lab
`build` of a cell whose gear assembler backs up reads 0/min for that machine in the measure — the
cell is fine, its output is simply full.)
