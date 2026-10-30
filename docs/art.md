# Browser artwork

The browser uses 50 whole cartoon residents with locally bundled DynaPuff headings and Comic Neue lettering
Their [font licences](licenses/) remain beside the documentation

## Editable sources

The original rounded, attached animals are the visual source of truth
Each runtime pose is one complete silhouette, without separately assembled heads or limbs

| Source | Runtime asset | Purpose |
| --- | --- | --- |
| [Original animals](../frontend/assets/images/wildlife.webp) and [activity poses](../frontend/assets/images/poses.webp) | [Cartoon atlases](../frontend/assets/wildlife/cartoons/) | The original 24 residents, with idle, activity and resting illustrations |
| [Additional cartoon sources](../frontend/assets/wildlife/cartoons/source/) | Cartoon atlases | Awake and resting illustrations for 26 additional species |
| Whole-character artwork | [Portraits](../frontend/assets/wildlife/cartoons/portraits/) | Small resident-picker thumbnails |
| [Habitat sources](../frontend/assets/habitats/source/) | [Habitats](../frontend/assets/habitats/) | Twenty individually loaded landscapes, softened behind the characters |
| [Species catalogue](../backend/assets/wildlife.toml) | `out/tools/wildlife.json` | Stories, facts, conservation sources, coordinates and home zones |
| [Pose bounds](../frontend/assets/wildlife/cartoons/index.toml) | `out/tools/cartoons.json` | Generated cell bounds and source digests |

Run `npm --prefix frontend run assets` after changing artwork and `npm --prefix frontend run configure` after editing the catalogue
The Pillow compiler skips unchanged sheets, isolates connected alpha silhouettes and packs each complete illustration into a padded 320 by 220 cell
Its alpha mask removes neighbouring fragments even when another animal overlaps a crop rectangle
Original PNG sources and the rejected anatomical-part artwork remain available for recovery
The default build uses the complete cartoons
SVG icons, flags and masks remain external files under `frontend/assets/`, with no inline SVG

## Movement and ownership

One lazy Pixi renderer paints visible whole characters into a shared viewport canvas
Its no-eval compatibility module works under the existing strict script policy
React owns controls and infrequent action changes; the ticker owns bounded travel, flight, small breathing movements, weather and visitors
Walking moves towards one destination instead of pacing endlessly on a sine loop
The illustrated resting and active poses remain intact during movement

A native whole-character still remains visible during loading, reduced motion, context loss or renderer failure
Textures are reference-counted and unused entries are evicted above eight cached resources
The canvas, observers and listeners close when their last resident leaves
DPR is capped at two and the canvas at four million pixels
Devices reporting four or fewer hardware threads use a 30 fps ceiling

Residents remain stable for each mini and can be changed through the story's searchable picker
Independent action schedules avoid immediately repeating an action
Mini-page residents sleep after 90 seconds without activity and wake with species-specific movement
Burrows gradually refill, flying visitors cross suitable scenes, and rain or snow follows the home's forecast
Daylight changes continuously around sunrise and sunset, with the home clock as an offline fallback
Weather uses representative home locations, never visitor coordinates, with MET Norway and CC BY attribution in the story

## Verification and budgets

Tests check all 50 residents, whole-pose frame bounds, asset sizes, non-repeating actions and visitor bounds
Portraits stay below 12 KiB each and character atlases below 400 KiB
Each three-card row widens the hovered or focused tool without changing its reading order
The active card types a short description; touch layouts show every description without relying on hover
Titles sit on quiet paper captions while the animal and its story remain separate controls
See [frontend setup](frontend.md) for browser checks and [hosting measurements](hosting.md) for performance evidence
