# Contributing to UQ minis

Build small tools that help students research courses, manage deadlines and find their people
Keep browser and terminal workflows useful, and preserve the person's saved work

Read the [code of conduct](../.github/CODE_OF_CONDUCT.md), [accessibility guide](ACCESSIBILITY.md) and [security policy](../.github/SECURITY.md) before contributing
Use the [issue templates](https://github.com/keys-i/uq.minis/issues/new/choose) for bugs and ideas
Describe the student problem and expected behaviour before proposing a large change

## Set up a checkout

Use Python 3.15+, uv 0.13+ and Node.js 24+
Run these commands from the repository root

```sh
uv sync --directory backend --locked --all-extras
npm --prefix frontend ci
npm --prefix frontend run build
uv run --directory backend --all-extras mini browser
```

Open <http://127.0.0.1:8765>
For React development, leave FastAPI running and use `npm --prefix frontend run dev` in another terminal
Open the Vite address it prints; its API proxy uses backend port 8765

Browser automation needs Chromium installed with `uv run --directory backend --extra auth playwright install chromium`
Timey video workflows need FFmpeg and ffprobe on `PATH`
Only install or configure those external tools when working on the relevant mini
External sign-in and authorised API access are separate from dependency installation

## Keep ownership clear

| Location | Responsibility |
| --- | --- |
| `frontend/` | React, browser presentation, npm tooling and its lockfile |
| `frontend/assets/` | Browser artwork, SVG icons, masks, fonts and audio |
| `backend/src/app/` | FastAPI routes and browser input/output boundaries |
| `backend/src/cli/` | Commands, options and terminal workflows |
| `backend/src/minis/<mini>/` | Mini-specific domain logic shared by both interfaces |
| `backend/src/core/` | Shared terminal, paths, cache and publication helpers |
| `backend/src/worker/` | Persistent mailbox workflows |
| `backend/assets/` | Bundled artwork, fonts and other runtime assets |
| `skills/<mini>/SKILL.md` | Agent operating playbooks, outside both applications |
| `docs/` | Human-facing guides, apart from README and CHANGELOG files |
| `.github/` | Community policies, issue/PR templates and GitHub configuration |

Python configuration, dependencies, tests and development tools belong in `backend/`
React configuration and dependencies belong in `frontend/`
Reuse the shared terminal application and prompts; keep CLI forwarding modules out of mini packages
The import namespace is `uq_minis`, even though the source directories sit directly under `backend/src/`
See [AGENTS.md](../AGENTS.md) for the repository's detailed engineering conventions

## Make and verify a change

Trace the affected callers and saved-data contracts before editing
Prefer existing domain functions over duplicating rules in a route or React component
Use short, descriptive module names, Australian English and concise comments explaining constraints
Comment and docstring summaries omit a final full stop

Add a focused regression test for new non-trivial behaviour or a bug fix
Use synthetic fixtures and mocked external responses so tests don't require real enrolments, mailboxes or credentials
Keep dates, time zones, profile sources and marking-rule evidence explicit
Do not guess missing assessment deadlines or silently change official dates into personal targets
For performance changes, record the workload and actual before/after measurements

```sh
uv run --directory backend --all-extras dev check
npm --prefix frontend run check
git diff --check
```

The backend command runs Ruff, formatting, compilation, strict typing and tests
The frontend command checks formatting, types and lint, then runs Vitest, Playwright interactions and the production build
Frontend tests use checked `.ts` files for pure behaviour and `.tsx` files for React rendering
Use React Testing Library with user-event for component interactions and Playwright for native media, popovers and layout
Install its browser once with `npm --prefix frontend exec playwright install chromium`
Backend tests run in up to four isolated processes with work stealing; use `-n 0` when debugging a single process
Test groups follow their owners under `backend/tests/`, with shared fixtures under `tests/support/`
Use Google-style docstrings for meaningful public contracts and keep comments about constraints rather than restating syntax
For a focused backend test, use `uv run --directory backend --all-extras pytest tests/study/test_planny.py --no-cov`
Changes to interfaces also need the relevant manual checks in [ACCESSIBILITY.md](ACCESSIBILITY.md)
Report checks you couldn't run and why

## Browser and terminal workflows

Both clients call the mini's Python domain code; browser routes must not invoke CLI commands
The browser's secondary settings expose the same practical export and processing choices, while each client keeps controls appropriate to its medium

| Mini | Shared capabilities |
| --- | --- |
| Scrappy / Planny research | Natural-language search, faculty and period filters, weighted ratings, course readiness, SECaT imports, offering/detail exports and resumable batches |
| Clubby / Buzzy | Current union directory, full profiles, public noticeboard, historical imports, Discord events and authorised social reads |
| Eventy | New event details or existing files/directories, room search, editable drafts, logos, document workers and explicitly reviewed submissions |
| Timey | Video search, timing, preset or custom overlays, position, size, colour, font, motion, loop blend, music, resolution, frame rate, previews, publication drafts and reviewed uploads |
| Authy | Browser selection, sign-in timeout, custom form profiles and intended-session refresh |
| Watchy | Mailbox/browser or Graph setup, registration, date window, private state, status, polling, stop and checked unsent-reply recovery |

Browser exports use isolated destinations, so they do not need the CLI's output-overwrite flag
Terminal prompt flags and macOS background-service installation remain host controls
New browser event drafts retain unanswered booking terms and additional questions for explicit review
Upload audience and synthetic-media declarations must be answered rather than inferred

## Protect data and source access

Keep credentials, sessions, caches and saved state in the owning mini's private `.minis/<mini>/` directory
Default CLI/browser state is relative to the backend working directory
Never commit real student marks, private announcements, mailbox exports, risk documents or tokens
Keep fixtures small and remove identifying information from logs and screenshots
Access social accounts and Discord servers only with the owner's authorisation; follow [source setup](sources.md)

Changes to saved data need a migration or recovery path that preserves the original on failure
Do not overwrite existing outputs or remove source data as an incidental cleanup
The retired scraper prototypes are removed; extend Scrappy, Clubby or Planny rather than restoring them

## Send a pull request

Explain the problem, resulting behaviour and relevant validation in the [PR template](../.github/pull_request_template.md)
Keep unrelated edits out of the diff and update affected documentation and playbooks
For screenshots or recordings, use invented student data and include meaningful keyboard or mobile behaviour when relevant
Check and take responsibility for assisted or generated code, including its licensing and provenance
Never upload private project data to an external assistant without permission
