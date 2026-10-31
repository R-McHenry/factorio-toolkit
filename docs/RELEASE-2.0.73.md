# Toolkit 2.0.73: the 10-30 run's friction (the report_rates hang, fk decon, a way back)

From `C:\fk-player\runs\20261030-1602-opus\FRICTION.md`.

## fk build no longer hangs in report_rates

"`fk build --to report_bom` hangs after step 10 (tier), twice, 10+ min". The step after tier is
the second report_rates, the routed model. The base has a coal belt ring (coal4 round the steel
row), and the required-flow pass (no capacities) carried what went round the ring back in as
more, every round: 157/s and climbing by 0.68 a round, so each coal solve took all 400 rounds
(about 9 s), again in each of the up to 80 rounds of the machine coupling.

- `throughput._topo` enters a ring where it is fed (a node on a ring with an input from outside
  it, found with Tarjan's), so only the edge that closes the ring runs backward. It used to append
  every ring node in name order, which made extra edges backward (`in2b10` sorts before `in2b9`).
- The required flows don't go round a ring: its closing edges carry nothing in that pass. The
  capped pass is unchanged; its capacities already bound a ring.
- The machine coupling stops after `throughput.BUDGET` (60 s) and the report says it did NOT
  settle, as it says for 80 rounds.

On the run's own design (laptop, report_rates:2 only):

| design | before | after |
|---|---|---|
| world.fk as it stands (4593 nodes) | 3 min 39 s, settled in 55 rounds | 11 s, settled in 55 rounds |
| the boot's fm on iron-chest (6020 nodes) | 10+ min (killed) | 25 s, settled in 79 rounds |

The routed figures move where the ring sat: the steel row reads 0.469 at its lowest (was 0), and
`mil/gr` reads blocked at 0 (was 1.000 "as nominal", grenades going round the ring while the
military science maker, short of piercing rounds, took none).

## fk decon works in the live game

"`fk decon X0,Y0,X1,Y1` fails ... LinkError ... 'end' expected near <eof>", with or without
`--name`. `Rcon.lua` joins a script into one line, and `lua_decon_area` had a trailing comment
(`-- cancel_deconstruction returns nothing`) that commented out the rest. `link.lua_one_line`
drops a trailing `--` comment on every line now (outside quotes), so no generator can do it again.

## A way back from a bad paste

"write_layout had overwritten world.fkp, with no copy of the layout before it." Before
write_layout replaces a `.fkp` with different content, it keeps the old one in
`out\fkp-history\<name>.<date>-<time>.fkp`; the last 8 of each are kept.

report_bom's `taken-up` warning counted machines only. It also says when the paste takes up belts
and pipes that carry now while belt or pipe kinds it lays are SHORT: "549 belts SHORT, robots tore
the old mains up before the new ones could be built". `stop_on short-stock` holds such a paste.

## Not toolkit

- "every fk command fails with root@10.77.0.2: Permission denied (publickey)" (23:05): a drop-in
  `/etc/ssh/sshd_config.d/09-hardening.conf` on computah-ct turned root logins off at 23:01 (sshd
  logged ROOT LOGIN REFUSED) until it read `prohibit-password` at 23:25. Nothing changed in fk.
- Not done here: a SHORT re-route that keeps the old route standing until the new one is built,
  `cover power` NO_POWER (a check, which warns), and the other entries.

## Tests

`test_friction_2072`: the one-line join (comments, quotes, escapes, fk decon's whole script), a
belt ring that settles and is entered where it is fed, the coupling's budget, the .fkp history,
and the carriers a paste takes up.
