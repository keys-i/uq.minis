# UQ minis

Small tools for student life, with a React browser interface and Python CLI: course research, assessment planning, marks, club events, event documents and countdown videos

Requires Python 3.15+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Use uv 0.13+ to download the stable 3.15 runtime automatically

## Browser and project layout

Run this from the repository root to build React and start FastAPI

```sh
npm --prefix frontend ci
npm --prefix frontend run build
uv run --directory backend --all-extras mini browser
```

Open http://127.0.0.1:8765 — no app installation is needed for the student using the browser
The local server runs on your computer; cross-device access needs a separately hosted service

`frontend/` owns React, Vite, npm configuration and its lockfile
`backend/` owns Python, uv configuration and lockfile, tests and assets
FastAPI routes live in `backend/src/app/`, CLI workflows in `backend/src/cli/`, mini logic in `backend/src/minis/` and shared code in `backend/src/core/`
Repository-wide agent playbooks live in `skills/`, outside both applications
Both interfaces call the same Python implementations
The browser uses a bright illustrated campus crew, rounded lettering and colourful cards, with keyboard focus, reduced motion and compact mobile layouts
The CLI keeps its shaded animal artwork and habitat palettes
Discovery cards use real club logos and event artwork, with full-card title links and separate Follow/Save controls
Nudgy previews an earlier target as you move its slider; official dates stay unchanged

On this Mac with Python 3.15, 50 local API searches across 3,452 offerings measured a 35.50 ms median when reloading the CSV for each request and 2.93 ms using the bounded index cache, with a 4.16 ms cached p95
A 20-assessment drop-lowest marks scenario measured a 0.24 ms median across 100 calls
These are local measurements using FastAPI TestClient, not hosted-network or browser-rendering timings

For development, run `npm --prefix frontend run dev` alongside the backend and open Vite's local address
The frontend proxies API requests to FastAPI on port 8765
Run `npm --prefix frontend run check` and `uv run --directory backend --all-extras dev check` for validation

[Contributing](docs/CONTRIBUTING.md) · [Accessibility](docs/ACCESSIBILITY.md) · [Security](.github/SECURITY.md) · [Code of conduct](.github/CODE_OF_CONDUCT.md)

**Run the remaining Python command examples from `backend/`**
State, including marks and credentials, lives under that working directory's `.config/`
Existing state is kept in its original location; move it deliberately or use explicit paths

## Planny

Start in Scrappy to select your enrolled courses, then use Planny for assessments and marks, Buzzy for your combined calendar and Clubby to discover societies
Scrappy defaults to the current teaching semester, with natural-language search, faculty filters, review rankings, offering badges and a branching prerequisite tree
Hover or focus a tree node to trace its coloured paths; official prerequisite wording stays visible alongside separate assumed knowledge and topics to brush up on
Enter completed courses and skills to check published requirements, and compare the actual UQ offerings before adding one to your plan
SECaT imports retain their question, semester and sample size alongside attributed student reviews
App light/dark themes leave wildlife habitat clocks unchanged
The reading picker supports 138 languages through compatible on-device translation or the optional Microsoft Translator adapter
See [university access, translation setup and source limits](docs/access.md) for the verified UQ login protecting event, mailbox and bulk catalogue actions

Choose enrolled courses in Scrappy without waiting for live profile access, then attach the actual teaching period and campus profile
`mini scrappy catalogue` crawls the official programs-courses.uq.edu.au index; review refreshes retain that official catalogue and its checked requirements
Review imported assessments before adding them; dates without an exact year and time stay unset
If UQ blocks direct profile access, open the official link, save its HTML and import that file

Planny keeps assessments, a Gantt timeline and marks together; Nudgy sets earlier personal targets while keeping official dates visible
Marky calculates weighted scenarios with per-assessment PAFs, penalties, hurdles and equal-weight drop-lowest groups
Course-specific rounding, bonus, scaling or replacement rules need manual review and adjustments; a projection is an estimate, not an official grade

Buzzy is a separate colour calendar combining official deadlines, personal targets and followed or saved society events
Clubby discovers societies and their announcements; Buzzy also keeps announcement imports and authorised social connections available
Follow clubs or save events to include them in Buzzy
Eventy combines event preparation with booking and email follow-up; account connections live behind the sidebar avatar rather than separate Authy and Watchy pages
Calendy provides an editable JSON backup and live calendar subscriptions, with choices for device calendars, Google, Outlook and other apps
Google and Outlook subscriptions need a securely hosted feed; the local device feed works while the backend is running
See [source access and connection setup](docs/sources.md) for Discord, Meta and LinkedIn

