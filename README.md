# UQ minis

Tools for UQ events, course exports, and an Outlook event watcher. Use them from an AI agent or the CLI.

Requires Python 3.15+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Use uv 0.13+ to download the stable 3.15 runtime automatically

Run `uv run mini` for the interactive picker. Type to filter choices, use ↑/↓ to browse, Tab to complete and Enter to select. Long selected suggestions scroll automatically inside their highlighted row, pause at either end and return smoothly; changing selection resets the caption without changing the value you select

Fifty shaded animals bring threatened and extinct species from around the world into the terminal, with an equal chance for every menu visitor. Mini residents retain their familiar habitats; visitors range from Amur leopards, ring-tailed lemurs and African penguins to dodos, thylacines and Steller’s sea cows. India is represented by tigers, elephants, red pandas, lion-tailed macaques, Nilgiri tahrs, Ganges river dolphins, gharials, Indian pangolins and threatened grassland birds

Each animal has a full body, face, markings and its own foliage, water and ground palette. Alternating suggestion and table rows follow that palette, alongside shared progress and error displays; the name, conservation status, country or region and habitat have distinct colours. Country names use colours drawn from their flags, while regions use habitat colours. Gentle colour transitions enliven the text and scenery without moving the selected value

Animals react when you type, select a choice or correct an invalid answer. Hover for a hint, then click their head, body or nearby object for different movements; pointer targets follow them as they move. Each region cycles through three reactions before repeating, alongside four longer animal-specific routines: hopping, digging, calling, paddling or exploring. The fourth poke brings up a warm species-specific reply bubble; later pokes choose a different quip. Artwork clears when the prompt finishes, leaving validated answers in the scrollback; motion runs only while a prompt is open

Expected errors in interactive runs offer a return to the menu or a review of saved answers and command arguments. Reopening the workflow prefills validated answers for editing; confirmations must be answered again. Answers stay in memory for that mini session and are cleared when you leave it. Actions never retry automatically; an explicit submission retry asks you to check for partial submissions, and upload retries require fresh confirmation. Redirected and `--no-input` runs still fail with a nonzero exit status

Press Esc or Alt+← to return from a mini to the menu, `?` in an empty field or Alt+H for keyboard help, and Alt+M to pause or resume motion. Ctrl+Space opens suggestions, Ctrl+U clears the line and Ctrl+C cancels. Shortcut labels follow your OS: ⌃/⌥ on macOS, Ctrl/Alt on Windows and Linux

Terminals smaller than 80 columns or 24 rows show compact prompts. `MINI_MOTION=0` keeps artwork, captions and text colours still; `NO_COLOR` keeps the interface monochrome and still. Redirected input or `TERM=dumb` uses ordinary text prompts. Editable sculptures, movement frames, depth, material and pointer maps live in [docs/assets/terminal](docs/assets/terminal/), with conservation sources and palette choices recorded in [forest.toml](docs/assets/terminal/forest.toml). Run `uv run python docs/assets/terminal/sculpt.py` to rebuild the 80 × 64 dot sculptures from their editable geometry; append species names, such as `axolotl`, to rebuild just their movement frames

## AI agents

Agents with terminal access use [AGENTS.md](AGENTS.md) to choose a task skill, then run the CLI to complete the work. Read the matching skill, inspect the inputs, run the authorised commands and check the resulting documents, exports or watcher state

```sh
uv run mini list
uv run mini event --help
```

Task playbooks cover [event planning](skills/event/SKILL.md), [browser sign-in](skills/auth/SKILL.md), [booking follow-up](skills/agent/SKILL.md), [course research](skills/scrappy/SKILL.md), [countdown videos](skills/timey/SKILL.md) and [workflow discovery](skills/discovery/SKILL.md). Use explicit preview flags while drafting; submit, send or upload within the user's existing authority

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

Credentials are saved to a private `.minis/auth/.env`. Sign-in requires a person.

For venue selection during event setup, run `uv run mini event event.toml --choose-room`. Choose the campus and minimum capacity, then type a building name/number or room number and use Tab to browse matching entries. Room choices show seats and room type, and rooms with a tour offer `tour` before `select`

