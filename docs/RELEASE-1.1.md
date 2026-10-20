# Toolkit 1.1 (2026-10-20)

The first point release of the V1 toolkit, from the 0534 run: a Claude player that built red,
green and blue science, oil and robots mostly on its own. 1.1 adds what it ran into, keeps what it
built itself, and adds no rules: every new line is a check (a report, never a gate) or a tool.

## New

- **Chest limits.** `Chest<provider, limit=4>` is the chest's inventory bar in the paste: a full
  chest stops what feeds it. (The run's network held 4800 iron and 5300 copper plates.)
- **Limited-production checks** (Rory: in the game a sink takes what reaches it first, never a
  proportional share). They say what can happen, not how to build; mixed belts and chests are fine
  where production is limited.
  - `CLOG`: a mixed belt that machines feed, or an unlimited chest fed two or more items by
    separate nets. A belt only requester chests feed is limited, so it gets no line.
  - `UNLIMITED`: provider or storage chests without `limit=`, one line per factory.
  - `SHARED_SINK`: such a chest on a net with machines (red science stood at 0% behind a copper
    chest that was first on the belt).
- **Rip estimate.** Before each apply, the diff reads what will be taken up (structures, the items
  in them, the network's robots and storage) and estimates the robot minutes. A big one is a `RIP`
  check with Rory's trick: stop the input and let the factory drain first. When the same names come
  back as new ghosts, it says a factory moved and points to `fk merge`, which keeps both factories
  where they stand (the run's hand merge rebuilt 1300 entities; `fk merge` was never in the
  player's docs). `fk build --to diff` shows it without pasting.
- **`fk fresh X0,Y0,X1,Y1`.** Belts holding items their net doesn't carry (old items from a
  rebuild) are taken up by robots, and the next build lays them fresh: the scripted fix that goes
  through the game (Rory: break the connectors with stale items and replace them; nothing moved by
  script). `fk look` now lists where those belts are and points to it.
- **The player's own patches, as features**: `inserter=inserter` on a row, `item="a,b"` on a
  requester (one chest feeding a one-off crafter), a third lab belt by long-handed inserters, and
  `route --hand inserter` for plain inserters in direct insertion.
- `fk merge`, `fk chests-to-net`, `fk net-to-chests` and `fk build --to diff` are in TOOLKIT.md;
  `fk measure` takes the area first, as the docs always said.

## The player's side

The brief loses the "one product per belt" rule and gains two tips (a chest's `limit=` helps;
drain a factory before a big rebuild) and `fk fresh` under "Ways to get unstuck".

## Compatibility

The 0534 run's game code, through the 1.1 design steps, writes byte-identical layouts (no rip on
its next build). On its base the new checks are five lines: `UNLIMITED` for base, oil and coal, and
`SHARED_SINK` on two nets. 331 tests pass.

## Handing it to a running run

`kickoff/upgrade_run.py RUN --sha SHA` (only with Rory's approval), after the toolkit is on the host
as `fk-v5-SHA`: it swaps `.toolkit`, `bin`, `docs`, `AGENTS.md` and `CLAUDE.md` (the old ones kept
in `.upgrade-<old>`), keeps a player's plain direct insertion (`route --hand inserter`), and prints
the note for the player (a Claude player gets it through `INBOX.md`).

## 1.1.1 (same day)

`fk fresh` also takes up inserters that hold an item the assembling machine they feed doesn't use
(a recipe switch leaves one in the hand), so it covers what the 0534 player's `scripts/unjam.py`
did by moving items, the way the game allows. The live read found none stuck at release.

Left for later (FRICTION.md): re-laying a belt automatically when its net changes, plot moves and
shrinks that leave the old entities, `cover robots` and the kit's network, a new plot over an old
power bridge.
