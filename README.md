# UQ minis

Tools for UQ events, course exports, and an Outlook event watcher. Use them from an AI agent or the CLI.

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

## AI agents

```sh
uv run --extra agents --extra agent mini agents
```

This starts an MCP server. [Connect your agent app](tools/agents/README.md) to generate documents, export courses, submit forms, and manage the watcher. Tools return structured results and reuse the same mini functions as the CLI. Generation never submits; submission is a separate tool.

## Events

Copy [event.example.toml](examples/event.example.toml), or start from [movie night](examples/movie-night/event.toml) or [AGM](examples/agm/event.toml).

```sh
uv run mini event event.toml --form --preview
uv run mini event event.toml --risk --layout form
uv run mini event event.toml --form --risk --preview
```

Outputs go to `generated/` beside the input. Use `-o DIR` to change it, `--force` to replace files, and `--layout form|pack|both` for risk documents. Directory inputs process their event TOML files.

For Forms submission, sign in once through the browser:

```sh
uv run --extra auth playwright install chromium
uv run --extra auth mini auth
uv run mini event event.toml --form --submit
```

Credentials are saved to a private `.env`. Sign-in requires a person.

## Courses

```sh
uv run mini scrappy links -o courses_offerings.csv
uv run mini scrappy details courses_offerings.csv -o courses.csv
```

Use `links --html search.html` to parse a saved search page. CSV exports replace their output file.

## Outlook watcher

Sends risk-assessment replies, follows booking updates, and notifies on macOS. The experimental browser backend uses Outlook web without Apple Mail or Entra app registration. [Setup and limits](docs/agent.md).

```sh
uv run --extra agent playwright install chromium
uv run --extra agent mini agent login --mailbox YOUR_UQ_EMAIL --username YOUR_UQ_SIGN_IN
uv run --extra agent mini agent watch event.toml --event-id ID --attachment approved.docx
uv run --extra agent mini agent install
```

Use `agent status`, `agent stop ID`, and `agent uninstall` to manage it. Check Sent Items before `agent retry-send ID --confirm-not-sent`.

## Development

Minis are functions in `src/minis/`. CLI wrappers live in `src/cli/commands.py`; AI tool adapters live in `tools/agents/`.

```sh
uv run mini list
uv run mini add hello-world
uv run mini hello-world --help
uv run mini rm hello-world
uv run dev check
```
