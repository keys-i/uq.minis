# Hosting Minis

The production target is currently unverified after the previous Oracle account ended
The intended public routes are [uni.keysi.dev/mini/](https://uni.keysi.dev/mini/) and [uni.keysi.dev/soc/](https://uni.keysi.dev/soc/)
Its home page and mini catalogue open before sign-in, without starting an account worker
Ordinary minis use a private browser workspace without UQ sign-in
Only Eventy requires a verified UQ account, with separate files and independently saved Forms or mailbox access
The existing university homepage remains on GitHub Pages and matched its original SHA-256 after the switch
Cast remains connected to its existing `questrelay` Worker at [cast.keysi.dev](https://cast.keysi.dev)

## Updating the hosted app

Run from this checkout

```sh
MINIS_SSH_KEY=~/.ssh/minis uv run --directory backend dev deploy user@host --dry-run
MINIS_SSH_KEY=~/.ssh/minis uv run --directory backend dev deploy user@host
```

The deployment checks the backend and frontend, builds React beneath `/mini/`, then uploads only the wheel, locked dependencies, built assets and service definitions
It uses `MINIS_SSH_KEY` or `~/.ssh/minis`, requires the verified host key and keeps local drafts, credentials and `.config/` files off the server
The server switches releases atomically and restores the previous code and service definitions if readiness fails
A deployment ends UQ sign-in sessions, so Eventy visitors need to verify UQ access again
The guest workspace cookie survives gateway restarts, while its saved files remain outside releases
Saved workspace files remain outside releases, and each account's Timey draft remains in that browser tab's storage
No Git commit or push is performed by this command

Use the installed compatible Chromium through `MINIS_BROWSER` if the frontend test runner's default browser is unavailable
The existing Wrangler CLI and [deployment configuration](../deploy/wrangler.jsonc) update the Cloudflare Worker when path routing changes
Ordinary frontend and backend changes only need the deployment command above

## Account and filesystem boundaries

`minis.service` accepts only the systemd-owned `/run/minis-edge/uq.sock` and owns the UQ portal access check
Its opaque eight-hour hosted cookie is Secure, HttpOnly and host-only through the `__Host-` prefix
Only a response from UQ's protected session page establishes identity
The in-site sign-in browser closes after completion, cancellation or timeout without retaining its UQ cookies

Every workspace starts a separate `minis@<account-id>.service` under a systemd dynamic Unix user
Its private working directory contains that account's relative `.config/` paths
systemd manages those directories beneath `/var/lib/private/uq-minis/`, with protected links beneath `/var/lib/uq-minis/`
The gateway's private account records live in `/var/lib/minis/workspaces/`
Per-workspace delegate secrets arrive through systemd credentials, and only the gateway can connect to workspace Unix sockets
The narrow polkit rule permits validated workspace socket starts and workspace stops, with no arbitrary service management

An anonymous `/api/session` response issues a random 256-bit Secure, HttpOnly, SameSite=Lax, host-only workspace cookie
Only its SHA-256 digest appears in the public workspace ID; the ID itself cannot authenticate a request
API requests bind the cookie to the workspace owning the rendered page
Eventy separately checks the verified UQ identity, including owned job results and downloads
Ordinary downloads use the browser workspace, while calendar subscriptions use separate persistent read-only capability links
Browser drafts and cached timer previews use workspace-specific identities and retain guest work across Eventy sign-in
Existing UQ files and old draft keys remain intact and are never exposed through a new guest cookie
Signing out reloads the page, and account changes notify other open tabs to discard volatile state
Local desktop mode retains its existing paths and draft key

## Network and capacity

The next host must run Linux with systemd and keep application ports closed to inbound Internet traffic
SSH should be key-only over the chosen private administration network with root and password login disabled

The locally managed Cloudflare Tunnel connects outbound from `cloudflared-minis.service`
Its root-only credential JSON lives at `/etc/cloudflared/minis.json` and reaches the dynamic service through `LoadCredential`
`/etc/cloudflared/minis.env` supplies only `MINIS_TUNNEL_ID=<uuid>`
The checked-in ingress is authoritative and sends the connector to `/run/minis-edge/caddy.sock`
Caddy alone can reach `/run/soc-minis/app.sock`, while cloudflared cannot traverse the separate `soc-minis` socket group
`minis-origin.keysi.dev` points to the tunnel, and the proxied university hostname retains its `keys-i.github.io` CNAME
The Worker routes only `/mini`, `/mini/*`, `/api/*`, `/download/*` and `/calendar.ics` to Minis
Its ordinary homepage and notes continue to use Pages

At most two workspace processes remain active and stay warm between visits
A third workspace evicts the least recently used idle process without deleting its saved files
Measured basic workers retained about 60–62 MB each, with warm plan requests at 51–52 ms versus 3.17–3.22 seconds for a cold worker through the public gateway
New guest registrations stop at 256 workspace records and preserve existing files when capacity is reached
Busy workspaces are retained, and excess work receives a retryable capacity error
Long requests return owned job links and are polled, avoiding a single long Cloudflare HTTP request
Completed job results are bounded and evicted when room is needed for new work
Each private workspace owns its upstream rate limit, rather than charging every account against a second gateway limit
Reading local mini setup fields does not consume upstream capacity
Uploads use ordered 8 MiB parts, preserving the 512 MiB upload limit through Cloudflare's free proxy
Workspace processes have memory, task and 512 MiB individual-file limits
Mutations stop when free disk space falls below 6 GiB, while read requests remain available for backups
The earlier 1 GB VM measurements remain capacity evidence only and do not validate an unchosen replacement host

## Verification and recovery

The current local implementation passed backend lint, formatting, compilation, strict typing and 1,776 tests at 86% coverage
Frontend formatting, typing, lint, all 156 unit tests and the production build passed
Twenty-six of 27 browser workflows passed before the final surface-invariant correction, then the corrected Timey regression passed independently
A complete post-fix browser rerun remains unverified because this workspace cannot open the local test port
Wheel and source-archive metadata checks passed, including the bundled species catalogue and native server entry
The final deployment status must be verified separately from these local checks
Live guest checks confirmed separate plans, rejected cross-workspace headers, Eventy-only UQ gates and retained plan data after restarting a private worker
An anonymous browser cookie also retained the same workspace identity across a real gateway replacement
Native Oracle checks with disposable test identities confirmed separate plans, rejected cross-workspace delegate credentials and downloads, and recovery of saved plans and media after stopping a workspace
Mount-namespace checks confirmed the tenant could read its own plan while peer files and gateway credentials were inaccessible
The polkit check permitted the intended socket start and rejected SSH restarts, direct service starts and socket restarts
The public HTTPS WebSocket returned the real UQ credential form as 741 bytes of control metadata without a screenshot, then closed without entering credentials
A real three-second 960 × 540 timer rendered in 15.93 seconds, with an observed workspace peak of 270,225,408 bytes
This short sample does not establish performance for long or high-resolution renders

The host prerequisites are systemd, polkit, uv, FFmpeg, curl, `build-essential` and Chromium's OS libraries
Shared Python and Chromium runtimes live beneath `/opt/minis/`, outside private user storage
Deployment compiles Python bytecode before activation, including dependencies
The login gateway starts reclaiming memory at 448 MiB and retains its existing 512 MiB hard limit
The previous 256 MiB soft threshold caused 938 reclaim events and roughly three seconds of accumulated memory stalls during a real login-form check
An anonymous live form probe at 384 MiB took 20.04 seconds, with 1,222 new reclaim events and 2.76 seconds of full memory stalls
The same probe at 448 MiB took 9.71 and 14.41 seconds, with 592 and 554 reclaim events and 0.65 and 1.28 seconds of full stalls
Each probe reserved a fresh `/api/session/login` check, read the first `/api/session/window` form packet, verified its text/password/submit controls and closed without entering credentials
These short samples measure backend form preparation and memory pressure, rather than guaranteeing UQ or MFA response times
Versioned frontend assets use public immutable caching, while HTML, sessions and private API responses remain uncached
Timey opens canonically at `/mini/timey`, with `?m=timey` and `?mini=timey` retained for existing bookmarks
The editor renders before its settings request and the fixed form schema no longer starts a private worker
After-paint module warming and a stable Suspense boundary preserve the current page while navigation resolves
Three fresh headless Chromium contexts measured 313–316 ms from click to the editor's second animation frame before the boundary fix, then 42–114 ms afterwards with a 47 ms median
The same final run reached the public home heading in 254–384 ms; earlier home samples ranged from 295 ms to 3,069 ms, so they do not establish a whole-page speedup
A separate live pass measured page-switch feedback at 22–32 ms across all six minis
The first saved-plan load in a fresh workspace still took 3,525 ms, including backend startup and rendering; retaining the bounded worker pool removes repeated cold starts for its two resident workspaces
Cloudflare returned a cache hit for the deployed entry script in 43 ms on the second fetch
The earlier sign-in-first build reduced the compressed entry script from 122,344 to 88,001 bytes in the same gzip comparison
Paired fresh Python processes creating the same local app measured 11.23 seconds and 78,184 KiB peak RSS before, then 2.04 seconds and 63,180 KiB after
Earlier original-release samples varied from roughly six to eleven seconds, so these are process-setup observations rather than a whole-site latency guarantee
The final real UQ form took 12.69 seconds to prepare on the backend; the editable frontend form appears immediately while that happens
YouTube denied the reported video from Oracle even with a JavaScript runtime, while the same source downloaded on the Mac
The current stable and nightly yt-dlp releases and the tested embedded, mobile, Safari, VR and TV clients still received the bot sign-in denial
The recommended PO-token provider explicitly does not remove IP-based login restrictions, so it has not been added as an unproven dependency
Playwright's bundled Node supplies the supported runtime without a separate installation; denied downloads offer a local-file recovery
Keep recovery backups of both `/var/lib/minis/` and `/var/lib/private/uq-minis/`, preserving permissions and ownership
No off-host backup has been configured
Older releases and the prior browser runtime remain available for rollback
Rollback has local regression coverage, including delayed readiness, but a remote rollback from a live release has not been exercised
The separate Keysi Rust services are not deployed by this Minis workflow

## Current implementation measurements

Five isolated process samples on the Oracle E2.1.Micro host measured 2,684.6 ms median CLI startup and 2,578.9 ms for the direct web entry
Those samples use the same installed release and avoid workspace state
Rendering 108 overlay frames across minimal, Minecraft and Temple Run at 640 × 360 took a median 2,307.5 ms with JIT disabled and 2,392.2 ms with JIT enabled, with matching output digests
JIT remains disabled because this workload showed no benefit
These are sampled startup and overlay costs, not whole-site latency or a guarantee for longer renders
The reproducible local benchmark is `uv run --directory backend python ../tools/scripts/bench.py`, with results under `out/artifacts/`
The current native entry is `minis-web`; it keeps the interactive CLI out of systemd startup
Private plan snapshots paint before revalidation, and fresh server queries stay reusable for 30 seconds

The cartoon correction also removes the public shelf's dependency on the catalogue response
Three fresh local Chromium contexts with the same simulated 800 ms catalogue delay measured a 1,567 ms median to visible cards before the change and 436 ms afterwards
Those samples use the Vite development server and do not measure the Oracle host
The production build under the real backend CSP measured 29–61 ms from a DOM click event to the new mini heading's second animation frame across eight switches
The separate Playwright locator timings include actionability waits and are not used as interaction latency
Evidence stays in `out/artifacts/shelf.json` and `out/artifacts/production.json`
The English date parser is a separate 14.5 KiB gzip chunk loaded on Fill details, keeping it out of initial page loading

Durable workspace state now belongs in `.config/<mini>/`, derived caches in `out/.cache/` and exports in `out/<mini>/`
The first migration copies and verifies legacy `.minis` files without deleting them
Quiesce old writers before cutover and preserve both state trees for rollback
The active local backend and its original drafts have been left running