```sh
uv run mini scrappy links -o .config/scrappy/offerings.csv
uv run mini clubby refresh
uv run mini planny show
uv run mini buzzy calendar -o semester.ics
uv run mini planny marks
```

The CLI uses the same private plan as the browser
Use `mini planny show > plan-backup.json` to keep an editable backup, then import a reviewed JSON file with `mini planny import reviewed-plan.json`
Replacing an existing plan requires `--force`; concurrent edits are rejected so an import cannot silently overwrite a newer browser save

Run `uv run mini` for the interactive picker. Type to filter choices, use ↑/↓ to browse, Tab to complete and Enter to select. Long selected suggestions scroll automatically inside their highlighted row, pause at either end and return smoothly; changing selection resets the caption without changing the value you select

Fifty shaded animals bring threatened and extinct species from around the world into the terminal, with an equal chance for every menu visitor. Mini residents retain their familiar habitats; visitors range from Amur leopards, ring-tailed lemurs and African penguins to dodos, thylacines and Steller’s sea cows. India is represented by tigers, elephants, red pandas, lion-tailed macaques, Nilgiri tahrs, Ganges river dolphins, gharials, Indian pangolins and threatened grassland birds

Each animal has a full body, face, textured markings and its own foliage, water and ground palette. Fur keeps its natural colour, with flag colours in the lighting and surroundings. Alternating suggestion and table rows follow the habitat palette, with a softly tinted selection and coloured chevron, alongside shared progress and error displays; the name, conservation status, country or region and habitat have distinct colours. Static flags are twelve dots high, in three rows of mascot-sized braille beside status, country and habitat, preserving each flag's proportions to the nearest dot. Shared ranges show separate flags, and regional labels use continent or globe silhouettes. Long labels scroll without moving the flags

Animals react when you type, select a choice or correct an invalid answer. Hover for a hint and a glance, then click their head, body or nearby object for different movements; pointer targets follow them as they move. Feet lift and plant during walking, ears and tails settle after head movements, foliage sways, swimming leaves a wake and digging raises dust. Each region cycles through three reactions before repeating, alongside four longer animal-specific routines: hopping, digging, calling, paddling or exploring. The fourth poke brings up a warm species-specific reply bubble; later pokes choose a different quip. Artwork clears when the prompt finishes, leaving validated answers in the scrollback; motion runs only while a prompt is open

Expected errors in interactive runs offer a return to the menu or a review of saved answers and command arguments. Reopening the workflow prefills validated answers for editing; confirmations must be answered again. Answers stay in memory for that mini session and are cleared when you leave it. Actions never retry automatically; an explicit submission retry asks you to check for partial submissions, and upload retries require fresh confirmation. Redirected and `--no-input` runs still fail with a nonzero exit status

Press Esc or Alt+← to return from a mini to the menu, `?` in an empty field or Alt+H for keyboard help, and Alt+M to pause or resume motion. Ctrl+Space opens suggestions, Ctrl+U clears the line and Ctrl+C cancels. Shortcut labels follow your OS: ⌃/⌥ on macOS, Ctrl/Alt on Windows and Linux

Every mini uses the same input, navigation, alternating rows and selection treatment. The two-column interface starts with 55% of the terminal width for the scene and 45% for content and its gutter. On extra-wide terminals the left panel stops at 96 columns so the menu stays close to the artwork; sculptures adapt up to 184 × 112 dots with matching pointer targets. Thumbnails and timer samples occupy that same panel, fitting its available cells without stretching and sampling the original image again when resized. Image renderers have a 512 × 512 pixel budget; the current layout uses up to 92 × 128 pixels, with two vertical pixels per terminal cell. Selected samples remain visible through subsequent inputs and compact loading stages on the right. Below 80 columns or 24 rows, prompts retain a still animal portrait when at least 44 columns are available. `MINI_MOTION=0` keeps artwork, captions and text colours still; `NO_COLOR` keeps the mascot visible in monochrome. Redirected input uses ordinary text prompts; an interactive `TERM=dumb` terminal keeps a still portrait without cursor animations

