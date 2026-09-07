# UQ minis

Generate UQ event booking JSON and editable risk-assessment DOCX files from TOML.

## Run

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv sync --locked
uv run mini --tool event examples/movie-night/event.toml --preview
```

Copy [event.example.toml](examples/event.example.toml) for your own event. See the [movie night](examples/movie-night/event.toml) and [AGM](examples/agm/event.toml) examples for completed files.

Set a unique `[document].output_name` per event. Outputs go to `generated/` beside the input file; use `-o <directory>` to change this or `--force` to replace existing files.

## Outputs

```sh
# Microsoft Forms JSON
uv run mini --tool event-form event.toml --preview

# Risk assessment DOCX
uv run mini --tool event-risk event.toml --layout form

# Both
uv run mini --tool event event.toml --mode both --risk-layout form --preview

# Batch
uv run mini --tool event events/ --mode both --risk-layout form --preview -o generated/ -j 4
```

Risk layouts: `form` for the assessment, `pack` to prepend an event summary, `both` for two DOCX files. University approval fields stay blank.

Directory inputs recursively find `event.toml`, `events.toml` and `*.event.toml`. Duplicate output names are rejected.

Save defaults in the event file:

```toml
[output]
mode = "both"        # form, risk, both
risk_layout = "form" # form, pack, both

[form]
action = "preview"   # preview, submit
```

CLI options override TOML values. Missing choices prompt in a terminal; scripts need explicit options or saved defaults. Use `--no-input` to disable prompts. Preview is the default unless submission is selected in TOML or with `--submit`.

## Submit to Microsoft Forms

```sh
uv sync --locked --extra auth
uv run --extra auth playwright install chromium
uv run --extra auth mini --tool auth
uv run mini --tool event-form event.toml --submit
```

Sign in through the browser. If capture stalls, complete the fields and click Submit once; the auth window blocks submission while capturing credentials.

Credentials are saved to `.env` in the working directory; see [.env.example](examples/.env.example) for the variable names. Keep them private. Existing environment variables take precedence. To refresh credentials:

```sh
uv run --extra auth mini --tool auth --force
```

Sign-in requires a person. The Forms session API can change, and submissions are never retried automatically. Use `--form-profile path.toml` for a custom [form profile](src/helper/uq-event-booking.toml).

## Minis and completion

```sh
uv run mini list
uv run mini --help
uv run mini --tool event --help
uv run mini --install-completion
uv run mini add hello-world
uv run mini --tool hello-world --help
uv run mini rm hello-world
```

In zsh, completion covers `uv run mini` and `uv run dev`; restart the terminal after installation.

`add` creates `src/minis/hello_world/__init__.py`. Put the implementation in `run()`; discovery is automatic. `rm` deletes the module and everything inside it. These commands require an editable checkout.

## Development

```sh
uv run dev lint                       # Fix lint and formatting
uv run dev lint --check               # Check without edits
uv run dev check                      # Lint, formatting, compilation and tests
uv run dev test -x                    # pytest with coverage
uv run --group security dev security  # Bandit and dependency audit
uv build --no-sources -o .cache/dist  # Wheel and source archive
```

Application code is in `src/`, tooling in `tools/`, and tests in `tests/`. Build output, reports and caches go under `.cache/`.
