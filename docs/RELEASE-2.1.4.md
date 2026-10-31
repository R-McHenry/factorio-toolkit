# Toolkit 2.1.4: stats for a run with no loop

A run driven from a conversation has no `claude_loop.py`, so nothing took its stats samples
(2.1.0). Now the player's `fk` takes one after a command, at most every 5 minutes:

- `fk stats . --sample` on the host, after the command has finished, with no footer;
- quiet: its output and any failure stay out of the player's command;
- `<run>\.stats-sampled` keeps when it last tried (outside `game\`, so no sync carries it);
- never after `fk stats` itself or `--help`.

The host keeps the samples. `fk stats --history` and `--page` pull them as before. A run with the
loop samples from both, which is harmless: a sample keeps only what is due.

There is no timer: a run samples while its player works, which is when its history moves.

Tests: `tests/test_sample_when_due.py`.