The picker uses [UQ's room catalogue](https://campuses.uq.edu.au/list-rooms), bundled as a [compressed catalogue](docs/assets/event/rooms.csv.gz), checked on 9 October 2026. Put a custom list in `.minis/event/rooms.csv` or pass `--rooms PATH`; use the same `campus,building,room,kind,seats,tour` columns. Selection applies to that run's outputs and asks for the Forms capacity answer without changing the source TOML. The catalogue gives capacity and tours; availability still comes from booking. Compression removes the readable CSV from the checkout and package, but does not restrict access to UQ’s public directory or remove the CSV from older Git commits

Existing `.env`, `.timey/` and watcher directories are not migrated automatically. Move saved files to the corresponding `.minis/` location when adopting the new defaults, or use explicit paths such as `--token` and `--state-dir`

## Courses

```sh
uv run mini scrappy                              # interactive menu
uv run mini scrappy links -o courses_offerings.csv
uv run mini scrappy list courses_offerings.csv --query COMP
uv run mini scrappy details courses_offerings.csv --course COMP3400 -o COMP3400.csv
uv run mini scrappy details courses_offerings.csv -o courses.csv
```

The menu browses/searches courses, refreshes links, and scrapes one course or all courses. Use `links --html search.html` for a saved page. `--jobs 1..8` controls concurrent requests (default 4).

Exports validate course codes and links, remove duplicate URLs, and write one CSV header. The final CSV is replaced only when the whole batch succeeds. Failed or interrupted batches keep completed courses in a SQLite checkpoint in `.minis/scrappy/`; rerun the same command to resume, or add `--fresh` to start over. Successful exports clear the checkpoint. To rebuild a damaged dataset, regenerate its links and run `details --fresh`.

## Outlook watcher

Sends risk-assessment replies, follows booking updates, and notifies on macOS. The experimental browser backend uses Outlook web without Apple Mail or Entra app registration. [Setup and limits](docs/agent.md).

```sh
uv run --extra agent playwright install chromium
uv run --extra agent mini agent login --mailbox YOUR_UQ_EMAIL --username YOUR_UQ_SIGN_IN
uv run --extra agent mini agent watch event.toml --event-id ID --attachment approved.docx
uv run --extra agent mini agent install
```

Use `agent status`, `agent stop ID`, and `agent uninstall` to manage it. Check Sent Items before `agent retry-send ID --confirm-not-sent`.

## Timey

Paste a YouTube link, choose a local video or enter search words in the wizard. YouTube searches show five results with a thumbnail, title and duration; highlighting previews a result, selecting fills its canonical link, and **back** lets you search again. Music uses the same picker. Thumbnails use a 40-pixel-wide terminal sample with Lanczos resizing and fall back to the smaller YouTube image when needed. Search reads metadata and thumbnails before you choose; media downloads begin during preparation

Style, position, colour and font choices show tiny previews made by the actual overlay renderer. Describe a font with words such as **spook**, **round** or **arcade**, or try an approximate name such as **ariel**. The font shelf offers named matches: “ariel” suggests Arimo, an Arial-style alternative, for you to review rather than silently replacing the font. Unrecognised words open the shelf instead of requesting a nonexistent Google family. Choose a family, inspect its actual timer sample and accept or reject it. Google Fonts specimen links and local font files still work; bundled fonts need no download. Custom thumbnail files and the opening video frame also have previews. Small or monochrome terminals show text alternatives. Tab completes choices and paths; free-form style briefs and pasted links still work, and blank entries keep the default or skip optional fields

```sh
uv run --extra timey mini timey
```

Requires FFmpeg and ffprobe on `PATH`. YouTube downloads also need [Node.js or Deno](https://github.com/yt-dlp/yt-dlp/wiki/EJS), used by yt-dlp to read YouTube videos

Choose the countdown length, a gap before it starts and a hold after it finishes. `10m`, `25:00`, `1h 30m` and seconds all work. The default gaps are five seconds each. Short backgrounds loop to fill the full timer, with a brief crossfade over the wrap instead of an abrupt cut; longer backgrounds are trimmed. A 20-second clip can fill a one-minute countdown plus both gaps. YouTube downloads request only the segment needed for the timer, or the opening second for a still preview. Audio is kept unless you choose mute

The countdown is the main focus: larger digits, a centred panel and a blank label by default. Use `--label` to add your own text. Only the opening and finishing gaps show a quiet status caption, with fixed digit positions and a subtle reflected sweep around the panel edge. Digit changes settle through a brief eased dissolve, and the edge responds when the countdown starts and finishes. Temple Run uses textured, bevelled temple stone, moss, emerald gems, an idol crest and cracked gold numeral artwork; its gems catch the light while the frame stays still. Stone and numeral artwork are sampled directly at the output size to preserve their detail. Other styles include Minecraft's pixel digits, hearts, inventory slots and XP meter, Subway Surfers-inspired coin badge and outlined lettering, neon, minimal and blurred glass. Glass blurs the live video inside its rounded panel while the surrounding scene stays sharp. Auto selects a preset from the video title, with minimal as the fallback

Before the full export, the wizard offers a silent motion preview lasting up to six seconds. It keeps your actual countdown length and layout, shortens the opening gap to at most one second and shows the first few digit changes. With motion disabled, it uses a still preview. `--preview` still saves a PNG for direct commands

Temple Run's live countdown composes bundled cracked-gold numeral sprites, with [Skranji Bold](https://fonts.google.com/specimen/Skranji) for its quieter labels. Minecraft labels use [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P) and Subway Surfers uses [Bungee](https://fonts.google.com/specimen/Bungee). These are original game-inspired artwork and open fonts; their OFL licences ship with the fonts and no download is needed for preset typography. Supply your own lettering with `--font`; this also replaces Temple Run's numeral sprites. The Temple Run artwork's [generation prompts](docs/assets/timey/art/temple.md) are included in the source

Choose `custom`, type any game or describe a look instead of a preset. Timey asks a signed-in Codex or Claude Code CLI to design the overlay and saves reusable artwork in `.minis/timey/styles/`. `--designer auto` picks the first installed CLI, preferring Codex; use `--designer codex` or `--designer claude` to choose. Codex also sees a small background reference frame. Styles use bounded drawing shapes, typography and a live countdown/progress meter, with no generated Python executed during rendering. Select a saved name in the wizard, pass its JSON file to `--style`, or edit the JSON yourself. `--instructions` creates a custom variation of a preset or refines saved artwork

```sh
# Quick local preview
uv run --extra timey mini timey gameplay.mp4 --length 10m --style minecraft \
  --preview --no-input -o outputs/preview.png

# Render directly without questions
uv run --extra timey mini timey 'https://youtu.be/VIDEO_ID' --length 25m \
  --video-start 1:20 --style temple-run --start-gap 8s --end-gap 10s --no-upload --no-input \
  -o outputs/temple.mp4

# Centred frosted glass with smooth looping
uv run --extra timey mini timey gameplay.mp4 --length 1m --style glass \
  --no-upload --no-input -o outputs/glass.mp4

# Render and prepare an editable YouTube draft and first-frame thumbnail
uv run --extra timey mini timey gameplay.mp4 --length 10m --video-start 30s \
  --style minecraft --metadata --first-frame \
  --metadata-instructions 'A focus timer for study sessions' \
  --no-upload --no-input -o outputs/study.mp4

# Create any style from a brief using your installed, signed-in coding agent
uv run --extra timey mini timey gameplay.mp4 --length 10m \
  --style custom --instructions 'Hollow Knight: bone mask, soul vessel, indigo stone and silver filigree' \
  --designer codex --preview --no-input -o outputs/custom.png

# Use a Google font and the soundtrack from another video
uv run --extra timey mini timey gameplay.mp4 --length 10m --style subway-surfers \
  --font 'https://fonts.google.com/specimen/Bungee' \
  --music 'https://youtu.be/MUSIC_VIDEO_ID' --music-volume 0.4 \
  --no-upload --no-input -o outputs/music.mp4
```

Use `--customise` to reveal the styling, motion, loop and music questions, or pass `--position`, `--size`, `--label`, `--accent '#8FDA53'` and `--font` directly. `--size 2.4` is the default, about 71% larger in width and height than the previous 1.4 baseline; choose 0.5–3 and the panel stays inside safe screen margins on portrait and landscape videos. `--no-motion` disables digit transitions and edge animation. `--loop-blend 0.6` is the default crossfade in seconds, capped at a quarter of very short clips; use 0–2 or `--loop-blend 0` to keep an existing seamless loop's cut. Blended loops start just after their opening overlap, and prepare one reusable cycle instead of building a larger graph for each repeat. Original audio is crossfaded with the video when it is retained

The wizard asks where the background footage should start. `--video-start 1:20` skips the first 80 seconds of a local file or YouTube source; it is separate from `--start-gap`, which controls the opening pause before the countdown. Short sources repeat the footage after that timestamp, including when loop blending is disabled. Timestamps past the source's end are rejected

YouTube video and music clips are cached automatically in `.minis/timey/media/`, with a 2 GiB / 32-clip limit and oldest-unused clips evicted first. Matching video, quality and starting timestamp reuse a cached range for equal or shorter requests; a complete remaining clip also supports longer timers through looping. Cache hits skip YouTube lookup and transfer entirely. Completed clips are published atomically, and interrupted downloads never become cache hits. `--no-cache` forces a fresh download. New downloads request only the required section at the selected height; whole-clip HLS/DASH downloads use up to eight concurrent fragments, and YouTube extractor data is reused through yt-dlp's cache. `--height 720` also reduces download and render work

Fonts accept local TTF/OTF/TTC files and HTTPS Google Fonts specimen, stylesheet or desktop-font links. The interactive picker searches the full Google Fonts catalogue, including Open Sans and non-Latin families, alongside mood and typo suggestions. Its catalogue is cached for a week and remains usable offline; without a cached catalogue, the picker explains that it is using the smaller offline shelf. Downloaded fonts are validated and cached in `.minis/timey/fonts/`. [Google Fonts links](https://developers.google.com/fonts/docs/getting_started) need no API key

`--music` accepts a YouTube video link or a local audio/video file and uses its audio as the soundtrack. Music replaces the original audio by default; `--mix-audio` keeps both, and `--music-volume` sets music volume from 0 to 2. Short music loops to the exact video length and fades in/out. `--mute` silences the original video while retaining explicitly added music. PNG previews skip music downloads

Loading stages include “Grokking the video”, downloading, crafting the overlay, rendering and finishing. Progress shows actual downloaded bytes or media time, transfer speed, ETA where known, rendered frames, fps, render speed and elapsed time. Metadata lookup and agent design show the current stage without an invented percentage. Plain-text logs remain available when output is redirected

`--height 720 --fps 30` reduces rendering work. The timer is limited to 24 hours, with gaps up to an hour each. Video frames stay in FFmpeg; Python streams only a small transparent timer panel once a second. Ctrl+C stops rendering or style design and removes scratch files. Existing outputs are preserved unless you pass `--force`

The wizard asks whether to upload to YouTube. If you choose yes, it offers generated title, description and tags, then lets you edit them and answer visibility, audience and altered-content questions. Generation uses your signed-in Codex or Claude CLI, selected with `--designer`; without either CLI, it builds a factual draft from the timer settings. `--metadata-instructions` adds your intended purpose or audience. Drafts use specific duration and theme wording, natural search terms, an understandable opening summary and accurate countdown timings, following [YouTube's description guidance](https://support.google.com/youtube/answer/12948449?hl=en). This helps describe the video for people and search systems; it does not guarantee ranking, AI citations or recommendations

Choose `first-frame`, `custom` or `youtube` for the thumbnail. `first-frame` extracts the actual opening frame of the finished MP4, including the timer overlay and opening status, into a `.thumbnail.jpg` beside it. It is saved before upload confirmation, so you can inspect it even if you decline the upload. `--first-frame` also works with `--upload-only`; `--no-first-frame` leaves the thumbnail to YouTube. Custom PNG/JPEG files support the current [50 MB API limit](https://developers.google.com/youtube/v3/docs/thumbnails/set); your channel needs custom-thumbnail access

Advanced questions cover category, language, licence, embedding, subscriber notifications and a scheduled publication time with a timezone. Upload details and timer context are saved beside the MP4 as an editable `.youtube.json` draft, and you review title, description, tags, thumbnail and upload settings before confirming. `--metadata --first-frame --no-upload` prepares these files without uploading anything. Existing audience, visibility and advanced settings are retained when regenerating metadata in an existing draft

For the first upload, enable YouTube Data API v3 in your Google Cloud project, configure its OAuth consent screen and create an OAuth client of type **Desktop app**. Download its JSON to `.minis/timey/client_secret.json`, or pass `--client-secrets /path/to/client.json`. Add your account as a test user if the consent screen is in testing mode. [Google's OAuth setup](https://developers.google.com/youtube/v3/guides/auth/installed-apps) explains the steps. The browser is used for Google sign-in; subsequent uploads reuse an owner-only token in `.minis/timey/youtube.json`

```sh
# Upload a saved timer later, using its details draft
uv run --extra timey mini timey outputs/temple.mp4 --upload-only
```

Use `--details /path/to/details.json` for another draft. Unattended uploads require explicit `--yes`; rendering and uploading together also require `--upload --details`. A completed upload leaves an `.uploaded.json` receipt containing its YouTube link and prevents another upload of that output path. If an upload is interrupted, check YouTube Studio before retrying. A failed thumbnail upload preserves the video link in the receipt

YouTube Studio still handles copyright checks, age restriction, monetisation, cards and end screens. Google restricts uploads from unverified API projects to private visibility, even when another visibility was requested, until the project passes its audit. [YouTube upload API limits](https://developers.google.com/youtube/v3/docs/videos/insert)

## Development

Mini-specific domain logic lives in `src/minis/<mini>/`. Each `src/cli/<mini>.py` defines and registers that mini's commands, options and terminal workflows; `src/cli/core.py` registers management commands, and `src/cli/completion.py` handles shell completion. CLI implementations live directly in `src/cli/`

`src/core/` owns mini management, shared helpers, the Typer/Rich/prompt_toolkit stack, cache publication and eviction, and the `.minis/` runtime location. Mailbox storage, transports and background processing live in `src/worker/`. Mini-owned credentials, cache and state use `.minis/<mini>/`; bundled assets use `docs/assets/`

Reusable task skills live in `skills/<mini>/SKILL.md` and are linked from `AGENTS.md`. Repository development scripts live in `tools/scripts/`. `mini add` creates the mini, its CLI registration and a skill scaffold

```sh
uv run mini list
uv run mini add hello-world
uv run mini hello-world --help
uv run mini rm hello-world
uv run dev check
```

For the complete test suite, sync all extras and install Chromium; FFmpeg and ffprobe must also be on `PATH`

```sh
uv sync --locked --all-extras
uv run playwright install chromium
uv run dev check --cov-fail-under=85
```

Tests cover every mini, shared infrastructure and the worker. Shared setup lives in `tests/fixtures.py` and test doubles in `tests/fakes.py`. Browser checks use local pages with external requests blocked, and video checks render short generated clips. Optional checks are reported as skipped when their dependencies are missing

Coverage measures lines and branches, including greenlets, worker processes and CLI subprocesses. CI runs all extras, Chromium and FFmpeg on Linux, Windows and macOS, with an 85% minimum on Linux. Test results and HTML coverage are kept for seven days, including failed runs

Lint, formatting and compilation run once before the test matrix. Packaging rebuilds the wheel from its source archive and checks installed commands, skills and assets away from the checkout. Release checks run the complete suite before publishing

Security CI audits the locked dependencies and gates medium/high Bandit findings. Typer's completion-language option and the worker's validated SQL identifiers have specific false-positive annotations; subprocess calls pass argument lists without a shell

Python 3.15's native lazy imports keep command help from loading browser, document or media dependencies. Timey's preset maps use `frozendict` to prevent accidental changes. On macOS with Python 3.15, `tests/benchmarks/cli.py` measured Timey help at a median 387 ms before lazy imports and 110 ms after, across five fresh processes for each; the help budget is 200 ms
