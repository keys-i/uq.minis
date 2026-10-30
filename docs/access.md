# UQ access and inclusive reading

Minis currently runs on loopback and keeps one private workspace on this computer
The browser is not a public multi-user service
Do not put it behind a public proxy until workspace isolation, HTTPS cookies, persistent sessions, trusted deployment origins and private calendar tokens are implemented

## University access

Eventy and shared catalogue updates require verified UQ access on both GET and POST
Choose **Check UQ access** in sidebar account settings or the workflow gate
Minis displays UQ's own portal inside the page, using a private headless browser on this computer
Complete UQ's account selection and MFA in that window if asked
No separate Chrome, Safari or Edge window opens
No registered application, tenant ID or application secret is needed

The local check reads the protected `auth.uq.edu.au` authentication-status page after UQ signs the person in
It accepts a UQ account address from that page's attributes with UQ's successful-session confirmation or the protected page's logout link
The public login page, an email typed into minis and a callback URL cannot establish access
The portal window closes afterwards; passwords, UQ cookies and service tokens are not saved by this check
A random HttpOnly, SameSite=Lax minis session lasts eight hours and expires on server restart
Only one portal check runs at a time, with a five-minute limit and cancellation when the in-site window closes
The local WebSocket requires a one-use HttpOnly cookie reservation and a permitted loopback origin
The backend browser can reach only HTTPS authentication pages at `auth.uq.edu.au` and Duo subdomains
Native labelled controls overlay the original page image for keyboard, touch and assistive-technology input
Sign-in input passes through this local backend into UQ's page, stays in memory and is never logged or saved by minis
Frames update at most twice a second, unchanged frames are not sent and pending input is bounded
UQ's framing policy is preserved; minis neither embeds its HTML nor removes its security headers

This access check runs on the local computer alongside minis
It proves portal access, not club-officer status or permission for a particular booking
Forms and Outlook keep their separate existing connections for submissions and mailbox actions
Authentication does not authorise a submission, email or upload
The CLI's local workflows are unchanged
University and catalogue requests retain their shared ceiling of two concurrent requests and thirty starts per minute

## Translation

