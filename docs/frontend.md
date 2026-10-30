# Minis frontend

Use Node 24 or newer

React, TypeScript and Vite live in `frontend/`, with all npm configuration and dependencies
Python and FastAPI live in `backend/`

```sh
npm --prefix frontend ci
npm --prefix frontend exec playwright install chromium
npm --prefix frontend run dev
npm --prefix frontend run check
```

Development requests proxy to FastAPI at `http://127.0.0.1:8765`
Start it from the repository root with `uv run --directory backend --all-extras mini browser`
For a single local address, run `npm run build` in `frontend/` and open the backend's address
The Python package does not bundle the React build; keep `out/artifacts/frontend/` beside `backend/` when serving this checkout
Use `mini browser --frontend PATH` when the compiled frontend is stored separately
See [Hosting Minis](hosting.md) for the checked Oracle deployment command and current hosting blockers

Source stays one folder deep: `shared/` owns common controls and services, `timey/` owns the video desk, `study/` owns course and calendar features, and `wildlife/` owns the animals and habitats
The app entry and common stylesheet stay at `frontend/src/`; `main.tsx` opens the public app shell while checking identity independently
The home catalogue and Timey settings load without a private plan or account worker
Only Eventy and its Forms/mailbox connections require UQ access
The home shelf starts from the bundled public catalogue and revalidates independently, so a slow catalogue request never leaves the cards empty
Other minis use a private browser workspace prepared independently of the page render
Study plans load when opening a study mini; Timey renders its controls immediately and merges server settings without replacing edits
Mini modules warm after the first page paint without mounting editors or starting backend workers
Navigation uses transitions and one Suspense boundary outside the keyed habitat, preventing a new loading boundary from imposing its fallback delay on each mini
Links use `?m=timey`; existing `?mini=timey` bookmarks remain supported
Tool settings live in `tools/config/*.toml`; `npm run configure` writes native settings beneath `out/tools/`
Vite 8 uses its Rolldown and Oxc pipeline, SWC for React transforms, and Oxfmt and Oxlint for formatting and lint
Builds go to `out/artifacts/frontend/`, test output to `out/test-results/` and caches to `out/.cache/`
Tests live in `frontend/tests/`
Artwork, external SVG icons, masks, fonts and audio live in `frontend/assets/`, grouped by purpose
SVG markup stays out of application source and the document; diagrams retain native HTML controls with canvas connections
Assets remain separate build files so browsers can cache them rather than repeat them inside JavaScript

Zustand owns the editable study plan, verified session, Timey draft and shared notices
TanStack Query owns shared catalogue, weather and private plan fetches
Plan queries stay fresh for 30 seconds; bounded tab snapshots paint before revalidation
Private queries and volatile plans are cleared when the workspace changes
Plan edits and imports share a save queue and use the latest accepted server revision
Temporary pointer gestures, search text and open menus stay local to their components

Searches accept everyday phrasing, common topic alternatives and explicit exclusions such as `gaming clubs without alcohol`
Server and local browser searches share the vocabulary in `backend/assets/search.toml`
Course research retains its existing level, semester and rating interpretation
Room searches also understand capacities such as `a room at St Lucia for 50 people`
These are local domain parsers, rather than an arbitrary conversational model

Event and assessment briefs fill editable fields without submitting or saving them
The English date parser loads only when Fill details is used, accepts Australian day/month ordering and leaves incomplete deadlines for review
Follow-up changes keep unrelated values, and late imports cannot fill a dismissed or changed brief
Selecting a course profile opens its published assessment proposals automatically
Planny offers the same read for selected courses without assessments, while other offering years stay behind More years
The newest year with a published profile takes priority over unpublished future listings
Imports still preserve saved marks and require review before adding assessments

Every JSON API request supplies a Zod response schema to `shared/api.ts`
Shared form and sign-in contracts live in `shared/schema.ts`; study and media contracts stay in their owning `model.ts` files
Types are inferred from these schemas rather than maintained as parallel interfaces
Use `zod/mini` for browser schemas to keep the validation bundle small
JSON uploads, portal messages and saved display preferences use the same runtime checks
Failed response validation reports a recoverable error and leaves the last accepted plan intact
Plan schemas preserve additional saved fields so editing through an older client does not silently discard them
On this Mac, 50 warm schema parses of a plan with 1,000 assessments and 500 announcements measured a 1.85 ms median and 2.66 ms p95, within a 16 ms validation budget
The production entry bundle increased from 111.04 to 122.19 KB gzipped with these contracts; Zod's full API produced a 139.06 KB bundle in the same build comparison

