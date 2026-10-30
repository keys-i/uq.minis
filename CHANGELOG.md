# Changelog

## v0.33.0

- Cache Timey’s ten-second background sections for local playback, remove embedded players and unify preview and export settings in consistent side controls
- Edit Timey directly on its preview with drag, resize, labels and contextual tools; add buffered playback, scrubbing and ten-second skips
- Start Timey from preview search or local upload, add iOS-style playback and a circular timing dial, and keep edge resizing and placement highlights together
- Resize Timey overlays independently by width and height, remove selection boxes and blend clean playback controls with the minis theme

- Separate Scrappy course selection, Planny assessment planning and Buzzy’s combined calendar; group booking follow-up inside Eventy and account access behind the sidebar avatar
- Crawl the official UQ course index, keep selection usable during catalogue outages and add offering badges, assumed knowledge and coloured prerequisite trees with keyboard path highlighting
- Give Timey a central live renderer preview, duration presets, a position pad and built-in YouTube search with ten-second timestamp previews

- Keep each event's risk-return recipient and exact subject together, add the authorised PF Assist choice to both interfaces, and preserve legacy return details when upgrading saved watches

- Separate React and npm into `frontend/`, Python and uv into `backend/`, and keep shared task skills at the repository root
- Add FastAPI browser routes for every mini, sharing the CLI's habitat colours, animal artwork and Python implementations
- Combine UQ course research, club discovery and published UNSW CSE offerings in Scrappy and Clubby, with validated imports and pooled public-directory requests
- Add Planny enrolments, assessment review, personal deadlines, Gantt planning, weighted marks with PAFs and hurdles, and subscribable local calendars
- Unify public Rubric announcements, authorised Discord scheduled events and social exports, with bounded search indexes and private local plans

- Give timer themes their own shared preview/export scenes, textured font fills and continuous motion: temple vines and cracks, stacked Minecraft worlds and reacting grass, moving graffiti trains, circuit traffic and liquid-glass refraction
- Show static, proportional flags twelve dots high in mascot-sized braille beside status, country and habitat; use separate flags for shared ranges, original vector colours and offline globe or regional silhouettes
- Rebuild all 50 animal sculptures from editable anatomy profiles at 224 × 160 dots and 24 FPS; replace generic rounded fins, horns, tails and torsos with shaped contours and clipped markings
- Articulate feathered wings through shoulder, elbow, wrist and separate feather fans; distinguish limb and foot types, diagonal trots, hopping extension, fixed dorsal fins and coordinated swimming
- Replace slogan-like animal bubbles with natural species-specific remarks and add underlined, hoverable reference links with a ↗ and Alt+A shortcut; browser errors preserve the menu
- Document species anatomy, locomotion research and reconstruction limits, with focused regressions for silhouette edges, joints, footfalls and link recovery

- Use calendars and hour/minute dials with arrows, Tab and eased markers; add sliders for bounded values and labelled resolution stops, with direct typing retained
- Complete nested folder and file paths, descend into directories with Tab and preserve filenames containing spaces
- Replace per-action menu receipts with final reviews; make Timey's Finish and create timer action start processing directly and choose numbered filenames for occupied interactive destinations
- Collect new event details and save their validated TOML before generation; review venue and document choices before writing or submitting
- Add verified official room photos, Right/Left photo and virtual-tour shortcuts, and recoverable missing-preview messages
- Expand public Python docstrings with input contracts, return values, cancellation and file-safety behaviour
- Unify mini inputs, navigation, alternating habitat-coloured rows and subtle highlights; retain the 55% scene / 45% content split, close the gap on wide terminals and prevent completion menus from reporting a small window
- Keep the left panel stable for sculptures up to 184 × 112 dots, thumbnails and live timer samples; resize from the original image and preserve selected previews beside compact right-panel loading bars
- Complete YouTube video and music queries as you type, with debouncing, cancelled obsolete requests and offline fallback; fetch the largest available thumbnail before trying smaller images
- Default exports to original source dimensions and best available YouTube quality; offer 240p–4320p ceilings, arbitrary heights above 240 and no upscaling of smaller footage
- Preview actual font lettering on hover or keyboard highlight, name its family and face, load Google Fonts on demand and cancel obsolete samples without leaving the picker
- Preserve textured natural fur with flag colours in highlights and surroundings; improve surface lighting, marine flukes, side-profile faces and ground shadows
- Animate at 16 frames per second with planted four-legged footfalls, connected elbows and knees, frog launch and landing poses, flightless bird rules and different tail movement for fish and cetaceans
- Ground habitat trees and terrain, add depth and parallax, and preserve delayed ear and tail settling, body breathing, swaying foliage, swimming wakes, dust and reactions in nearby plants
- Correct attached facial markings, tail bands, orangutan fist walking, wild axolotl colouring and eyelids, bumblebee wing and leg counts, and the Ganges dolphin's small eye; document animal references and reconstruction limits
- Make animals glance when hovered, reveal interaction hints and keep pointer targets attached across movement and terminal sizes; retain pause, reduced-motion and monochrome views
- Rebuild all 50 species as compressed movement assets while retaining editable geometry and bounded lazy caches
- Check movement, high-resolution rendering and pointer maps across the species catalogue; remove inherited virtual-environment warnings from isolated type checks