Choices use `>` on the highlighted row, with alternating habitat colours across the full row. Numeric ranges use sliders, and stepped options such as resolution show named stops. Date inputs use a calendar: arrows move by day, Tab switches to month or year, and Enter keeps the date. Time inputs have paired hour/minute dials with arrows, Tab, wheel and pointer controls. Marker movement eases into place when motion is enabled. Type values directly whenever that is quicker

File inputs complete nested folders and filenames, including paths with spaces and `~/` paths. Tab on a highlighted directory descends into it. Menus retain draft values for recovery without displaying an action-by-action receipt; final reviews show the relevant details, and saved results appear after completion. Use Alt+↑/↓ or the mouse wheel to scroll a long review

Animal references guide the 50 species' anatomy, feet, feathered wings, flippers and tail movement. Editable [anatomy profiles](backend/assets/terminal/anatomy.toml) preserve pointed fins, swept horns, tapered tails and different body contours; jointed wings coordinate shoulders, elbows, wrists and feather fans. Sculptures are baked at 224 × 160 dots and move at 24 frames per second, then fit the terminal's actual cells. Natural coats retain flag-coloured highlights and surroundings. Underlined animal names with ↗ open their reference page; Alt+A does the same while preserving the current input. [Anatomy and movement notes](docs/animals.md) document all species and distinguish observations from reconstructed timing. Geometry lives in [sculpt.py](backend/assets/terminal/sculpt.py), with conservation sources, palette choices and natural reply bubbles in [forest.toml](backend/assets/terminal/forest.toml). Run `uv run --directory backend python assets/terminal/sculpt.py` to rebuild the sculptures; append species names, such as `axolotl`, to rebuild just their movement frames

## AI agents

Agents with terminal access use [AGENTS.md](AGENTS.md) to choose a task skill, then run the CLI to complete the work. Read the matching skill, inspect the inputs, run the authorised commands and check the resulting documents, exports or watcher state

```sh
uv run mini list
uv run mini event --help
```

Task playbooks cover [event planning](skills/event/SKILL.md), [browser sign-in](skills/auth/SKILL.md), [booking follow-up](skills/agent/SKILL.md), [course research](skills/scrappy/SKILL.md), [countdown videos](skills/timey/SKILL.md) and [workflow discovery](skills/discovery/SKILL.md). Use explicit preview flags while drafting; submit, send or upload within the user's existing authority

## Events

Copy [event.example.toml](backend/examples/event.example.toml), or start from [movie night](backend/examples/movie-night/event.toml) or [AGM](backend/examples/agm/event.toml).

In the interactive wizard, enter a new `.toml` path to collect the event details, choose the date, adjust the schedule dials and find a venue. Review and save the editable TOML before generating any documents. Existing TOML files open as inputs and are never replaced by setup. Booking drafts leave the form's additional questions and terms unanswered for review before submission

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

Credentials are saved to a private `.config/auth/.env`. Sign-in requires a person.

For venue selection during event setup, run `uv run mini event event.toml --choose-room`. Choose the campus and minimum capacity, then type a building name/number or room number and use Tab to browse matching entries. Highlight a room and press Right for its photo or Left for its virtual tour; the picker stays open until you accept the venue. Plain-text menus also offer the available preview links before selection

