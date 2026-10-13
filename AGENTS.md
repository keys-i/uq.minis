# UQ minis

Mini-specific domain logic lives in `src/minis/<mini>/`
Each `src/cli/<mini>.py` owns its commands, options and terminal workflows
Keep CLI implementations in `src/cli/` without forwarding modules under `src/minis/`
Persistent mailbox logic lives in `src/worker/`
Management registration lives in `src/cli/core.py`, with its implementation in `src/core/mini.py`

Shared helpers, terminal setup and cache storage belong in `src/core/`
Use the common terminal application, consoles and prompt functions rather than separate mini implementations
Keep cache publication, budgets and eviction shared; mini-specific identities and validation stay with the mini
Mini-owned dotfiles, credentials, caches and state belong in `.minis/<mini>/`
Bundled assets belong in `docs/assets/`, and agent skills belong in `skills/<mini>/SKILL.md`

Before handling a task below, read the linked skill and use it to carry out the work
The skill is an operating playbook: inspect the inputs, use the available tools, resolve material gaps, produce the deliverable and check it
Work within the user's existing authority and keep independent work moving while a necessary answer is pending

- [Event](skills/event/SKILL.md)
- [Forms authentication](skills/auth/SKILL.md)
- [Email watcher](skills/agent/SKILL.md)
- [Workflow discovery](skills/discovery/SKILL.md)
- [Course scraper](skills/scrappy/SKILL.md)
- [Countdown videos](skills/timey/SKILL.md)

Use `uv run mini list` to find available minis and `uv run mini <mini> --help` for current arguments
Read the selected skill, execute its authorised CLI workflow and inspect the resulting files or state
Respond like a capable colleague in warm, direct Australian English
Lead with the useful result, explain decisions in the person's terms and link the deliverable
Keep internal orchestration and configuration out of the main answer unless they help the person act
Run `uv run dev check` for lint, formatting, compilation, strict typing and tests
Keep unrelated changes and existing generated output intact
