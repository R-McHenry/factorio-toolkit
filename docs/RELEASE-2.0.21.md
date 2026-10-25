# Toolkit 2.0.21: chests first means no belts, a ramp instead of "grow big", and two checks

Rory, 2026-10-25, on the 1035 run: "the chests first means no belts, it didnt even follow that, maybe
we need to clarify this. The chest fed belt is basically never actually good design. Thats why the
note says chest first and then belt driven later. The chest fed belt is basically just a temporary or
small volume measure", "We should have some scale guide numbers based on a speedrun that describes an
exponential ramp. grow big sounds like a pretty big problem to have, that does not describe a ramp
that starts slow and then gets big", "ask yourself, at the stage of the game you are at, are you
building ten times larger, ten times smaller, or just right for what you need?", "Spending hundreds of
inserters and belts before youve constructed a single one is a sign you are off by an order of
magnitude and are not going to be able to progress", "Robots are supposed to be an easy way to get a
couple items ... The one way to deal with the robots saturating, is to use belts instead. also use
belts to move a chest closer to hub area", and "I dont want to give it the answers".

- **Chests first means no belt in or out.** The row's own little belts are part of the row; a first
  cell must not have a belt carrying items to it or away from it, or a chest feeding a belt. A
  chest-to-belt feed is a temporary measure for a small volume, never a design. The brief and
  STRATEGY say it that way now.
- **"Grow big" is gone; the base grows in a ramp.** A speedrun's pace is the shape: 4 furnaces and
  red science by 10 min, 8-12 and green by 20-25, 24 and blue by 35-45, 48 and production/utility by
  60-75, 1000+ plates/min for the rocket. Each step about twice the last, built when the last runs.
- **The order-of-magnitude question is back in the brief, with weight:** "at the stage the base is
  at, is this ten times too big, ten times too small, or about right?", and "spending hundreds of
  inserters and belts before you have constructed a single one is a sign you are off by an order of
  magnitude". It was in the older briefs and had been lost.
- **Robots are the easy way to get a couple of items**, with no saturation rules: when they are the
  slow part, the answer is a belt. Keep their trips short by putting the chest near the hub and
  belting the item in from the far end (a provider by the hub takes the belt, a requester beside it
  pulls from that): more belt on the routing, far less robot travel.
- **`UNBOUNDED` now names the demand.** A rate-less requester reads as "everything downstream is
  unbounded", which reads as fine; the line now says how much the machines on it take and points at
  `fk stock` to compare: "the 10 machines on it take 3.125/s: `fk stock` says what the network
  holds". A demand, not a required target rate.
- **A coverage roboport is no longer `UNFED`**: the `Roboport` template made a bare roboport report
  "anything has no net" (the 1035 run's `spine`).

Tests: `tests/test_unbounded_demand.py`, `tests/test_roboport.py` (a coverage roboport is not
unfed), and the whole suite (855).
