---
name: browser-authentication
description: Use when a workflow needs browser sign-in or a refreshed session; prepare the login, guide the person through it, save credentials privately and verify that the original task can continue
---

# Browser authentication

Get the person's blocked workflow moving again.
Identify the service, intended account and operation, then prepare its supported sign-in flow.
Keep passwords, MFA and account selection in the browser

## Establish the session

Inspect the application's existing credential location and authentication error.
Distinguish a missing session from expiry, the wrong account or a denied operation.
Use the application’s OAuth flow when available, or its established browser-session capture.
Start the authorised sign-in and explain the single human step clearly.
Never request cookies, tokens or passwords in chat

Save the session to the application’s private location, with owner-only access and atomic writes.
Refresh the intended credential file while preserving other settings and working credentials if capture fails.
Return to the original task once access is established.
Verify through an available read or preview before a consequential operation

## Use the tools

For UQ Forms, run the existing authentication mini:

```sh
uv run --extra auth mini auth
```

Its default is `.minis/auth/.env`.
Use `--force` to refresh that intended file, or `--output PATH` for a specific destination.
The person completes browser sign-in; unattended capture is unsupported.
Forms submission reads the default file or credentials already supplied through the environment

For Outlook, run `uv run --extra agent mini agent login --mailbox ADDRESS`, with `--username ADDRESS` when the sign-in account differs.
Mailbox state belongs in `.minis/agent/`.
For YouTube, use the timer workflow's OAuth flow, with its client-secret and token files in `.minis/timey/`.
These sessions serve different services and cannot be interchanged

## Finish and hand back control

Confirm the intended account, saved location and the read or preview that verified access.
Continue the authorised task that prompted sign-in.
Authentication alone does not authorise a new submission, email or upload

Keep the person-facing language calm and practical.
Say what the browser needs from them and what can proceed once they finish.
Report secret-free results, and turn a failure into one clear recovery step supported by the actual error
