# Toolkit 2.1.x: power domains and switching

Draft for the "Power domains and switching" phase of `assessment-20261031\PLAN-2.1.md`; the
integrator gives the number.

## What a player can write now

- **Domains.** Each `power NAME:` line is its own electric network. `cover all` takes everything
  no other domain names. One `power` line builds as before.
- **`copper NAME: A -> B`** joins two domains, or a domain and a switch side (`sw.left`,
  `sw.right`). Two domains joined with no switch are one network, and the cover report says so.
- **`PowerSwitch`** (prelude): closed while its `when` holds.
- **`Accumulator<read=S>`** (prelude): puts its charge, 0 to 100, on its wire.
- **`Decider<if="...", out="...">`** and **`Arithmetic<calc="...", out="...">`**. The condition
  is 2.0's form: `or` between groups of `and`, `red.S` and `green.S` for one colour. A
  combinator's ends are `x.in` and `x.out`. A wire from its `out` to its own `in` is a latch.
  `$p` works in the strings inside a module.
- A wire inside an unsealed module is named from outside: `shedder.hold.S`, `shedder.latch.in`.
  So a `Hysteresis<in, out, lo, hi>` module works without an output port.

## What the build does

- `cover power` covers each domain on its own: poles `power-NAME/pN`, with `domain=NAME` on the
  pole. Pole wiring stays inside a domain (`codec.pole_wires`), also across plots.
- No pole goes where its supply area reaches another domain's machines.
- A copper line runs from the nearest pole in reach of its other end. If none is, a bridge pole is
  added through the cover's search.
- The `.fkp` keeps copper lines as `w` records (colour `copper`). The blueprint writes them as wires
  on connectors 5 and 6 (a switch's right side is 6).
- The wire pass after a paste cuts copper wires between domains, since the blueprint's wires are
  the design's.
- `floorplan` writes `out\power-domains.json`, each domain's poles. The run stats read it.

## New checks

- `no-source`: a domain with no generator and no copper line to one.
- `power-short`: with every switch open, a domain's machines want more than its generators make.
- `switch-never`: a switch whose condition can't change.
- `domain-overlap`: no spot for a pole that powers only its own domain, or two domains name one
  instance.
- `copper`: a copper line that can't be laid (no pole, ends too far, a bad side).

## Run stats

`fk stats` splits power by domain: `power by domain: labs made 0 W, used 1.8 MW; main made 3.1 MW,
used 1.2 MW`. The recorder notes each network's poles, and a network no domain owns is `rest`.

## Measured

- A paste of two domains side by side (laptop server, 2.0.77): the paste's own wires never join
  them. Pasted beside a standing domain, the game's robots auto-connect the new poles, and the two
  were one network from the robots' last build (tick 744) until the wire pass cut it (1 wire, about
  0.1 game seconds later).
- `tests\power\power-shed.fk` on the lab: the switch opened at 19.2% charge and closed at 79.6%,
  once each way. Two networks.

## Fixes on the way

- `settings.live` counted a self-loop wire one way only, so the diff called a latch's own wire
  "by hand".
- A condition that ends with `and` or `or` is refused.