Requires Python 3.15+

[Development changes](https://github.com/keys-i/uq.minis/compare/v0.32.0...v0.33.0)

## v0.32.0

- Enforce strict basedpyright across source, tools, tests and the terminal artwork generator, with zero errors or warnings
- Type shared prompts, worker state, browser requests, media previews and upload credentials; validate nullable streams and keep custom thumbnails intact when saving upload drafts
- Give test fixtures and callbacks explicit contracts, preserve lazy CLI imports and make completion assertions wait for rendered choices
- Keep all 50 mascots visible in monochrome menus and show still portraits in compact or plain interactive terminals
- Run typing checks in `dev check` and GitHub CI against a freshly built wheel in an isolated environment, keeping interactive minis available throughout

Requires Python 3.15+

[Development changes](https://github.com/keys-i/uq.minis/compare/v0.31.1...v0.32.0)

## v0.31.1

- Centralise Ruff rules in `pyproject.toml` so direct commands, `dev` and CI share the same configuration
- Enable Python 3.15 preview support and apply safe lint fixes and consistent formatting across source, tools, tests and the artwork generator
- Preserve the 100-column layout and test docstring exemptions, and give automated GitHub releases their SemVer title

Requires Python 3.15+

[Development changes](https://github.com/keys-i/uq.minis/compare/v0.31.0...v0.31.1)

## v0.31.0

- Use shared nonblocking locks on Windows, macOS and Linux so Scrappy exports retain collision protection and checkpoint recovery
- Verify CLI help with and without ANSI colours, and use native directory separators in completion tests
- Wait for rendered shortcut panels in interactive tests and handle Windows pipe closure during video cancellation without leaving a thread warning
- Publish matching SemVer package metadata and curated changelogs, including the changelog in source distributions

Requires Python 3.15+; mini-owned state remains in `.minis/<mini>/`

[Development changes](https://github.com/keys-i/uq.minis/compare/v0.30.0...v0.31.0)

## v0.30.0

- Expand the forest to 50 species with an equal chance for every menu visitor
- Give new species distinct anatomy, habitats, routines and pointer reactions; keep eye glints visible on the braille grid
- Retain bounded animation caches, with measured new-frame rendering below 0.4 ms and retained memory near 10 MiB

Historical source release, incorporating all 29 development iterations

Requires Python 3.15+; keep mini-owned state in `.minis/<mini>/`. CLI and skills replace MCP; existing dotfiles are not migrated automatically

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/7514fe8672939ad5ef65b878fcac0e3fc76c7db7...fc5e7e4b4869e50770307ba3d850b92f93e0eb31)

## v0.29.0

- Replace the bundled plain room CSV with a compressed catalogue while retaining offline venue selection
- Reject corrupt, truncated and oversized inputs; compression is reversible and older snapshots retain the original CSV

Historical source release for development iteration 28; original code is preserved with version metadata updated to `0.29.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/ff64a20e089cdd190ad6a15035d99e1047bc14ce...7514fe8672939ad5ef65b878fcac0e3fc76c7db7)

## v0.28.0

- Parameterise bundled-font tests with Google Fonts online and offline
- Verify bundled fonts remain usable without starting a download

Historical source release for development iteration 27; original code is preserved with version metadata updated to `0.28.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/1043b789b8179cfbd7a26ccd4d95b31f9230187f...ff64a20e089cdd190ad6a15035d99e1047bc14ce)

## v0.27.0

- Search the complete Google Fonts catalogue, including Open Sans
- Cache validated catalogue data, offer fuzzy suggestions and retain offline fallback instead of sending invented font names to Google

Historical source release for development iteration 26; original code is preserved with version metadata updated to `0.27.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/d8393bb0f6d4a7948fc9555b517c9e91ecd1f2ea...1043b789b8179cfbd7a26ccd4d95b31f9230187f)

## v0.26.0

- Suggest named fonts for mood words, misspellings and uncertain input
- Keep an offline font shelf and expose useful shared APIs through lazy package exports

Historical source release for development iteration 25; original code is preserved with version metadata updated to `0.26.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/1313c3986cafba42c4ddf3855d5bf5c8b79220aa...d8393bb0f6d4a7948fc9555b517c9e91ecd1f2ea)

## v0.25.0

- Set the package author to `keys-i`
- Keep distribution metadata consistent with the project author

Historical source release for development iteration 24; original code is preserved with version metadata updated to `0.25.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/32b2b4d1c83267f6781f839af332133f18400bf4...1313c3986cafba42c4ddf3855d5bf5c8b79220aa)

## v0.24.0

- Improve terminal media samples and preview readability
- Document forest controls, motion preferences and editable artwork

Historical source release for development iteration 23; original code is preserved with version metadata updated to `0.24.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/2725fc563d4cc740a0da074d183e58853c73392d...32b2b4d1c83267f6781f839af332133f18400bf4)

