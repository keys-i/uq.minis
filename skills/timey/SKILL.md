---
name: countdown-video
description: Use when asked for a study timer or themed countdown video; turn the visual brief into a checked preview, finished render and editable publication details, using available rendering tools
---

# Countdown video

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
YouTube downloads also require the supported Node.js or Deno runtime.
Local footage can be used directly

Start with a reviewable preview:

```sh
uv run --extra timey mini timey gameplay.mp4 --length 10m --style minecraft --preview --no-input -o outputs/preview.png
```

Use the user's actual source, length and style in that command.
The interactive wizard offers a short motion preview and Tab completion for choices and paths.
Use its video or music search when the person needs help choosing footage, then inspect the thumbnail, title and duration before selecting the link.
Review the actual timer style, position, colour and font samples
When the person describes lettering instead of naming a font, search the font shelf by mood or approximate name, then review a real named family before applying it
Treat suggestions such as Arimo for “ariel” as alternatives for the person to choose
Keep their words out of exact Google Fonts requests unless they supplied a specimen link
Check custom thumbnails and opening-frame previews against the person's publication brief.
For a custom theme, use the installed, signed-in designer supported by the workflow and inspect the saved style.
Saved styles, fonts, media cache and OAuth files live in `.minis/timey/`.
Bundled artwork and font licences live in `docs/assets/timey/`

Once the preview fits the brief, render the agreed video:

```sh
uv run --extra timey mini timey gameplay.mp4 --length 10m --style minecraft --no-upload --no-input -o outputs/timer.mp4
```

For publication requested in the brief, prepare and review the editable title, description and thumbnail, then use the upload workflow with the existing authority.
After an interrupted upload, inspect YouTube Studio before attempting another

## Inspect and deliver

Verify rendered duration and streams, opening and ending frames, countdown readability, cropping, loop joins and audio.
Give the person the finished file and editable assets or metadata they need.
State any playback or destination check that remains untested

Keep the language warm and visual.
Describe what they can see and hear, connect style choices to their brief, and lead with the preview or finished timer.
Keep codec options, cache mechanics and authentication setup out of the creative handoff unless they affect the person's next choice
