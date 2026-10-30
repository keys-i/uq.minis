---
name: club-discovery
description: Find UQ student clubs, combine historical exports and read authorised Discord events or club social posts
---

# Club discovery

Run Python commands from `backend/`
Use `uv run mini clubby --help` for the available commands
Ask about interests or guilds only when needed to resolve the person's request

Refresh the current public UQU directory, then search the saved catalogue

```sh
uv run mini clubby refresh
uv run mini clubby list --query gaming
uv run mini clubby list --offset 20 --limit 20
```

The current directory supplies names, official directory links and available social links
The browser populates and refreshes this directory automatically; students only search, open profiles and follow clubs
Use `uv run mini clubby enrich` to complete the current union clubs’ own public profiles, artwork, descriptions and social links
Use `mini clubby profile UNION_LISTED_URL` for a full profile or `mini clubby feed` for the browser’s hourly public noticeboard
UQU’s embedded Rubric university-12 directory is the authority; do not append older Talkwall club records
Interests and descriptions are searchable when present in imported data
Open shortlisted source links before claiming a club is active or offers a particular activity
Directory membership is evidence of a listing, not a guarantee about events or enrolment

Import older exports without changing the source files

```sh
uv run mini clubby import previous-clubs.csv \
  --details previous-details.csv -o out/clubby/historical-clubs.csv
uv run mini clubby list out/clubby/historical-clubs.csv --query consulting
```

Label historical records as historical and check current directory links when possible
The name join normalises case, whitespace and curly apostrophes; it does not guess renamed clubs

For Discord, use an authorised bot token in `DISCORD_BOT_TOKEN`, private `.config/clubby/.env` or supplied JSON
Never reuse a token embedded in the old prototype or print credentials

```sh
uv run mini clubby events --guild GUILD_ID --guild ANOTHER_GUILD_ID -o out/clubby/events.csv
uv run mini clubby events --json scheduled-events.json -o out/clubby/events.csv
```

The bot must already have access to the requested guilds
These commands only read scheduled events; they do not send messages or import announcements
Keep all statuses in the export and use the status column when selecting upcoming events
Start and end times use UTC with explicit offsets
Recurring series are exported as Discord returns them, without expanding future occurrences

For authorised Facebook Pages, professional Instagram accounts with Facebook Login, or LinkedIn organisations, read `docs/sources.md` from the repository root for the required backend settings
Union directory links identify clubs but do not grant permission to read social accounts
Use `mini clubby posts --provider instagram --account ACCOUNT_ID --club "Your club" -o posts.json` for a Buzzy-compatible JSON export
Live reads collect one recent page of at most 100 posts, preserve original URLs and never infer event dates from publication dates
Tokens and supported API versions stay in private backend environment or `.config/clubby/.env`, never in command arguments or browser inputs

Inspect the CSV for names, counts and source links
Failures preserve the previous destination rather than publishing a partial snapshot
Deliver the saved catalogue or a shortlist with the source links and any access limitations