Application source and tests use strict TypeScript with no JavaScript fallback or suppressed type errors
`npm run check` runs Rust-based Oxfmt and Oxlint, TypeScript, Vitest, Playwright interactions and a production build through Vite's Rust-based Rolldown bundler
Vitest runs pure contract and lifecycle checks in Node; React Testing Library and user-event exercise rendered components in JSDOM
Use accessible queries and user interactions for component behaviour, with complete synthetic fixtures from `tests/fixtures.ts`
Playwright owns native media, popovers, layout, pointer resizing and keyboard workflows; its video-switch regression decodes a small local WebM fixture
Run a focused component test with `npm --prefix frontend test -- tests/timey.test.tsx`
Browser tests start their own Vite server on port 5174 and mock university/media responses; they never submit real credentials
Set `MINIS_BROWSER` to an existing compatible Chromium executable when using a managed browser installation
Authentication tests cover relay input, errors, cancellation, retry and verified completion; a human still needs to check real UQ MFA
The themed UQ form accepts typing while its private browser connects, sends credentials only on submission and clears its password afterwards
The username/password step sends semantic control metadata without screenshots; original UQ or Duo pages remain available for interactive MFA
Cancelled playback promises during a media-cache swap are expected interruptions, while unsupported media remains a visible error
Blocked YouTube downloads offer the same file picker used by the background search, retaining the timer's edits and any accepted backdrop
YouTube search and remote media require Connect Google, which opens the original provider page in a short-lived, private server browser
Its cookies are stored owner-only in that workspace and are separate from UQ and upload OAuth
Local editing and uploads remain available without Google
Reconnect and disconnect remain available; saving a connection does not prove that YouTube will allow a download
Expired Eventy access reloads into the in-page sign-in flow without changing the guest workspace
Timey drafts and preview caches use the workspace identity, so checking UQ access does not switch or discard guest work
Old UQ-scoped drafts and server files remain in their original workspace; they are never copied into an anonymous workspace

Timey accepts files through the picker, drag-and-drop and native Paste, including Command–V and Control–V
Backgrounds include still raster images, HEIC/HEIF and animated GIF/APNG/WebP, which the backend normalises for the player
Music uses FFmpeg's audio decoders; uploaded fonts use FreeType validation for TTF, OTF, TTC, WOFF and WOFF2
Direct file links are fetched by the browser without credentials and must allow cross-origin access; blocked links offer a local-file recovery
Google Fonts specimen links continue through the shared trusted font loader

Themed hints use one manual popover, with pointer and keyboard triggers, Escape dismissal and listener cleanup
Media preparation keeps the accepted backdrop, offers cancellation and shows interactive mist over the wallpaper or a small real thumbnail
Visible timer and playback skeletons sit in a pointer-cleared haze over the wallpaper
Soft overlapping washes add detail through several resolution levels, starting at eight pixels and reaching native playback in at most 1.5 seconds without rectangular reveal tiles
Available thumbnails also gain detail while the full media prepares; the final reveal never restarts below their displayed resolution
The two temporary display surfaces are capped at 960 × 540, with one sample bounded to the same dimensions; all release on completion, cancellation, source changes or unmount
Scenery and mist share one external, uneven feather mask that stays fixed on hover and selection; controls and keyboard focus remain outside it
Reduced motion, background tabs and reduced-data preferences skip the refinement and drifting grains
Preview images use an optional browser cache capped at 24 entries, 24 MiB total and one day, with at most 2 MiB per entry
Cache reads have a 120 ms ceiling and writes stay off the display path; blocked storage, quota failures and stale entries fall back to rendering
Media files also use private HTTP caching with revalidation, so browser storage never determines whether a file is allowed to open

Timey keeps editing, a rendered sample and the finished video in the same central player
Watch preview leads to Edit video and Make video; a finished render leads to Edit video and Save video
Appearance controls stay in editing, while quality and frame rate remain available in every stage
Changing quality rebuilds a watched movie and disables saving its older version until the replacement is ready
The edit backdrop uses the chosen quality, while overlay drawing stays within a 960 × 540 working budget
Tab storage preserves validated settings, custom-design questions and accepted results through sign-in or reload; blocked storage leaves the in-memory draft usable
Saved media links remain tied to the running backend workspace
Custom looks use a name, description and focused follow-up answers; later changes reuse the saved artwork
Media predictions start after 100 ms of typing and font searches after 180 ms, cancelling superseded requests
The suggestion cache holds at most 60 queries for five minutes and never prevents a full search
Saving requires verified UQ access and offers device download or a separate reviewed YouTube upload
Keysi CDN needs its service integration before that destination becomes available
No browser test publishes a real video or signs into a real account
