# Toolkit 2.0.8: a conversation's id is kept as soon as it is known

The loop wrote `claude-session.txt` only when a round ended. On 2026-10-23 the solo run's window was
closed at 22:29, an hour into the first round of a fresh conversation, so the restart could not find
that conversation and began another. Now the id is written as soon as the conversation's first event
names it.
