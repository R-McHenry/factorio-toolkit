# The lane router (PLAN-4.0 part N): lanes as the search's resource

Written 2026-11-08 on `claude/40-lanes`. DESIGN-LANES-2.1.md (the October branch, Rory's
decisions A1-A7 of 2026-10-24/25) restated for today's toolkit: units routed once with a store,
`NetJob`, the design database, patching by branch, one physics table (`fkcore/lanephys.py`) and
one judge (`lanes.reach`). This is the spec the kernel port follows; `fkcore/lanesearch.py` is the
Python reference, `native/fkroute/src/lane.rs` the same search step for step.

## 1. The model (what October decided, what stands)

- **The lane is the unit.** A belt tile has one heading and two lane slots, L and R looking
  along the flow. A net does not own a belt: a belt tile is two lane slots any nets may hold,
  one item per lane; a net alone on a belt holds one lane and the other is free for the search
  (A6d, "one net per belt is retired"). Two nets on one belt are two lane facts, not a pair job.
- **One physics table.** Everything that happens to lanes is a row of `lanephys` (CORE-V2's
  measured table): keep moves (straight, turn, tunnel, splitter), `side` (both incoming lanes
  onto the near lane), `ug_side` (only the open side's lane goes through, the other is blocked),
  `drop_lane`, `turn_drop_lane`, `mine_lane`, `entry` (how a feed enters: a belt fed from one
  side with nothing behind turns, with something behind or from both sides it side-loads). The
  search, the kernel (`lanephys.table()` as data; nothing in Rust states a rule) and the judge
  read the same rows. A rule anywhere else is a bug.
- **One judge.** What a laid layout's lanes hold is `lanes.reach` over the lane graph
  (`lanes.build` over `connect`), labels carried along every edge by the table. The search
  predicts lanes with the same rows, so it cannot disagree with the judge where the moves are
  the table's; `routed`'s WRONG-LANE stays the audit after the fact.
- **No join by accident** (A6b). A connector next to another net's joins it without anyone
  meaning to: a belt pointing into a belt side-loads or runs on into it; an inserter beside a
  belt picks from or drops onto it; an entrance pairs with the first end ahead. So every move
  checks what it would feed and what would feed it. A join the search chose is a move it priced
  (an entry, a ride, a drop onto a host) and is reported `shared`; anything else is prevented
  (the tile a host's chain ends into is entered only from that chain; a leaf's front is never a
  host; the tile ahead of a belt end is the consumer's own belt) or, where it still happens, a
  check line (`unchosen`: a pair of nets whose items meet on a belt no `shared` line reports).
- **Sharing costs.** A tile ridden on a host costs `ride` (0.15) against 1 for a belt of one's
  own, so nets share where the search finds that cheaper. Negotiation over lane slots (N4): a
  belt lane is a resource `(tile, lane)`, everything else `(tile)`; pres and hist as today.

## 2. The state

`(x, y, h, ex, L, R)`: steiner's belt state (the tile, the heading it arrived with, just exited
an underground) and what the belt's two lanes hold, as small ids: `EMPTY` 0, the job's nets
1..k, `FOREIGN` (a standing carrier's passenger from outside the job). A state on a host's tile
is a **ride**: the net's own belt is not there; its items are on the host's lane it entered on.
A belt's real heading is where its move goes (a step may turn it; a Fixed end turns into its
consumer); a state reached by a stub side-load, a drop root and an exit keep their heading.

## 3. The moves and their lane effects

| move | lanes (the table) | cost |
|---|---|---|
| step, turn | kept | belt (+ turn) |
| jump (an underground pair) | kept (tunnel) | ug |
| split (a splitter cut into a straight own belt, steiner's start) | kept (splitter) | split - belt |
| **side-load** into a belt of the own tree or a host | both lanes onto the near lane; onto an underground end only the lane on the open side, the other blocked (lost); a turn where nothing feeds the target | ride (a host), 0 (the tree: an attachment) |
| **stub**: a new belt across the way with an empty belt behind it | a side-load onto an empty belt, the near lane | 2 belt |
| **ride** a host's chain | the hop's move as the table says (straight, turn, tunnel, side, ug_side), merged with the host's content | ride a tile |
| **leave** a host's chain end (only the net itself aboard) | kept | belt |
| **drop** from a driver machine onto a new belt, a tree belt or a host | `drop_lane` (across: the far lane; in line: the right lane); onto a turn `turn_drop_lane` | hand (+ belt / ride) |
| **tap** into a consumer | picks both lanes: the net's item must be on one; nothing rejected on the other | tap / long_tap |

Every merge is generic: the table's edges move the feed's lanes onto the target's; a lane that
would hold two ids, or a move that leaves the net's own items nowhere, is no move. Hosts are
given as data (`Host`: tile, heading, kind, lanes, its chain `next`, its `feeds`, the free
`leave` tile); the entries into them and the hops along them are precomputed with the table
(`_host_entries`, `_hops`) and checked downstream (`_down_ok`: no lane two ids would share, no
met goal of another net broken), so the kernel only merges. A curve is never entered (a second
feed would turn it into a side-load and move the host's own items); an unfed empty belt is
(a turn). A side-loaded tile keeps the heading the stub gave it.

## 4. Goals, in lanes

A goal is a condition on the lanes at a tile, never a construct:

- a **pair's consumer** (`lanes A | B`, a Fixed belt end): `need = (A, B)`;
- a **wide net** (`width 2`, two driver groups): `(X, X)`; a **lane pin**: `(X, EMPTY)` or
  `(EMPTY, X)`;
- a **port**: what its declaration says (`ANY` where it does not care);
- a **tap** (a machine): the net's item on some lane of the tapped tile; `reject` ids whose items
  the machine would take but must not get.

`lanes_ok(need, L, R, me)`: an id must be there, EMPTY empty, ANY anything, another job net
there or not yet (its lane EMPTY until it is routed), and while the net still has drivers to
attach its own lanes are PENDING (itself or nothing yet); at the end the goal is checked as
declared. A Fixed end reached by a stub must already run the way it leaves.

## 5. A job

A job is k nets (a pair: 2; a wide net: 1 with two driver groups), routed in every order (the
cheapest kept, as October's `best_of` over net order). Per net, a `LaneTree`: consumers first
(forward legs from the first driver: a belt end with the lanes it carries, or a machine's drops
onto a new belt), then every other driver attached to the **stem** (the belts upstream of every
consumer met: a side-load, straight into an unfed root's back, a drop onto a tree belt) or to a
goal by riding a host. After every leg the tree's lanes are propagated again from its roots by
the table (`propagate`: own belts by `fed`, ride states by the move that entered them) and every
goal met so far must still hold, else the leg is refused. Each tree then becomes a host for the
nets after it (its lanes as labels, its riders' items carried on along its chain), the job's
inserters are blocked for them, and a tap another net laid is met by riding to the tile it
picks from (one inserter picks both lanes: a pair's `A+B` tap).

Today's join is one layout of this: A side-loads an empty stub, B side-loads the same tile from
the other side (or rides A's belt); both come out of the search, with no join tile, `reserved`
behind, stub belt or `no_bend` named anywhere.

## 6. Where it lives in 3.x

- A unit routes its nets once with a store; a job is one `NetJob` (a pair's `parts`, a wide
  net's halves) turned into a `LaneJob` (ids, starts with their lanes, sources, goals in lanes).
  N2: after each net lands in a unit, `lanes.reach` labels its carriers incrementally and the
  unit's carriers with a free lane are the next nets' hosts; the design database keeps the
  labels. N3: `pairs.route_lanes` stops enumerating (48 part routes) and runs one job; `_widen`
  is the same job with two driver groups. N4: `_negotiate`'s resource becomes `(tile, lane)`.
  N5: m2m's `LeftTap` is the drop rule's lane choice; ribbons keep their bundle search.
- Patching by branch: a net's route is the connectors its items flow through (the labels), so
  what still serves is lane reach, and a net whose items ride a belt goes stale when that belt
  moves (the dependency follows the flow).
- The record: a belt's `net=` is written by lane from the labels (`A|`, `|B`, `A|B`), never as a
  claim; ownership (`~A/b3`) still says who laid it. Every belt two nets share gets one `shared`
  line in the route report.

## 7. Open, and answered

- *May a net ride another net's belt that carries one lane?* Yes, priced, reported `shared`; a
  rebuild of the host re-lays the rider (Rory, 2026-10-24).
- *The state cap:* one job per search (a pair or a wide net); m2m and ribbons keep their lane
  handling until N5.
- *Templates' lane goals at their ports:* not in this release.
- *Not yet in the search (wave 2):* a splitter branch off a host's belt and the splitter merge
  (October A6e), riding through a splitter, a drop onto a host whose chain the kernel then
  follows, FOREIGN passengers carried off a host (a ride leaves only when the net is alone
  aboard), pres/hist on lane slots, rip-up and re-route (steiner's improve rounds).