## v0.23.0

- Animate a worldwide terminal forest with distinct animal routines and pointer reactions
- Add colourful alternating rows, flag colours, smooth selected-row marquees, natural shortcuts and recoverable interactive errors

Historical source release for development iteration 22; original code is preserved with version metadata updated to `0.23.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/da63d7daa3c690feb1c1e92afba4e07bbf2dd284...2725fc563d4cc740a0da074d183e58853c73392d)

## v0.22.0

- Search YouTube from countdown setup and show title, duration and thumbnail previews
- Let the user accept a result to fill its URL, or return without selecting it

Historical source release for development iteration 21; original code is preserved with version metadata updated to `0.22.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/2068241c5f6ec82641bf9ab1cb212e637c9c9772...da63d7daa3c690feb1c1e92afba4e07bbf2dd284)

## v0.21.0

- Share interactive terminal portraits and media previews
- Give mini workflows a common visual grammar and reusable preview rendering

Historical source release for development iteration 20; original code is preserved with version metadata updated to `0.21.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/4b80d88130e40ce32b08c610a7fd47e822a8b3ef...2068241c5f6ec82641bf9ab1cb212e637c9c9772)

## v0.20.0

- Bundle editable shaded animal sculptures and movement frames
- Verify installed artwork and use bounded rendering caches

Historical source release for development iteration 19; original code is preserved with version metadata updated to `0.20.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/2135006e56779c3738cf6bb877441911e235d2e7...4b80d88130e40ce32b08c610a7fd47e822a8b3ef)

## v0.19.0

- Test every mini on Linux, macOS and Windows
- Verify built packages, rebuild the wheel from the source archive and check installed assets away from the checkout

Historical source release for development iteration 18; original code is preserved with version metadata updated to `0.19.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/c884cdf25af0b8424d9e508a3cd4b2eb031495f6...2135006e56779c3738cf6bb877441911e235d2e7)

## v0.18.0

- Repair source and dependency security audits
- Update affected dependencies and preserve strict audit failure reporting

Historical source release for development iteration 17; original code is preserved with version metadata updated to `0.18.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/b51d7d8d4d87956a2c3fcccd3e53f45032e4cab1...c884cdf25af0b8424d9e508a3cd4b2eb031495f6)

## v0.17.0

- Require Python 3.15 and adopt its deferred-import support
- Keep optional mini dependencies out of unrelated command startup paths

Historical source release for development iteration 16; original code is preserved with version metadata updated to `0.17.0`

Python requirement: `>=3.15`

[Development changes](https://github.com/keys-i/uq.minis/compare/a07c2ce9f1c22fcd0debf64a8c65513bc3460bc2...b51d7d8d4d87956a2c3fcccd3e53f45032e4cab1)

## v0.16.0

- Run the complete Linux test environment in GitHub Actions
- Make test failures and the coverage gate block CI, with reports available for inspection

Historical source release for development iteration 15; original code is preserved with version metadata updated to `0.16.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/376b5067362e4fd691335b90f79cf9b9d88c35fe...a07c2ce9f1c22fcd0debf64a8c65513bc3460bc2)

## v0.15.0

- Replace command-sheet skills with reusable task playbooks
- Document mini workflows, input inspection and deliverable checks in warm Australian English

Historical source release for development iteration 14; original code is preserved with version metadata updated to `0.15.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/a5ccadd0502cac1cce0d38b3b101b931f346c274...376b5067362e4fd691335b90f79cf9b9d88c35fe)

## v0.14.0

- Cover countdown rendering and upload validation
- Exercise media configuration and upload failure paths with controlled inputs

