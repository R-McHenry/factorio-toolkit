# Toolkit 2.0.25: a chat message is unanswered until the player dismisses it

Rory, 2026-10-25: "I think we can have a handful of sources that make the message pop up, and then
the one way the model can dismiss them."

## What was wrong

Chat reached the player through one narrow pipe: every `fk` command's footer read the journal after
a cursor, printed the new lines once at the end of that command's output, and moved the cursor.
So a message was shown **once**, and it was consumed on **read**, not on answer. In run 1133: 201
`fk` results, 142 piped through `Select-Object`/`Select-String`, **42 of them lost the footer
entirely**; 8 of 12 messages reached the model and 4 were eaten unseen (both supervisor hints among
them). A message that did arrive was one line under a wall of build output, and nothing ever asked
the player to answer it — Rory's "the problem is the thing that I told you about and you ignored".

## What it does now

- **The queue repeats.** `out/chat-ack.json` holds an ack watermark; every command prints every
  message after it, with its age:
  `UNANSWERED CHAT (2): answer with `fk say <reply>`, then dismiss with `fk ack``.
  A message stays under every command until it is dismissed, so a pipe that drops it costs nothing.
- **One way to dismiss.** `fk ack` moves the watermark to now. There is no other: replying with
  `fk say` does not clear it (Rory's rule: answer, do the work, then ack).
- **`fk chat`** lists what is unanswered; `fk chat --all` still shows the whole journal.
- **First use replays nothing**: with no ack file, the first command sets the watermark to the
  current tick, so a fresh run does not get a wall of history.
- **It rides at the end of the footer**, after the research line, so `| Select-Object -Last N` keeps
  it (that is the pipe the player uses most).
- **Second source (harness):** `C:\fk-player\launch.ps1` prepends `fk chat`'s output to the round
  message — the one place no pipe or truncation can reach. A round message is a real user turn; the
  queue makes the message frequent, the round message makes it certain. Only applies to a loop
  restarted after this change.
- Supervisor hints go through the same journal, so they repeat too and stop being a lottery.

## How the player is told

`docs/TOOLKIT.md` (the chat entry) and the brief: a message keeps appearing until `fk ack`; answer
with `fk say`, do the work, then ack.

## Tests

`tests/test_chat_ack.py`: no history replay on first use; a message repeats until acked; `ack` is
the one dismissal; two messages show a count and ages; a journal-less map says so.
