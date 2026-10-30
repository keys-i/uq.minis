---
name: planny
description: Plan UQ assessments, review course profiles, calculate marks and combine authorised club events into a personal calendar
---

# Planny

Run Python commands from `backend/`
Use `uv run mini planny --help` for headless commands or `uv run --extra browser mini browser` for the React interface after building `frontend/`

Start from the student's actual enrolled courses and chosen semester/campus profiles
Refresh the course index with `mini scrappy links -o .config/scrappy/offerings.csv` and clubs with `mini clubby refresh`
Do not infer enrolment from browsing history or create example marks in a real plan

Sync published assessment names, weights, Brisbane deadlines, date windows and task descriptions automatically
Keep these official fields read-only while allowing personal progress, marks and planning around them
Retain unclear dates as published text instead of guessing

Personal buffers create earlier targets without altering official deadlines
Marks support weighted scores, a multiplicative PAF, percentage-point penalties, individual hurdles and equal-weight drop-lowest groups
Record evidence in course notes and leave rules unverified until reviewed
Unsupported scaling, rounding, bonus and replacement rules need explicit manual adjustments

Open Buzzy as its own calendar for official deadlines, personal targets and followed or saved society events
Keep course selection and research in Scrappy, society discovery in Clubby and event bookings and email follow-up in Eventy
Use Buzzy for public Rubric events, authorised Discord scheduled events, approved Facebook/Instagram/LinkedIn post reads or social JSON imports
Read `docs/sources.md` from the repository root for access setup
Never reuse the historical Discord token or ask someone to paste a secret into the browser
Use the union directory for all listed clubs, and connect live social feeds only where the account owner has authorised access
Social reads cover one recent page of at most 100 posts; publication dates never become calendar event dates automatically

Inspect the calendar and projections, then export an editable backup and ICS if requested
CLI commands `show`, `marks`, `calendar` and `import` use the same private plan
Use `mini scrappy research --refresh "fun first year coding"` for the daily attributed course/review snapshot, `--expand` for weekly independent star observations, or `--professors` for available teacher reviews
Browser and CLI share the credibility-weighted minis rating and default to the current/upcoming semester; use `--semester all` or an explicit semester to override
Use `--minimum`, `--offset`, `--metric` and `--order` to control rankings and pagination
The scoring method, overlap exclusions and date-window shortcut are documented in `docs/access.md`
Use `mini scrappy secat saved-chart.html` to combine a saved official SECaT course chart without importing restricted staff comments
Source meanings, translation and verified browser access are documented in `docs/access.md`
Import refuses to replace an existing plan unless the person explicitly chooses `--force` after checking a backup
Local calendar subscriptions need the server running; other devices need a separately hosted authenticated service
