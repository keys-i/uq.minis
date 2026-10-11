---
name: event-planning
description: Use when asked to plan an event, find a room, prepare a booking application or produce a risk assessment; take the brief through venue choice, editable drafts and checked outputs
---

# Event planning

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

When UQ minis is available, read `examples/movie-night/event.toml` for the current input shape and create or update the user's event TOML.
Use the room picker or `uq_minis.minis.event.rooms.read()` to research the bundled catalogue
The public directory is compressed in `docs/assets/event/rooms.csv.gz`, checked against https://campuses.uq.edu.au/list-rooms on 2026-10-09
Use a current official source to verify changes that affect the booking

For a person choosing in the terminal, run `mini event event.toml --choose-room`.
Tab searches building names/numbers and room numbers; room choices show capacity and offer a tour before selection.
`--rooms PATH` or `.minis/event/rooms.csv` supplies their custom list.
The picker applies the selection to that run's outputs; write an agreed venue back to the TOML when future runs need it.
Keep the Forms capacity answer consistent with the selected room

For agent-driven generation, run the CLI with the event's source path, explicit output modes and a preview flag.
Set the requested destination, then open and inspect the generated files:

```sh
uv run mini event event.toml --form --risk --layout both --preview --no-input -o outputs/event
```

When submission is already authorised and the draft is ready, run `uv run mini event event.toml --form --submit --no-input -o outputs/submission` with the agreed source and destination.
Use a fresh destination or `--force` only when replacing an existing output is intended.
Resolve missing sign-in through the browser-authentication skill.
If the response is uncertain, check status before attempting another submission

## Finish with something useful

Deliver the editable event source, requested documents, chosen venue and any unresolved booking fact.
Check the files open, the location and timings match, and the risk controls suit the activity.
Speak like a capable colleague: warm, direct and specific.
Lead with what is ready, explain the venue choice in everyday terms, link the drafts and name the next decision only when one remains.
Keep schema keys and setup chatter out of the organiser's main answer
