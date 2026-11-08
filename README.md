# v5: the Factorio toolkit

The toolkit Rory's AI players build with: a factory language (`.fk`), a rate model, a router, a
build flow that pastes ghosts into the game, and the commands around them. 3.1 is the current
line (`docs\RELEASE-3.1.md`); `fkcore.__version__` says which release this checkout is, and
`CLAUDE.md` says how the repo is worked on. Python stdlib only; the Rust router kernel
(`native\fkroute`) is optional, with a Python fallback.

## Where things are

- **`fkcore/`**: the core. `lang` and `elaborate` (the language), `flow` (the build steps),
  `route` and `compiled` (the router and the one compile store, `out\compiled\<module>\<key>.json`),
  `design` (the per-net route files), `surface` (surface files and their properties: `free`,
  `force`), `alone` and `standin` (a module built alone on a slot of any surface; god-mode
  stand-ins where things are free), `lab` (the thin `fk lab` alias), `terrain` (bare ground and,
  on request, standing entities as obstacles), `robots` and `cover` (roboports and poles from the
  design alone), `apply`, `look`, `sim`, `stage`, `capture`.
- **`agent/`**: what players get. `docs/` holds `FAIR-PLAY.md` (the game's rules), `STRATEGY.md`
  and `BUILDING.md` (advice), `TOOLKIT.md`, `LANGUAGE.md` and `EXAMPLES.md` (how the toolkit
  works); `prompts/` the briefs; `fk.py` the player's `fk` command.
- **`kickoff/`**: new runs (`new_run.py`, the template game folder), the player loop and live
  upgrades (`upgrade_run.py`).
- **`games/`**: paper games the tests build (`spm10`, `redgreen`, `nauvis`, the `lab-*` ones on a
  free surface). **`scenario/fk-play`**: the lab scenario. **`tools/`**: laptop server and live
  checks. **`docs/`**: one `RELEASE-X.Y.md` per release and the design notes per branch.
- **Specs**: `CORE.md` (V1), `CORE-V2.md` (lanes and throughput), `..\CORE-V1.md`; the plans and
  reviews in `..\assessment-*`.

## Run

```
python -m fkcore --help                              # every command, one line each
python -m fkcore rates games/spm10/main.fk           # the rate model on paper
python -m fkcore build games/nauvis/nauvis.build.fkb # the whole flow; reports in out/
python -m fkcore status games/nauvis                 # the nets as routed, the compile store
python -m fkcore look games/nauvis --source design
python -m unittest tests.test_flow                   # one module at a time, never the whole suite
```

With the game link (`FK_LINK=on`, on the game host): `alone`, `standin`, `lab`, `robots`,
`read-terrain --entities`, `look --source world`, `measure`, `capture`, `sim`, `map`.
