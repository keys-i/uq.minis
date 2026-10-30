---
name: countdown-video
description: Use when asked for a study timer or themed countdown video; turn the visual brief into a checked preview, finished render and editable publication details, using available rendering tools
---

# Countdown video

Run Python commands from `backend/` in this checkout

Make the timer the person asked for, from the brief through the finished file.
Take care of timing, composition and export, while keeping the person involved in meaningful creative choices

## Build the brief

Read the supplied footage, references and destination requirements.
Establish countdown length, opening gap, finishing hold, output size, background audio and any separate music.
Choose the style, position and optional label from the person's brief.
Ask about a gap that affects the result, and use reversible defaults for routine export choices.
Preserve supplied media and use material suitable for its intended publication

Keep the digits readable against busy footage, with stable positions and useful contrast.
Check long times, the final seconds, zero, opening and finishing states.
A short background needs a comfortable loop rather than a jump repeating throughout the timer.
Retain editable custom artwork and metadata

## Use the tools

When UQ minis is available, use `mini timey --help` for the current flags and available presets.
Check that FFmpeg and ffprobe are installed before preparing a render.
YouTube downloads also require the supported Node.js or Deno runtime
Reuse Playwright's bundled Node when no system runtime is available
Some hosting IPs are denied by YouTube even with a runtime; explain that limit without requesting browser cookies and retain a local-file recovery
Local footage can be used directly

Start with a reviewable preview:

```sh
uv run --extra timey mini timey gameplay.mp4 --length 10m --style minecraft --preview --no-input -o out/timey/preview.png
```

Use the user's actual source, length and style in that command.
The interactive wizard offers a short motion preview and Tab completion for choices and paths.
Tab on a highlighted folder descends into it, including nested paths with spaces
Review the final timing, layout, quality, sound and save location before choosing Finish and create timer
Occupied filenames entered in the save prompt receive a numbered suffix; inspect the final path before rendering
Numeric ranges use sliders or dials, with direct typing retained
Video and music queries also offer YouTube autocomplete while preserving typed searches when predictions are unavailable
Use its video or music search when the person needs help choosing footage, then inspect the thumbnail, title and duration before selecting the link.
Review the actual timer style, position, colour and font samples
Watch a digit change in the live preview and check the theme's own materials and scene
Temple Run grows moss and crawling insects around the stone, while the idol's green repair pulses seal seeded cracks
Its energy weakens near the end, goes dark at ten seconds and the stone fractures into falling pieces during the final five seconds
The countdown stays readable over the rubble; short timers compress that collapse into their available time
Game overlays use open silhouettes: floating Mario platforms, twin Minions goggles, a native Minecraft survival HUD, Sonic’s winged ring, Pac-Man maze numerals and painted Subway lettering
Coins and mushrooms, blinking eyes and bananas, spinning rings and a runner, chasing ghosts, trains and circuit traffic animate in their own worlds
Keep the countdown readable while those details move, including the opening, final seconds and zero
Hover or highlight a font option to inspect its lettering on the animated timer and check the displayed family and face before accepting it
Google Fonts samples load on demand; a failed sample keeps the picker open, and changing the highlight cancels the earlier request
Search the full Google Fonts catalogue by name, including families such as Open Sans
When the person describes lettering instead of naming a font, search by mood or approximate name, then review a real named family before applying it
Treat suggestions such as Arimo for “ariel” as alternatives for the person to choose
Keep their words out of exact Google Fonts requests unless they supplied a specimen link
Check custom thumbnails and opening-frame previews against the person's publication brief.
For a custom theme, use the installed, signed-in designer supported by the workflow and inspect the saved style.
Saved styles, fonts, media cache and OAuth files live in `.config/timey/`.
Bundled artwork and font licences live in `backend/assets/timey/`

Once the preview fits the brief, render the agreed video:

```sh
uv run --extra timey mini timey gameplay.mp4 --length 10m --style minecraft --no-upload --no-input -o out/timey/timer.mp4
```

Original quality is the CLI default: `--height 0` preserves local source dimensions and requests the best available YouTube footage
Use a positive height of at least 240 when the destination needs a ceiling, including 240p–1080p or higher exports
The same ceiling applies to terminal samples, whose visible resolution also depends on terminal cells and available thumbnail quality
Selected samples stay on the left while compact preparation progress remains on the right

For publication requested in the brief, prepare and review the editable title, description and thumbnail, then use the upload workflow with the existing authority.
After an interrupted upload, inspect YouTube Studio before attempting another

## Inspect and deliver

Verify rendered duration and streams, opening and ending frames, countdown readability, cropping, loop joins and audio.
Give the person the finished file and editable assets or metadata they need.
State any playback or destination check that remains untested

Keep the language warm and visual.
Describe what they can see and hear, connect style choices to their brief, and lead with the preview or finished timer.
Keep codec options, cache mechanics and authentication setup out of the creative handoff unless they affect the person's next choice


## Browser preview desk

