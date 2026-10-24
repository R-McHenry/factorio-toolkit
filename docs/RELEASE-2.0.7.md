# Toolkit 2.0.7: the player starts a fresh conversation itself

Rory, 2026-10-23, about the solo run (`20261022-1858-solo`): its conversation reached 466k tokens of
context before Rory asked whether it wanted a fresh session. The loop's own hand-over (`--fresh-at`)
only comes at a round's end, after three rounds in the conversation, and this player's rounds ran
one to three hours. "give it a way to restart itself at a good stopping point before it gets so
long".

- **The player hears when its conversation is long.** At 150k tokens of context, and again every
  100k after, the loop leaves a note (`LONG`, through the PostToolUse hook): pick a good stopping
  point with nothing half-built, bring NOTES.md and GOAL.md up to date, create an empty file named
  `NEW-CONVERSATION` and end the turn.
- **`NEW-CONVERSATION`.** At the next round the loop takes the file into `.loop`, starts a fresh
  conversation from NOTES.md and GOAL.md, and adds the file's text, if any, as a note to the player.
  The old conversation id goes into `claude-sessions.txt` ("asked").
- **The briefs** (core-v1 and lead-v1) say so in one short paragraph.
- **A Stop hook** that keeps a player going (`C:\fk-player\notes\stop_hook.py`, under test in the
  solo run) lets the stop through while the file is there.
