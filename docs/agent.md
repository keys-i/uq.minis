# Outlook event watcher

The watcher is a local macOS background worker for registered event applications. It watches for the risk-assessment request, replies to `pfeventa@uq.edu.au` with the required form and attachment, then watches the same conversation for a UQ Clubs booking update. It alerts you when it finishes or when booking wording needs review.

## Browser setup

The browser backend uses Outlook on the web. It needs no Entra app registration or Apple Mail. Sign in normally, including UQ MFA; the worker saves its own Chromium profile under the private state directory.

```sh
uv sync --locked --extra agent
uv run --extra agent playwright install chromium
uv run --extra agent mini agent login --mailbox YOUR_ACTUAL_UQ_EMAIL --username s1234567@uq.edu.au
```

`--mailbox` is the actual **From** address on your sent emails. `--username` is the address in Outlook's account menu and Microsoft's sign-in screen, such as `s1234567@uq.edu.au`. Omit `--username` when both addresses are the same.

In Outlook settings, use English and **Mail → Layout → Show email as individual messages**, with the reading pane visible. Login checks the account shown in the account menu. Later polls run Chromium without a visible window.

**The browser backend is experimental.** Its parsing and restart safeguards have local tests; the Outlook controls still need validation with a signed-in UQ mailbox. An unrecognised layout stops processing and reports an error. It doesn't work around a blocked Outlook web sign-in or MFA challenge. Run `login` again when the session expires.

The browser reads matching emails using Outlook's EML download action. Opening them may mark them read. Replies are matched through their `References` and `In-Reply-To` headers; missing thread headers cannot confirm a booking automatically.

## Graph setup (optional)

Graph requires a Microsoft Entra app registration. Follow Microsoft’s [register an app guide](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app), using the UQ tenant and a single-tenant app where appropriate. Record its Application (client) ID and Directory (tenant) ID.

In **API permissions**, add Microsoft Graph delegated permissions `Mail.ReadWrite` and `Mail.Send`. In **Authentication**, enable **Allow public client flows** for device-code sign-in. Do not create a client secret. UQ may require an administrator to approve these permissions.

```sh
uv sync --locked --extra agent
uv run --extra agent mini agent login --backend graph --client-id CLIENT_ID --tenant-id TENANT_ID --mailbox you@uq.edu.au
```

Sign in as the mailbox named in `--mailbox`. Re-run `login` if the tenant revokes access.

Supplying client and tenant IDs also selects Graph for existing commands. Without them, `login` selects the browser backend. A failed Graph setup can be replaced if it has no saved token cache and no processed events. Otherwise use a separate `--state-dir` and pass it to each command.

## Watch an event

```sh
uv run --extra agent mini agent watch event.toml --event-id ID --attachment approved.docx
```

`--attachment` accepts an approved `.docx` or `.pdf`. `--since YYYY-MM-DD` limits old mail; without it the watcher starts 30 days back. Omit `--attachment` to generate the risk form from TOML. Registration saves a fixed copy of the form; later edits do not change it. Each Event ID can be registered once.

The worker checks mail every 60 seconds. It matches the event ID and title, replies only to `pfeventa@uq.edu.au`, and looks for `clubs@uqu.com.au` in the same conversation. Clear booked, not-booked or changed wording completes the watch. Ambiguous wording sends a notification and leaves it running for your review.

```sh
uv run --extra agent mini agent install
uv run --extra agent mini agent status
uv run --extra agent mini agent stop EVENT_ID
uv run --extra agent mini agent uninstall
```

The default state directory is `~/Library/Application Support/UQ minis/agent`. It holds the browser profile, matching mail, form snapshots and any Graph tokens. Keep it private. The macOS user launch agent resumes after login and while the Mac is awake. Sleeping, offline, or powered-off Macs do not process mail, but saved events remain for the next poll.

Before sending, the worker records its draft identity and send intent. Graph reconciles using the immutable message ID. The browser checks Sent Items for a reply to the original request with the exact recipient, subject, body and attachment bytes. It never infers delivery from a missing draft. A crash during browser preparation can leave an unsent draft in Outlook; the worker does not send that draft later.

If send status is uncertain, it waits and notifies you. Check Sent Items before an explicit retry:

```sh
uv run --extra agent mini agent retry-send EVENT_ID --confirm-not-sent
```

Uncertain sends are not retried automatically. A sent message can still fail delivery; the worker waits for the booking replies.