The large live timer preview is central, with timing and named video-quality choices on the left and visual controls below
Start with the centred video search or upload inside the empty preview; timer controls appear after the backdrop is ready
Pasting a YouTube link selects it with its timestamp; local videos and raster pictures, including HEIC/HEIF, can be dropped or pasted onto the preview
Still image imports are limited to 16 megapixels and become safe PNG backgrounds in both previews and exports
Animated GIF, APNG and WebP imports retain their motion through a bounded MP4 conversion, up to five minutes at 1920 × 1080
Drag the timer, resize width and height from four corner grips and click or right-click it for a floating toolbar with label, look, colour, alignment and Music controls
Dragging to an edge or corner highlights a destination; release to align without resizing, or use the interior for free positioning
Hover the placement control to open its visual popover; drag into a preset to preview and apply it, or use the edge, corner and centre choices with a click or keyboard
Look and Music open their settings from the timer toolbar; background search and volume expand on hover or keyboard focus
Look searches the shared font catalogue by family, approximate name or style through “Search any font…”; Google Fonts links and local font paths use the same field; uploaded or pasted TTF, OTF, TTC, WOFF and WOFF2 files are checked with FreeType
Choose Rolling digits or Simple countdown and drag the video-loop fade from a clean cut to a soft two-second blend
Custom joins the theme buttons and opens its artwork fields in a context bubble; selecting a built-in theme preserves the custom draft for later
Video details and writing notes sit below quality with a divider; publication drafts always use general audience, no realistic synthetic footage and the opening-frame thumbnail
Look, Music, Colour and placement share rounded speech bubbles that stay beside their toolbar buttons and within the viewport as content changes
Alt/Option bypasses snapping, Home centres the timer and Escape cancels an unfinished drag
The toolbar disappears when idle without hiding a focused control; video controls appear on hover or keyboard focus and stay available for touch
Arrow keys nudge, Shift nudges further and +/− resize; the same free placement is available through `--x` and `--y` in the CLI
Duration presets and the circular timing dial keep common choices immediate
Quality, motion and cache refresh stay visible under the dial; their compact dropdowns close with a selection, Enter or Escape
A zero-duration draft keeps its real 00:00 overlay visible, while exporting requires a positive duration
Busy hover previews retry with the server’s delay and cancel when the pointer leaves
Dragging beyond a full turn stretches the dial; release to stretch, recoil and settle back to zero, then choose a positive duration before exporting
Super Mario, Minions, Sonic and Pac-Man join the original timer looks, with locally drawn symbols and the same animated scenes in browser samples, CLI previews and exported videos
The get-ready and finishing gaps each use a smaller ring inside the main dial
Changing the timer look, length, size, label, colour or position redraws the actual shared overlay without downloading footage
After the first still appears, the central preview plays a bounded four-second animated loop from the shared renderer
Reduced motion, background tabs and reduced-data preferences keep the still; abandoned previews cancel and release their image URLs
Built-in YouTube search uses the CLI’s five-result search, and selected videos preview the first ten seconds after the chosen start timestamp
Rendered motion samples last up to ten seconds and include the actual countdown and local footage
Sound opens beside its clicked toolbar button, with keyboard focus and native outside-click dismissal
Music uses the same search-or-link field as video, with local audio/video upload, drag-and-drop and native Paste
Command–V, Control–V, menu Paste and assistive paste use the same clipboard events
Direct file links use the browser’s cross-origin access rules; when a site blocks access, explain how to download and add a local copy
Choose Listen to audition the cached track with the backdrop; volume uses a slider, and named icon buttons control mixing and original video sound
Uploaded music remains available to previews and exports through its workspace registration
The colour wheel offers hue, saturation, brightness, named swatches, a hex value and the original theme colour
Custom artwork and export options retain the same settings as the preview
Video search shows thumbnails and prepares ten-second hover samples on demand
Selecting a video caches a playable ten-second section first, then prepares the complete local H.264/AAC backdrop in the background
Playback position and Music controls survive the swap to the complete cache; changing source, seeking an uncached section or leaving cancels obsolete work
The player offers local scrubbing, play/pause and ten-second skips; seeking also selects the background start for the finished timer without downloading another section
Longer videos need an initial download and conversion, under the shared cache budget and a five-minute conversion limit
Search and preparation feedback stays inside the preview, with cancellation for abandoned work
Themed status notes and actionable recovery bubbles share the tool palette; hints use themed pointer and keyboard popovers
Loading uses wallpaper-backed mist, interactive dust and a real thumbnail sampled at low resolution
Visible timer and playback skeletons sit in the mist; soft overlapping washes add detail through several resolution levels without rectangular reveal tiles
The resolution starts at eight pixels, improves the available thumbnail while waiting and reaches native playback in at most 1.5 seconds after decoding
Temporary display surfaces stay within 960 × 540 and release their pixels afterwards; a shared uneven feather keeps the scenery edge consistent on hover and selection
Reduced motion, background tabs and reduced-data preferences skip the refinement and keep these effects still
Optional browser preview storage is capped at 24 entries, 24 MiB and one day; blocked or slow storage always falls back to rendering
Raw media and preview files share the existing media-cache budgets and atomic publication
YouTube can deny a download; keep its error visible and offer another video or a local file without replacing a working cache entry
Watch preview and Make video replace the central editor with the actual rendered sample or final movie
Edit video restores the retained draft and its appearance controls; quality and frame rate remain available in every stage
Save video offers a device download or reviewed upload without requiring UQ access
Browser workspaces retain drafts independently of Eventy's UQ sign-in
YouTube uploads use the existing private publication workflow; Keysi CDN stays unavailable until connected
Custom artwork uses a name and description with follow-up answers and subsequent revisions, retaining the previous artwork
Quick typing predictions use the same CLI suggestion service with cancellation and a bounded optional cache
Publication remains a separate reviewed action

## Hosted backdrop failures

A YouTube upload token is separate from download authentication
If the provider requires sign-in, open Timey's YouTube connection and let the person use Google's real page
Only this workspace remembers provider cookies in `.config/timey/youtube/`; never request passwords or cookies in chat
A saved connection is not proof that a server download works
Check a fresh requested section of the original failing source and another source before reporting a fix
If Google refuses the hosted browser or YouTube still denies access, retain the draft and offer the file picker with the actual provider error

Use `out/timey/` for exports and `out/.cache/timey/` for derived media
Keep uploaded originals and chosen fonts durable under `.config/timey/`
