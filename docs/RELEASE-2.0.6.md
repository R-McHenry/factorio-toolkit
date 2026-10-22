# Toolkit 2.0.6: the player loop finds Claude Code where the desktop app keeps it now

On 2026-10-22 the Claude desktop app moved its bundled Claude Code from the MSIX package's
`LocalCache\Roaming\Claude\claude-code` to `%LOCALAPPDATA%\Claude-Data\claude_<package id>\claude-code`.
`claude_loop.claude_bin` found nothing in the old folders and fell back to a `claude` shim that
looked in the old places too. `auth status` failed, `auth login` failed at once, and the first 2.0.6
solo run's loop logged "not signed in" hundreds of times a second.

- `claude_bin` looks in `Claude-Data` first, then the two old places.
- `ensure_login` waits a minute after a login that fails at once, so it no longer spins.
