# UQ minis

Create UQ event form payloads and editable risk-assessment documents from TOML. Choose the Microsoft Form, the risk DOCX, or both. Club names, coordinator details, schedules and event descriptions come from your event file.

## Run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
uv sync --locked
uv run mini list
uv run mini --tool event examples/movie-night/event.toml
```

The project exposes `mini` and `dev`:

| Command | Purpose |
| --- | --- |
| `uv run mini --tool <name> <args>` | Run a mini |
| `uv run mini <add|rm|list>` | Manage source minis |
| `uv run dev <check|lint|security|test> <args>` | Run development tasks |

`uv run mini` displays available tools and prompts in an interactive terminal. Only the selected tool is imported. All commands use [Typer](https://typer.tiangolo.com/) with Rich help panels, validated options and readable errors.

```sh
uv run mini --help
uv run mini --tool event --help
uv run mini add --help
uv run dev --help

# Unattended: never prompt, even in a terminal
uv run mini --tool event event.toml --mode both --risk-layout form --no-input
```

When input is piped, prompts are disabled automatically. Missing input or output choices return exit code 2. `--no-input` explicitly disables prompts for event tools; browser authentication requires a person and rejects that flag. Rich respects terminal colour support and `NO_COLOR=1`.

Tool, path and output-choice prompts suggest completions as you type. Press Tab to complete, arrow keys to select, and Enter to accept. Paths entered inside a prompt can contain spaces without shell quotes.

Generate and install zsh completion for `uv run mini …` and `uv run dev …` once, then restart the terminal:

```zsh
uv run mini --install-completion
```

For the current zsh session, use `eval "$(uv run mini --show-completion)"`. Both forms generate shell code from uv and Typer; no completion script is maintained in the repository. Installation writes `~/.zfunc/uq-minis.zsh` and adds its source line to `~/.zshrc` once.

Try `uv run mini --tool ev<Tab>`, `uv run mini --tool event-risk examples/mo<Tab>`, or `uv run mini --tool event-risk --layout f<Tab>`. Commands and choices come from the Typer apps, paths from `Path` annotations, and mini names from source discovery. New minis need no completion wiring or reinstallation. Other shells use [Typer's native completion](https://typer.tiangolo.com/tutorial/install/#enable-completion) through `uv run mini --install-completion` and `uv run dev --install-completion`, then run the installed commands from an activated environment.

## Choose outputs

```sh
# Microsoft Forms JSON only
uv run mini --tool event event.toml --mode form

# Risk document only
uv run mini --tool event event.toml --mode risk --risk-layout form

# Microsoft Forms JSON and a risk document
uv run mini --tool event event.toml --mode both --risk-layout form

# Dedicated minis
uv run mini --tool event-form event.toml --preview
uv run mini --tool event-risk event.toml --layout form
uv run mini --tool event-risk event.toml --layout pack
uv run mini --tool event-risk event.toml --layout both

# A directory of events, with up to four DOCX workers
uv run mini --tool event events/ --mode both --risk-layout both -o generated/ -j 4
```

The risk layouts are `form` (risk assessment), `pack` (event summary followed by the assessment), and `both` (two DOCX files). The existing UQ-style document layout is rebuilt from event data, leaving University approval fields blank. No source template DOCX is bundled; the layout is implemented in `src/helper/risk_docx.py`.

Directory inputs recursively discover `event.toml`, `events.toml` and `*.event.toml`. Outputs default to `generated/` beside the input. Existing files require `--force`; duplicate output names are rejected before writing. JSON and DOCX files are written through temporary files. Batch document generation uses up to four worker processes by default; `-j 1` runs in one process.

Selections can be saved in each TOML:

```toml
[output]
mode = "both"         # form, risk, both
risk_layout = "form" # form, pack, both