Historical source release for development iteration 13; original code is preserved with version metadata updated to `0.14.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/53e6f40c3d9a0be8ee8f7cc9988e52bff6cf962d...a5ccadd0502cac1cce0d38b3b101b931f346c274)

## v0.13.0

- Parameterise Scrappy export and menu tests
- Check course output and selection behaviour across representative inputs

Historical source release for development iteration 12; original code is preserved with version metadata updated to `0.13.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/9ec4d201d78861d9013dbc80d28f7e9ac3b2c15c...53e6f40c3d9a0be8ee8f7cc9988e52bff6cf962d)

## v0.12.0

- Cover mailbox safety and persistent worker recovery
- Exercise failures and resume behaviour without sending real email

Historical source release for development iteration 11; original code is preserved with version metadata updated to `0.12.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/342d9379f604aa84fd01beff8a8543b3d8669b95...9ec4d201d78861d9013dbc80d28f7e9ac3b2c15c)

## v0.11.0

- Separate reusable test setup from individual test cases
- Parameterise CLI coverage and reduce repeated fixtures

Historical source release for development iteration 10; original code is preserved with version metadata updated to `0.11.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/2466a94b3d7ad48523cc5fd8f5bd88f6c76c351b...342d9379f604aa84fd01beff8a8543b3d8669b95)

## v0.10.0

- Give each mini its own command registration in `src/cli/`
- Share Typer, Rich and prompt infrastructure; keep domain logic in each mini folder

Historical source release for development iteration 9; original code is preserved with version metadata updated to `0.10.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/ba9e751af66f19ba84be4116e00a9ba15155e2e6...2466a94b3d7ad48523cc5fd8f5bd88f6c76c351b)

## v0.9.0

- Add validated YouTube upload drafts and uploads
- Check metadata and upload choices before sending a generated video

Historical source release for development iteration 8; original code is preserved with version metadata updated to `0.9.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/d3cab49976ec500419c5d61a42c18e3e36753ebc...ba9e751af66f19ba84be4116e00a9ba15155e2e6)

## v0.8.0

- Add countdown rendering with reusable media inputs
- Validate timer settings and retain editable configuration alongside generated video output

Historical source release for development iteration 7; original code is preserved with version metadata updated to `0.8.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/6b1b7d15e5bcf26b7fbe03ff3614fca9c56189fc...d3cab49976ec500419c5d61a42c18e3e36753ebc)

## v0.7.0

- Add countdown styles and reusable bundled artwork
- Keep fonts and visual assets in `docs/assets/` for predictable offline use

Historical source release for development iteration 6; original code is preserved with version metadata updated to `0.7.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/9465564aeee75255e0d1da323c735104a026a227...6b1b7d15e5bcf26b7fbe03ff3614fca9c56189fc)

## v0.6.0

- Share cache publication, size budgets and eviction across minis
- Keep Scrappy-owned cache and state under `.minis/scrappy/`

Historical source release for development iteration 5; original code is preserved with version metadata updated to `0.6.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/0990b3118d335e301b7b9db57f476b3222f8ed69...9465564aeee75255e0d1da323c735104a026a227)

## v0.5.0

- Add campus, building and room selection during event setup
- Filter rooms by capacity, preview virtual tours and apply the selected venue without rewriting the event TOML

Historical source release for development iteration 4; original code is preserved with version metadata updated to `0.5.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/964c6d784b945d03390a68d89122abf3985c6836...0990b3118d335e301b7b9db57f476b3222f8ed69)

## v0.4.0

- Move persistent mailbox processing into `src/worker/`
- Repair Outlook composition and preserve worker recovery behaviour

Historical source release for development iteration 3; original code is preserved with version metadata updated to `0.4.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/5a0ed7cdb3a9813600628fd800d6e62919855f43...964c6d784b945d03390a68d89122abf3985c6836)

## v0.3.0

- Move common helpers, consoles, prompts and terminal setup into `src/core/`
- Reuse shared infrastructure instead of maintaining separate mini implementations

Historical source release for development iteration 2; original code is preserved with version metadata updated to `0.3.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/7d7c7c3c53dc91cd1450036de537401fa08d4fe3...5a0ed7cdb3a9813600628fd800d6e62919855f43)

## v0.2.0

- Remove the minis MCP adapters, server discovery and MCP dependencies
- Keep the supported workflows available through skills and the CLI

Historical source release for development iteration 1; original code is preserved with version metadata updated to `0.2.0`

Python requirement: `>=3.12`

[Development changes](https://github.com/keys-i/uq.minis/compare/a263ff886c25ec74caefa28bc3cf3190309c76a2...7d7c7c3c53dc91cd1450036de537401fa08d4fe3)
