# template-seablock

The Sea Block overlay on `kickoff/template`: `new_run.py --pack seablock` copies `template/game`,
then this `game/` over it, then deletes the files `DROP` names: the reactor plant (Sea Block has no
uranium and no oil) and the template's compiled `world.fkp`, which holds the plant; the first build
writes it again. `game/pack` names the pack, so fkcore in the game codebase reads
`fkcore/data/packs/seablock` (FK_PACK overrides it). The kit itself is `setup_v1.py --pack seablock`.
