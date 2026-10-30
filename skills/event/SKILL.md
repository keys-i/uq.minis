---
name: event-planning
description: Use when asked to plan an event, find a room, prepare a booking application or produce a risk assessment; take the brief through venue choice, editable drafts and checked outputs
---

# Event planning

Run Python commands from `backend/` in this checkout

Take ownership of the event preparation and leave the organiser with a plan they can use.
Read their existing brief and files, fill the available fields, find suitable venues and build the requested documents.
Carry out the authorised work through the available tools

## Get moving

Find the event notes or existing application first.
Extract the title, purpose, date, audience, attendance, activities, coordinator and setup/event/pack-up times.
Ask one bundled question for missing facts that affect the venue or application, while drafting everything independent of the answer.
Keep unknown facts visible in the draft

When a venue is needed, filter rooms by campus, attendance and the activity's layout.
Shortlist a few useful matches with building, exact room number, seats and a reason each fits.
Offer the virtual-tour link before the organiser chooses.
Record the chosen venue and check that booking times cover setup and pack-up.
A room listing gives capacity, not a confirmed reservation

Build a run sheet with time, activity, owner and equipment.
For the risk assessment, connect each actual hazard to people affected, practical controls and the responsible person.
Use the organisation's required matrix and template.
Make venue, attendance, contacts and timings agree across the application and risk document

## Use the tools

When UQ minis is available, read `backend/examples/movie-night/event.toml` for the current input shape and create or update the user's event TOML.
Use the room picker or `uq_minis.minis.event.rooms.read()` to research the bundled catalogue
The public directory is compressed in `backend/assets/event/rooms.csv.gz`, with photo links checked against https://campuses.uq.edu.au/list-rooms on 2026-10-14
Use a current official source to verify changes that affect the booking

For a person choosing in the terminal, run `mini event event.toml --choose-room`.
Type to search building names/numbers and room numbers; Tab completes the highlighted choice
Right opens the highlighted room's official photo and Left opens its virtual tour without selecting it
Review the room's capacity and intended layout before accepting the venue
`--rooms PATH` or `.config/event/rooms.csv` supplies their custom list.
The picker applies the selection to that run's outputs; write an agreed venue back to the TOML when future runs need it.
Keep the Forms capacity answer consistent with the selected room

For a new source, enter an unused `.toml` path in the interactive wizard
Collect the person's event details first, use arrows and Tab in its calendar and schedule dials, then review and save the TOML before generation
Additional Forms questions and terms remain unanswered in a booking draft until reviewed; do not infer consent or submit an unfinished source

For agent-driven generation, run the CLI with the event's source path, explicit output modes and a preview flag.
Set the requested destination, then open and inspect the generated files:

```sh
uv run mini event event.toml --form --risk --layout both --preview --no-input -o out/event/event
```

When submission is already authorised and the draft is ready, run `uv run mini event event.toml --form --submit --no-input -o out/event/submission` with the agreed source and destination.
Use a fresh destination or `--force` only when replacing an existing output is intended.
Resolve missing sign-in through the browser-authentication skill.
If the response is uncertain, check status before attempting another submission

## Finish with something useful

Deliver the editable event source, requested documents, chosen venue and any unresolved booking fact.
Check the files open, the location and timings match, and the risk controls suit the activity.
Speak like a capable colleague: warm, direct and specific.
Lead with what is ready, explain the venue choice in everyday terms, link the drafts and name the next decision only when one remains.
Keep schema keys and setup chatter out of the organiser's main answer


## Browser workflow

Eventy combines Prepare event with Booking & replies, reusing the existing event and persistent mailbox implementations
Account connections live behind the sidebar avatar and require the existing verified UQ session
Legacy `mini auth` and `mini agent` commands remain supported; authentication does not grant sending authority