The picker uses [UQ's room catalogue](https://campuses.uq.edu.au/list-rooms), bundled as a [compressed catalogue](backend/assets/event/rooms.csv.gz), with photo links checked on 14 October 2026. Put a custom list in `.config/event/rooms.csv` or pass `--rooms PATH`; use the `campus,building,room,kind,seats,tour` columns and an optional `photo` column for an official UQ image URL. Selection applies to that run's outputs and asks for the Forms capacity answer without changing the source TOML. The catalogue gives capacity and previews; availability still comes from booking. Compression removes the readable CSV from the checkout and package, but does not restrict access to UQ’s public directory or remove the CSV from older Git commits

Existing `.env`, `.timey/` and watcher directories are not migrated automatically. Move saved files to the corresponding `.config/` location when adopting the new defaults, or use explicit paths such as `--token` and `--state-dir`

## Courses

```sh
uv run mini scrappy                              # interactive menu
uv run mini scrappy links -o courses_offerings.csv
uv run mini scrappy list courses_offerings.csv --query COMP
uv run mini scrappy details courses_offerings.csv --course COMP3400 -o COMP3400.csv
uv run mini scrappy details courses_offerings.csv -o courses.csv
```

The menu browses/searches courses, refreshes links, and scrapes one course or all courses. Use `links --html search.html` for a saved page. `--jobs 1..8` controls concurrent requests (default 4).

Exports validate course codes and links, remove duplicate URLs, and write one CSV header. The final CSV is replaced only when the whole batch succeeds. Failed or interrupted batches keep completed courses in a SQLite checkpoint in `.config/scrappy/`; rerun the same command to resume, or add `--fresh` to start over. Successful exports clear the checkpoint. To rebuild a damaged dataset, regenerate its links and run `details --fresh`.

Find UNSW CSE teaching resources through their published WebCMS links

```sh
uv run mini scrappy links --university unsw -o out/scrappy/unsw.csv
uv run mini scrappy list out/scrappy/unsw.csv --query COMP
uv run mini scrappy links --university unsw --term 26T3 -o out/scrappy/unsw-26T3.csv
```

`--html` accepts a saved WebCMS index too. Each UNSW record includes its published term and `offering_link`. This reads one index instead of guessing historical CGI URLs; it covers courses linked by that index, not the complete UNSW handbook. UQ detail exports remain specific to UQ catalogue pages. Follow UNSW links to inspect their resources; some require a university login

## Clubs and scheduled events

Search UQ clubs, preserve useful historical descriptions and collect scheduled events from Discord servers your bot can access

```sh
uv run mini clubby refresh
uv run mini clubby list --query gaming
uv run mini clubby import previous-clubs.csv \
  --details previous-details.csv -o out/clubby/historical-clubs.csv
uv run mini clubby list out/clubby/historical-clubs.csv --query consulting
uv run mini clubby events --guild GUILD_ID --guild ANOTHER_GUILD_ID -o out/clubby/events.csv
uv run mini clubby events --json scheduled-events.json -o out/clubby/events.csv
```

The current UQU website embeds Rubric's directory. `refresh` reads its public search API with a pooled connection, 100 records per page and completeness checks, then saves `.config/clubby/clubs.csv` for offline browsing. Names, directory links and available social links come from that source; descriptions and interests are retained when supplied by historical CSVs. `list` searches names, interests and descriptions, with `--offset` and `--limit` for paging. Historical imports combine records by name after normalising case, spacing and apostrophes; renamed clubs remain separate for review

Live Discord exports read `DISCORD_BOT_TOKEN` from the environment. The bot must already have access to the guilds. No gateway connection or additional Discord package is needed. Saved JSON uses the Discord scheduled-event array format. Exports combine servers, remove duplicate event IDs within each server, sort by start time and retain status, description, location and Discord source links. Times use UTC with explicit offsets; recurring series are retained as returned without expanding occurrences. These commands read scheduled events, without posting messages or scraping announcement channels

Club and event exports publish atomically after all sources succeed. Access denial, rate limits, malformed responses and incomplete pagination leave the previous destination intact. Source files are never replaced by an import

The original `courses-scrap`, `unsw-scrap`, `soc-scrap` and `agg-soc` prototypes have been retired and removed
Their supported workflows live in `scrappy`, `clubby` and `planny`, sharing the minis terminal, browser API and atomic exports
Old UQ offering CSVs still work with `scrappy list` and `details`; the experimental Neo4j importer was not migrated
The exposed Discord token from the retired prototype must still be revoked in Discord's developer portal because repository history may retain it

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

Paste a YouTube link, choose a local video or enter search words in the wizard. Video and music search offer YouTube query predictions as you type, with local path completion still available. Predictions are debounced and obsolete requests are cancelled; unavailable suggestions leave ordinary search working. Searches show five results with a thumbnail, title and duration; hovering or highlighting previews a result, selecting fills its canonical link, and **back** lets you search again. Thumbnails request YouTube's largest available image and fall back through smaller sizes when needed; their quality depends on the video and they aren't necessarily 1080p. The left panel resamples at its current size with Lanczos filtering, without changing the menu's position. Search reads metadata and thumbnails before you choose; media downloads begin during preparation

Style, position, colour and font choices show live samples made by the actual overlay renderer. Describe a font with words such as **spook**, **round** or **arcade**, or try an approximate name such as **ariel**. The font shelf offers named matches: “ariel” suggests Arimo, an Arial-style alternative, for you to review rather than silently replacing the font. Unrecognised words open the shelf instead of requesting a nonexistent Google family. Hover over a family or highlight it with the keyboard to see its actual lettering on the timer, with its family and face named below the preview. Google Fonts samples load on demand with a small right-panel hint; moving to another family cancels the previous download, and leaving the prompt closes its background work. Sample errors keep the picker editable. Google Fonts specimen links and local font files still work; bundled fonts need no download. Custom thumbnail files and the opening video frame also have previews. Small or monochrome terminals show text alternatives. Tab completes choices and paths; free-form style briefs and pasted links still work, and blank entries keep the default or skip optional fields

```sh
uv run --extra timey mini timey
```

Requires FFmpeg and ffprobe on `PATH`. YouTube downloads also need [Node.js or Deno](https://github.com/yt-dlp/yt-dlp/wiki/EJS), used by yt-dlp to read YouTube videos

Choose the countdown length, a gap before it starts and a hold after it finishes. `10m`, `25:00`, `1h 30m` and seconds all work. The default gaps are five seconds each. Short backgrounds loop to fill the full timer, with a brief crossfade over the wrap instead of an abrupt cut; longer backgrounds are trimmed. A 20-second clip can fill a one-minute countdown plus both gaps. YouTube downloads request only the segment needed for the timer, or the opening second for a still preview. Audio is kept unless you choose mute

The countdown is the main focus: larger digits, a centred panel and a blank label by default. Use `--label` to add your own text. Only the opening and finishing gaps show a quiet status caption, and changing digits settle through a short dissolve while their positions stay fixed

Each theme has its own scene and material inside the selected lettering. Temple Run adds wind-shaped vines, stone cracks and gold dust to the carved temple frame. Minecraft makes the panel a voxel world: End skies above, Overworld grass around the digits and Nether blocks below, with walking mobs, piling blocks, bobbing items and an occasional dragon. Grass grows along digit edges and removed pieces fall when a number changes. Subway Surfers combines brushed train metal, window glass, paint-filled letters, writing graffiti and a moving train. Neon behaves like a circuit screen, with scanlines, travelling packets and a light-cycle trail. Liquid glass refracts the live video behind the panel, with flowing highlights inside its lettering and along the meniscus. Minimal keeps quiet lettering and a restrained edge light

Terminal samples and exports use the same seeded scene renderer, keeping events repeatable rather than changing randomly on every redraw. Live samples run at eight frames per second, retain only the latest frame and seek directly after long pauses; pause and reduced motion retain a still image. Auto selects a preset from the video title, with minimal as the fallback

On this Mac with Python 3.15, rendering 80 PNG frames per theme from a 3840 × 2160 source with a 1080 × 468 panel measured steady medians of 5.07–13.21 ms and a maximum of 16.44 ms, below the 41.7 ms budget at 24 FPS. The cold Temple Run frame took 107.45 ms including sprite loading. A separate 20-second run retained 0.02 MiB of Python allocations with a 0.26 MiB peak; these figures exclude Pillow's native image buffers

The browser opens a large preview with timing controls on the left and appearance tools below
Search or paste a YouTube link in the centred picker, or drop a local video or image onto the preview
PNG, JPEG and WebP images become still backgrounds; their orientation is preserved and transparent areas use a soft paper colour
Set the countdown with the circular dial or duration presets; two smaller rings inside it control the get-ready time and finishing hold
Drag the timer and resize its width and height with the single corner grip; click or right-click it for floating label and colour tools
Dragging to a preview edge or corner highlights the destination; release there to align the timer without changing its size
The toolbar's placement button opens visual edge, corner and centre choices; hover or focus one to preview its destination
Click the background for floating look and music settings; background search and volume controls expand on hover or keyboard focus
The interior stays free for placement anywhere; Alt/Option bypasses snapping at the edges and Escape cancels the drag
The floating toolbar slips away when idle; video playback controls appear over the footage on hover or keyboard focus
Arrow keys nudge the selected timer, Shift makes larger steps, Home centres it and +/− change its size
Built-in YouTube search uses the same five-result search as the CLI; Timey downloads and caches ten seconds from zero or your chosen timestamp, then plays the local clip
Appearance changes reuse that backdrop, and shared controls keep live previews and exports on the same settings
The player uses central play/pause and ten-second skips, a slim buffered timeline and a volume control, and lets you start the backdrop at the current frame
Local uploads stream into the existing media cache with a 512 MiB per-file limit and a 16-megapixel image limit; a blank preview shows no timer controls
Seeking outside the cached section prepares a new ten-second section rather than downloading the whole video
CLI users can set the same free placement with `--x 0.3 --y 0.8`, measured between the safe edges of the available space
Use `--overlay-width 0.4 --overlay-height 0.2` for independent dimensions as fractions of the video
A separate rendered sample includes the actual timer motion and local footage; full export and reviewed upload remain explicit actions
Sound, custom artwork and export settings live in the side controls; reviewed uploads remain a separate publication action

Before the full export, review the background, countdown, gaps, appearance, sound, quality and save location. Choose **Finish and create timer** to start processing, adjust the timing and layout, or watch a silent preview lasting up to ten seconds. The preview keeps your actual countdown length, shortens the opening gap to at most one second and shows the first few digit changes. With motion disabled, it uses a still preview. Enter on a save filename keeps the name when free or adds `-1`, `-2` and so on when it exists; the final review shows the chosen path. Explicit CLI destinations retain their overwrite protection, with `--force` for intended replacements. `--preview` saves a PNG for direct commands

Temple Run's live countdown composes bundled cracked-gold numeral sprites, with [Skranji Bold](https://fonts.google.com/specimen/Skranji) for its quieter labels. Minecraft labels use [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P) and Subway Surfers uses [Bungee](https://fonts.google.com/specimen/Bungee). These are original game-inspired artwork and open fonts; their OFL licences ship with the fonts and no download is needed for preset typography. Supply your own lettering with `--font`; this also replaces Temple Run's numeral sprites. The Temple Run artwork's [generation prompts](backend/assets/timey/art/temple.md) are included in the source

Choose `custom`, type any game or describe a look instead of a preset. Timey asks a signed-in Codex or Claude Code CLI to design the overlay and saves reusable artwork in `.config/timey/styles/`. `--designer auto` picks the first installed CLI, preferring Codex; use `--designer codex` or `--designer claude` to choose. Codex also sees a small background reference frame. Styles use bounded drawing shapes, typography and a live countdown/progress meter, with no generated Python executed during rendering. Select a saved name in the wizard, pass its JSON file to `--style`, or edit the JSON yourself. `--instructions` creates a custom variation of a preset or refines saved artwork

```sh
# Quick local preview
uv run --extra timey mini timey gameplay.mp4 --length 10m --style minecraft \
  --preview --no-input -o out/timey/preview.png

# Render directly without questions
uv run --extra timey mini timey 'https://youtu.be/VIDEO_ID' --length 25m \
  --video-start 1:20 --style temple-run --start-gap 8s --end-gap 10s --no-upload --no-input \
  -o out/timey/temple.mp4

# Centred frosted glass with smooth looping
uv run --extra timey mini timey gameplay.mp4 --length 1m --style glass \
  --no-upload --no-input -o out/timey/glass.mp4

# Render and prepare an editable YouTube draft and first-frame thumbnail
uv run --extra timey mini timey gameplay.mp4 --length 10m --video-start 30s \
  --style minecraft --metadata --first-frame \
  --metadata-instructions 'A focus timer for study sessions' \
  --no-upload --no-input -o out/timey/study.mp4

# Create any style from a brief using your installed, signed-in coding agent
uv run --extra timey mini timey gameplay.mp4 --length 10m \
  --style custom --instructions 'Hollow Knight: bone mask, soul vessel, indigo stone and silver filigree' \
  --designer codex --preview --no-input -o out/timey/custom.png

# Use a Google font and the soundtrack from another video
uv run --extra timey mini timey gameplay.mp4 --length 10m --style subway-surfers \
  --font 'https://fonts.google.com/specimen/Bungee' \
  --music 'https://youtu.be/MUSIC_VIDEO_ID' --music-volume 0.4 \
  --no-upload --no-input -o out/timey/music.mp4
```

Use `--customise` to reveal the styling, motion, loop and music questions, or pass `--position`, `--size`, `--label`, `--accent '#8FDA53'` and `--font` directly. `--size 2.4` is the default, about 71% larger in width and height than the previous 1.4 baseline; choose 0.5–3 and the panel stays inside safe screen margins on portrait and landscape videos. `--no-motion` disables digit transitions and edge animation. `--loop-blend 0.6` is the default crossfade in seconds, capped at a quarter of very short clips; use 0–2 or `--loop-blend 0` to keep an existing seamless loop's cut. Blended loops start just after their opening overlap, and prepare one reusable cycle instead of building a larger graph for each repeat. Original audio is crossfaded with the video when it is retained

The wizard asks where the background footage should start. `--video-start 1:20` skips the first 80 seconds of a local file or YouTube source; it is separate from `--start-gap`, which controls the opening pause before the countdown. Short sources repeat the footage after that timestamp, including when loop blending is disabled. Timestamps past the source's end are rejected

YouTube video and music clips are cached automatically in `out/.cache/timey/media/`, with a 2 GiB / 32-clip limit and oldest-unused clips evicted first. Matching video, quality and starting timestamp reuse a cached range for equal or shorter requests; a complete remaining clip also supports longer timers through looping. Cache hits skip YouTube lookup and transfer entirely. Completed clips are published atomically, and interrupted downloads never become cache hits. `--no-cache` forces a fresh download. New downloads request only the required section at the selected height; whole-clip HLS/DASH downloads use up to eight concurrent fragments, and YouTube extractor data is reused through yt-dlp's cache. `--height 720` also reduces download and render work

Fonts accept local TTF/OTF/TTC files and HTTPS Google Fonts specimen, stylesheet or desktop-font links. The interactive picker searches the full Google Fonts catalogue, including Open Sans and non-Latin families, alongside mood and typo suggestions. Its catalogue is cached for a week and remains usable offline; without a cached catalogue, the picker explains that it is using the smaller offline shelf. Downloaded fonts are validated and cached in `.config/timey/fonts/`. [Google Fonts links](https://developers.google.com/fonts/docs/getting_started) need no API key

`--music` accepts a YouTube video link or a local audio/video file and uses its audio as the soundtrack. Music replaces the original audio by default; `--mix-audio` keeps both, and `--music-volume` sets music volume from 0 to 2. Short music loops to the exact video length and fades in/out. `--mute` silences the original video while retaining explicitly added music. PNG previews skip music downloads

Loading stages include “Grokking the video”, downloading, crafting the overlay, rendering and finishing. Progress shows actual downloaded bytes or media time, transfer speed, ETA where known, rendered frames, fps, render speed and elapsed time. Metadata lookup and agent design show the current stage without an invented percentage. Plain-text logs remain available when output is redirected

Original quality is the wizard and CLI default: `--height 0` requests the best available YouTube video and preserves a local video's dimensions. The picker also offers 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p and 4320p; an explicit height of at least 240 sets a ceiling for downloads, exports and terminal previews. Smaller footage isn't upscaled. Terminal detail is bounded by its available character cells rather than the export's resolution. `--height 720 --fps 30` reduces rendering work. The timer is limited to 24 hours, with gaps up to an hour each. FFmpeg handles the background video, sound and glass refraction; Python streams a panel-sized animated overlay at the chosen frame rate, preparing digit masks once a second. Disabled motion retains the cheaper one-panel-per-second path. Ctrl+C stops rendering or style design and removes scratch files. Existing outputs are preserved unless you pass `--force`

The wizard asks whether to upload to YouTube. If you choose yes, it offers generated title, description and tags, then lets you edit them and answer visibility, audience and altered-content questions. Generation uses your signed-in Codex or Claude CLI, selected with `--designer`; without either CLI, it builds a factual draft from the timer settings. `--metadata-instructions` adds your intended purpose or audience. Drafts use specific duration and theme wording, natural search terms, an understandable opening summary and accurate countdown timings, following [YouTube's description guidance](https://support.google.com/youtube/answer/12948449?hl=en). This helps describe the video for people and search systems; it does not guarantee ranking, AI citations or recommendations

Choose `first-frame`, `custom` or `youtube` for the thumbnail. `first-frame` extracts the actual opening frame of the finished MP4, including the timer overlay and opening status, into a `.thumbnail.jpg` beside it. It is saved before upload confirmation, so you can inspect it even if you decline the upload. `--first-frame` also works with `--upload-only`; `--no-first-frame` leaves the thumbnail to YouTube. Custom PNG/JPEG files support the current [50 MB API limit](https://developers.google.com/youtube/v3/docs/thumbnails/set); your channel needs custom-thumbnail access

Advanced questions cover category, language, licence, embedding, subscriber notifications and a scheduled publication time with a timezone. Upload details and timer context are saved beside the MP4 as an editable `.youtube.json` draft, and you review title, description, tags, thumbnail and upload settings before confirming. `--metadata --first-frame --no-upload` prepares these files without uploading anything. Existing audience, visibility and advanced settings are retained when regenerating metadata in an existing draft

For the first upload, enable YouTube Data API v3 in your Google Cloud project, configure its OAuth consent screen and create an OAuth client of type **Desktop app**. Download its JSON to `.config/timey/client_secret.json`, or pass `--client-secrets /path/to/client.json`. Add your account as a test user if the consent screen is in testing mode. [Google's OAuth setup](https://developers.google.com/youtube/v3/guides/auth/installed-apps) explains the steps. The browser is used for Google sign-in; subsequent uploads reuse an owner-only token in `.config/timey/youtube.json`

```sh
# Upload a saved timer later, using its details draft
uv run --extra timey mini timey out/timey/temple.mp4 --upload-only
```

Use `--details /path/to/details.json` for another draft. Unattended uploads require explicit `--yes`; rendering and uploading together also require `--upload --details`. A completed upload leaves an `.uploaded.json` receipt containing its YouTube link and prevents another upload of that output path. If an upload is interrupted, check YouTube Studio before retrying. A failed thumbnail upload preserves the video link in the receipt

YouTube Studio still handles copyright checks, age restriction, monetisation, cards and end screens. Google restricts uploads from unverified API projects to private visibility, even when another visibility was requested, until the project passes its audit. [YouTube upload API limits](https://developers.google.com/youtube/v3/docs/videos/insert)

## Development

Mini-specific domain logic lives in `backend/src/minis/<mini>/`. Each `backend/src/cli/<mini>.py` defines and registers that mini's commands, options and terminal workflows; `backend/src/cli/core.py` registers management commands, and `backend/src/cli/completion.py` handles shell completion. CLI implementations live directly in `backend/src/cli/`

`backend/src/core/` owns mini management, shared helpers, the Typer/Rich/prompt_toolkit stack, cache publication and eviction, and the `.config/` runtime location. Mailbox storage, transports and background processing live in `backend/src/worker/`. Mini-owned credentials, and state use `.config/<mini>/`; disposable caches use `out/.cache/`; bundled assets use `backend/assets/`

Reusable task skills live in `skills/<mini>/SKILL.md` and are linked from `AGENTS.md`
Python development scripts live in `tools/scripts/`
`mini add` creates a shared mini core, CLI registration, FastAPI router and skill scaffold; restart the browser backend to discover it

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

Tests cover every mini, shared infrastructure and the worker
Feature groups live under `backend/tests/`, shared fixtures under `tests/support/` and test doubles in `tests/fakes.py`
Up to four isolated workers share pending tests; use `-n 0` for single-process debugging
Browser checks use local pages with external requests blocked, and video checks render short generated clips
Optional checks are reported as skipped when their dependencies are missing

`dev check` also runs strict basedpyright over source, tools, tests and the artwork generator in an isolated environment, keeping the editable checkout available for interactive use

Coverage measures lines and branches, including greenlets, worker processes and CLI subprocesses. CI runs all extras, Chromium and FFmpeg on Linux, Windows and macOS, with an 85% minimum on Linux. Test results and HTML coverage are kept for seven days, including failed runs

Lint, formatting and compilation run once before the test matrix. Packaging rebuilds the wheel from its source archive and checks installed commands and assets away from the checkout. Task skills remain in the repository root. Release checks run the complete suite before publishing

Security CI audits the locked dependencies and gates medium/high Bandit findings. Typer's completion-language option and the worker's validated SQL identifiers have specific false-positive annotations; subprocess calls pass argument lists without a shell

Python 3.15's native lazy imports keep command help from loading browser, document or media dependencies. Timey's preset maps are read-only to prevent accidental changes. On macOS with Python 3.15, `tests/benchmarks/cli.py` measured Timey help at a median 387 ms before lazy imports and 110 ms after, across five fresh processes for each; the help budget is 200 ms