[form]
action = "preview"   # preview, submit
```

Missing output selections are prompted in a terminal; unattended runs need explicit options or TOML values. Preview is the default form action.

## Event files

Copy [examples/event.example.toml](examples/event.example.toml). Complete examples are in [examples/movie-night](examples/movie-night/event.toml) and [examples/agm](examples/agm/event.toml).

- `[club]`: club name and responsible officers.
- `[event]`: title, date, room, campus, attendance, `summary` (the filler statement) and `risk_scope`.
- `[coordinator]` and `[schedule]`: contact and setup/event/pack-up times.
- `[catering]` and `[operations]`: inputs to the event-specific risk controls.
- `[form.values]`: answers to the booking form's remaining questions.
- `[application.fields]`: additional labelled rows in the summary pack.
- `[risk_overrides."1"]` through `[risk_overrides."22"]`: optional replacement risk text, with placeholders such as `{club}`, `{event_title}` and `{event_officer}`.

Set a unique `[document].output_name` for each event. Optional `[document].logo` paths are relative to that event file; `--logo` paths are relative to the current directory. Repository artwork is in `docs/assets/`.

## Browser sign-in and submission

```sh
uv sync --locked --extra auth
uv run --extra auth playwright install chromium
uv run --extra auth mini --tool auth
uv run mini --tool event-form event.toml --submit
```

Run Playwright through `uv run --extra auth`, rather than a bare `playwright` command: the package belongs to this project's environment. Browser installation is a one-time step per Playwright browser version.

The auth mini opens a visible browser for you to sign in. It captures the configured form's outgoing verification/session headers and endpoint-scoped cookies, then writes `.env` locally. If Forms does not send those headers on page load, complete its fields and click Submit once in that window; the auth window blocks Forms response POSTs so this capture does not submit an event.

Use `--browser chromium|firefox|webkit|chrome|edge`; install the matching Playwright engine first (Chrome and Edge use an existing supported installation). This uses [Playwright's supported browsers and operating systems](https://playwright.dev/python/docs/browsers), not arbitrary browser profiles. Native Safari and an OAuth redirect returning Forms cookies are not supported. Live sign-in depends on Microsoft's current Forms requests and your organisation's sign-in policy.

The four values are:

```dotenv
UQ_FORMS_COOKIE=some_cookie
UQ_FORMS_VERIFICATION_TOKEN=some_token
UQ_FORMS_SESSION_ID=some_id
UQ_FORMS_MUID=some_muid
```

An empty credential example is in `examples/.env.example`. Values are never printed or included in form JSON. `.env` is ignored and written with owner-only permissions on POSIX. Refresh it with `uv run --extra auth mini --tool auth --force`; other existing `.env` entries are retained. Windows filesystem ACLs govern access there. Submission reads `.env` from the working directory; existing environment variables take precedence. For a different credential file, use `uv run --env-file <path> mini --tool event-form event.toml --submit`.

The submission client uses HTTPS with TLS verification, bounded timeouts, no redirects and no environment proxies. It sends credentials only to `forms.cloud.microsoft`. There are no automatic submission retries.

The supplied question IDs and endpoint live in `src/helper/uq-event-booking.toml`. To use another profile, pass `--form-profile path.toml`, or set `[form].profile` relative to the event file. This browser-session Forms API is not a stable public OAuth API; changes to it may require updating the profile or auth capture.

## Add a mini

```sh
uv run mini add hello-world
uv run mini --tool hello-world --help
uv run src/minis/hello_world/__init__.py
uv run mini rm hello-world
```

`add` writes a Typer app in `src/minis/hello_world/__init__.py`, with a decorated `run()` command and `main(argv=None)` entrypoint. Put the mini's implementation in `run()`; additional helpers can live within its module or shared `src/helper/`. Discovery needs no registry or extra dispatcher. `rm` deletes that named module and all files inside it. Both management and development commands require an editable project checkout.

Existing minis also run directly, for example:

```sh
uv run src/minis/event_risk/__init__.py event.toml --layout form
```

## Develop and build

```sh
uv run dev lint                         # Ruff --fix, then format
uv run dev lint --check                 # Check lint and formatting without edits
uv run dev check                       # Lint, format check, bytecode compile, tests
uv run dev test -x                      # pytest with branch coverage and .cache/coverage.xml
uv run --group security dev security   # Bandit and dependency vulnerability audit
uv build --no-sources -o .cache/dist                  # Wheel and source archive
```

`dev lint` combines formatting and lint fixes; Ruff's formatter has no `--fix` flag because formatting is its default. Test arguments are forwarded to pytest; security arguments go to pip-audit. Generated coverage, test/lint caches and distributions live under `.cache/`; setuptools metadata lives under `src/`. The implementation is `tools/scripts/script.py`, and its independent Ruff/Bandit configuration is in `tools/config/`.

Ruff checks PEP 257 docstring formatting, with final punctuation rules disabled to keep summaries free of trailing full stops. CLI help and completion load document, HTTP and browser libraries only when an operation needs them. Measure five-run startup and two-event generation medians with `uv run tests/benchmarks/cli.py`.

Python source lives directly in `src/`, installed as `uq_minis` using [setuptools package mapping](https://setuptools.pypa.io/en/stable/userguide/package_discovery.html). Auxiliary tooling installs separately as `uq_minis_tools`. uv handles environments, dependency locking, execution and builds. Running a mini executes Python; it does not create a standalone executable.

```text
src/
  __init__.py
  cli/__init__.py
  minis/{auth,event,event_form,event_risk}/__init__.py
  helper/{common,forms,risk_docx}.py
  helper/uq-event-booking.toml
tools/
  scripts/{mini,script}.py
  config/{ruff,bandit}.toml
docs/assets/uq-logo.png
tests/
examples/{agm,movie-night}/event.toml
```

## Automation

- `checks.yml`: locked installs, lint/format/coverage tests on Linux Python 3.12, Windows 3.13 and macOS 3.14, plus a Linux package build.
- `security.yml`: Bandit, dependency audit (including the auth extra), dependency review and Python-only CodeQL.
- `release.yml`: version-tag validation, checks, distribution validation, SHA-256 sums, attestations and a GitHub release for `vX.Y.Z` tags. It does not publish to PyPI.
- `.github/dependabot.yml`: weekly Python dependency updates, grouping minor/patch changes.
- `.github/workflows/dependabot.yml`: requests squash auto-merge only for Dependabot minor/patch Python updates with compatibility strictly above 80%, no maintainer edits and a matching PR head commit.

All actions use full SHA pins with version/SHA comments at the top. Existing pins were retained; their tag correspondence has not been verified in this local session. Actions updates are manual because Dependabot is configured only for Python.

Auto-merge requires repository auto-merge enabled, required checks configured in branch protection, and a Dependabot secret named `DEPENDABOT_METADATA_TOKEN` with access to compatibility metadata. Missing scores do not qualify. Compatibility scores describe Dependabot's observations across projects; they do not replace this repository's required checks. The privileged workflow never checks out PR code. These repository settings and workflows must be enabled externally; this task only edits local files.