The initial reading language follows the browser's preferred supported language, with English always available near the top
The menu keeps browser preferences first, includes native and English language names, and offers 138 provider-supported choices across Latin, Indic, Arabic, Cyrillic, African and East Asian scripts
The bundled language list comes from [Microsoft Translator’s public languages endpoint](https://api.cognitive.microsofttranslator.com/languages?api-version=3.0&scope=translation), retrieved on 20 October 2026
The reading controls try the on-device browser Translator API first where available
Its language models may need a browser-managed download after the person selects or prepares a language
Unsupported browsers and language pairs use the configured service, or preserve the original text when no service is connected
Known source languages are passed to the fallback so short labels are not left to automatic detection
Automatic language detection for original reviews also requires the browser LanguageDetector API when using on-device translation

For a browser-independent provider, the adapter uses Microsoft Azure Translator's documented text API
Choose the **F0 free tier** if available in your account and region; no Azure account, resource, billing plan or subscription is created by minis
Configure the resource's key and region in the backend process environment

```text
MINIS_TRANSLATE_KEY=<Translator resource key>
MINIS_TRANSLATE_REGION=<resource region>
```

The server translates up to 4,000 characters per request and 60,000 uncached characters per process per day, with at most two active translations
Translation has its own limit and does not use the university request quota
Provider rate limits and temporary outages return `429` or `503` with `Retry-After`; both the browser and backend wait before sending further uncached work
Retries are deliberate rather than automatic, so a failure cannot queue repeated billable requests
Use **Retry translation** in the reading-language menu after the reported wait or connection issue is resolved
Invalid or empty responses are never cached, and a failed alternative keeps the last successful browser translation visible
The browser and server each keep at most 128 completed translated results in memory; the browser releases evicted native engines and destroys remaining engines when its reading context closes
These are local safeguards, not a replacement for the provider's billing limits
The browser requests translations only for visible marked public research text and interface labels
Private marks, completed-course lists, mailbox content and assessment notes are not passed to this adapter by the UI
Original reviews are sent to Microsoft only when that provider is configured and translation is enabled through the selected reading language or original-language detection

Translations are machine-generated, not human-reviewed or guaranteed accurate
Original wording remains available for course descriptions and reviews
**Try another translation** explicitly requests the configured service when a browser translation is inadequate
Minis cannot automatically judge the semantic accuracy of either result
Long passages beyond the current 4,000-character component limit remain in their original language
The complete translated Unicode run fades into place without random glyphs or per-letter spans, preserving Devanagari shaping, Arabic joining, selection and copy
Reduced motion removes this transition
This release translates marked course research and club text, rather than claiming complete translation of every legacy mini form
The configured status confirms that credentials are present, not that a live provider call has succeeded
Check an authorised connection with a short public phrase from the CLI

```sh
uv run --directory backend mini planny translate "Course information" --source en --to hi
```

## Course research sources

`mini scrappy catalogue` crawls the official UQ programs and courses search, following validated pagination and publishing only a complete nonempty index
The crawl is limited to once a day, with details fetched on demand rather than requesting thousands of course pages on every visit
`mini scrappy research --refresh` saves independent course/professor reviews; it preserves an existing official index and checked requirements
The older `mini planny research` command remains compatible
It reads only the site's published anonymous interface and never requests profiles, private messages or account credentials
Clubby uses [UQU's current directory](https://uqu.com.au/clubs-and-societies/) as its club authority
UQU embeds the public Rubric university-12 catalogue, so minis reads that same complete feed rather than appending clubs from a second site's historical list
`mini clubby refresh` replaces membership with the current union list while preserving already checked UQU profile details
`mini clubby enrich` completes descriptions, artwork, categories and social links from those clubs' own public profiles, refreshing profiles at most weekly
Descriptions retain the club's words, with encoded HTML removed before display
Clubby checks the directory daily and retains the previous catalogue after a failed refresh
The October 2026 refresh contained 221 current clubs
The right-hand noticeboard reads a shared hourly public event snapshot; authorised social posts already in the student's plan appear alongside it
Following a club also brings its newly published events into calendar subscriptions, without rewriting the saved plan on calendar reads
A complete public snapshot replaces disappeared public events; saved events from independent feeds remain separate

Social links do not grant account access
Facebook, Instagram, LinkedIn and Discord reads still require the owner's or server administrator's authorisation described in [sources.md](sources.md)
Minis does not claim a description was checked against a restricted social account when it was not
No students need to supply directory records or social account credentials to discover clubs

### The minis rating

`mini planny research --expand` collects public StudentVIP UQ star observations at most weekly
It retains course aggregates and temporary text fingerprints for deduplication, without republishing their written review corpus
The first expanded import added 1,175 observations across 490 courses
Direct course/professor review tables remain additional research inputs; the official UQ crawl owns the catalogue once refreshed
No integration posts to Talkwall or creates a forum
Current UQ course profiles remain the authority for requirements and offerings

The minis score is an explicit conservative heuristic, not a validated measure of teaching quality or an official university rating
It combines only available components on their published five-point scales

| Evidence | Base weight |
| --- | ---: |
| Latest available official SECaT overall question | 1.0 |
| Direct student Usefulness/Fun experience | 0.7 |
| Direct StudentVIP star observations | 0.65 |
| An existing mixed aggregate, only when neither direct source is available | 0.15 |

Each evidence weight is multiplied by the square root of its response count, capped at 100 responses per component
The weighted mean includes a neutral prior of 3/5 with weight 2, so very small samples stay cautious
Difficulty is displayed independently and never makes an otherwise good course score worse
A missing component contributes nothing; a completely unrated course stays unrated
The mixed aggregate overlaps direct StudentVIP and student reviews, so it is excluded whenever either is available
Counts are observations, not a verified count of distinct people across sites
Confidence labels describe the available weighted evidence only: early below 2, building from 2, and strong from 5
These weights do not establish accuracy or correct for all age, selection, popularity or response biases
Source identities, counts and component values remain in the local API and snapshot for audit, without source chatter on discovery cards
Usefulness, Fun and Difficulty keep their own genuine response counts, including zero-valued scores
Professor dimensions retain the meanings of teaching quality, difficulty and rapport; no professor feedback is invented when a source has none

[UQ's quantitative SECaT chart](https://www.pbi.uq.edu.au/clientservices/SECaT/embedChart.aspx) publishes course/semester question distributions
Maintainers can import a saved chart with `mini planny secat saved-chart.html`; Scrappy prepares ordinary course data without exposing maintenance controls to students
Imports preserve each question, period and response count, suppress distributions with fewer than five responses and reject incomplete distributions
The reversed answer codes are converted so 5 means strongly agree
Staff-only comments and individual teaching reports are not fetched
The first verified import was ABTS1000, Semester 1 2026; other courses do not pretend to have official results

### Study periods and requirements

Browser and CLI default to **Now / next**, using Semester 2 from June through November and Semester 1 otherwise, with the following year's Semester 1 selected in December
This is a month-based teaching-window shortcut, not a live UQ academic-calendar connection
Choose Semester 1, Semester 2, Summer or Any time to override it; an explicit semester in a natural-language query also takes precedence
Past catalogue years are labelled as last listed, without promising that a new offering exists
Requirements checked on a course's official page are remembered for its discovery card and retained during catalogue refresh
Their check timestamp remains in the snapshot; the UI always treats them as a guide rather than enrolment permission

Completed courses and skills are entered by the student and stored in the existing private plan
The CLI offers the same starting point and checks

```sh
uv run --directory backend mini planny knowledge --completed "CSSE1001, MATH1051" --skills "Python and calculus"
uv run --directory backend mini planny ready CSSE2002
uv run --directory backend mini planny research "easy first-year coding"
uv run --directory backend mini planny translate "Public course information" --to hi
```

Simple AND/OR prerequisite expressions can be checked against those completed codes
Permission, equivalent experience, concurrent enrolment and other prose conditions stay manual
Skills identify topic overlap and never waive a formal requirement
The clickable graph shows the selected course's published prerequisite references; alternative branches retain the actual source wording
Natural-language search is a local, transparent topic and filter parser, not a remote LLM or an academic eligibility decision

App light/dark preferences affect interface surfaces only
Wildlife clocks and artwork retain their own local-time habitat phase in every theme

## Local performance check

The backend search-work budget is 100 ms with no upstream fetch per keystroke
On 20 October 2026, `time.perf_counter` measured 40 warm searches per query against the expanded 4,801-course snapshot
The default Semester 2 browse measured a median of 2.36 ms and p95 of 5.12 ms, versus 16.40 ms and 24.49 ms immediately before deferring off-page scoring and prerequisite checks
The same revised run measured highest-rated searches at 5.78 ms median / 10.34 ms p95, and “fun first year coding” at 17.99 ms median / 24.16 ms p95
A cold snapshot read took 47.16 ms in this repeat
An earlier run on the same checkout measured default browsing at 1.18 ms median, illustrating the variation from other work on this computer
These are local Python measurements rather than browser or hosted-network timings
Only the 30 displayed rows receive prerequisite checks, while scores across all matches are calculated when ranking needs them
Unfiltered browsing also avoids scanning every description for an empty query
The research view remains separately loaded; current production bundle sizes are recorded by the frontend verification log
The existing illustration, font and audio budgets remain unchanged


## Course selection and prerequisite trees

Selecting a course saves the enrolment choice immediately, without requiring a live catalogue response or inventing a profile URL
Attach a published profile separately and review assessments before importing them
Saved official requirements remain available during an upstream outage and retain their unverified availability state
Browsing defaults to the current/upcoming semester without a semester switch; an exact code can still find a course listed in another semester

The prerequisite tree follows course-code references, shares repeated nodes and protects against cycles
Each expansion has limits of 80 nodes, eight levels and 16 live detail reads; UQ access denial stops further live reads
Unloaded branches stay visibly unresolved and can be followed by opening their course
Colours distinguish branches, while hover and keyboard focus trace dependencies without replacing AND/OR wording
Skill suggestions match named topics in the published description, assumed background or prerequisite text; they do not certify readiness or replace mandatory prerequisites

## Timer previews

Live controls render a transparent 960 × 540 overlay through the same validated Timer and artwork functions as final export
Requests are debounced and cancelled when superseded; obsolete object URLs are revoked and only one overlay renders at a time
Timer appearance requests do not download or encode footage
Direct placement and resizing update the existing panel in the browser without a server request; the shared renderer uses the same normalised safe-area coordinates for export
Pointer, touch and keyboard manipulation share bounded placement; selecting or right-clicking the timer reveals its floating toolbar
The toolbar closes after inactivity unless someone is using its controls; playback controls appear on video hover or keyboard focus and remain available on touchscreens
An empty preview centres video search and local upload on a themed surface, with no timer overlay or editing tools
Pasted YouTube links preserve their timestamps; files and YouTube links can also be dropped onto the preview
Local uploads stream through a route-specific 512 MiB limit and share the media cache budget
Video uploads are validated by ffprobe; PNG, JPEG and WebP images are decoded within a 16-megapixel limit, oriented and flattened to a safe PNG
Image previews are cached at up to 960 × 540; the shared renderer retains the imported resolution for CLI and browser exports
Uploads use opaque workspace registrations for preview and export; failed uploads remove their temporary files
The timing dial supports pointer and keyboard input; one corner grip changes width and height independently while retaining the opposite corner
The countdown and both gaps use the same integrated ring control, with smaller rings inside the main dial and one-second keyboard steps for the gaps
Overlay width and height are independent fractions of the video; corner resizing and keyboard scaling preserve the same shape in previews, CLI samples and exports
Resize affordances use one corner grip without a bounding rectangle; keyboard focus has its own small marker
Dragging to an edge or corner highlights the destination without resizing the timer; releasing in the interior preserves free positioning
The floating toolbar also opens a native placement popover with edge, corner and centre icons; hover or keyboard focus previews each destination, selecting applies it and Escape or an outside click dismisses it
The timer toolbar opens matching rounded speech bubbles for look, music, colour and placement; fields retain their values when the menus close
Custom artwork is a theme button with its own context bubble, and switching themes preserves the custom draft
The background-search label and volume slider expand on hover or keyboard focus, with no animation under reduced motion
Alt/Option bypasses edge snapping; arrow keys nudge, Home centres and Escape or cancelled pointer capture discards unfinished movement
YouTube search uses the CLI’s bounded five-result implementation
A video first opens from a cached ten-second section while the complete browser-compatible H.264/AAC MP4 prepares in the background
An existing complete cache opens directly, and upgrading from a section preserves playback position and pause state
Raw sections and playable previews share the existing 2 GiB / 32-entry media-cache budgets, with validated identities, atomic publication and last-use eviction
Local sources include their modification time and size in the preview identity
Changing appearance reuses the same cached backdrop; changing the source or timestamp requests the matching section
The browser cancels obsolete requests and releases old players, while the backend bounds preview preparation to one at a time
Registered local URLs support byte-range seeking; third-party frames are disabled by the browser content policy
The player timeline uses actual source duration when available and highlights the buffered section; seeking outside it prepares the new section
Local video and animated overlay samples use the renderer’s explicit ten-second sample action
Appearance, sound, custom artwork and export controls share one form state; saved artwork and fonts use the same configuration for live overlays and final exports
Generated artwork is built during an explicit motion sample or final render, and uploads retain their separate review controls
