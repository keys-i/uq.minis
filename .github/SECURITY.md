# Security policy

## Report a vulnerability

Report vulnerabilities exclusively through [GitHub private vulnerability reporting](https://github.com/keys-i/uq.minis/security/advisories/new)
Private reporting is enabled for this repository; open its Security tab and choose **Report a vulnerability**
Keep exploit details in the private report rather than public issues, pull requests or discussions
Keep follow-up and disclosure coordination in the GitHub report

Include the following

- The affected version or commit, mini and browser/CLI workflow
- Reproduction steps using synthetic data, with expected and actual behaviour
- The likely impact and any relevant operating system or deployment details
- A small, redacted proof of concept if one is needed

Never send live tokens, passwords, session cookies, student marks or mailbox exports as evidence
If a credential has leaked, revoke or rotate it with its provider first; deleting its current source file does not invalidate it or remove it from Git history
The exposed token from the retired `agg-soc` prototype also requires revocation by its owner

## Fixes and disclosure

Fixes are developed against `main`
Include the installed release version or commit so a maintainer can identify affected code
There is no published long-term support period or guaranteed response time for older releases
Coordinate a disclosure date with the maintainer through the private GitHub report

## Local service boundary

`mini browser` binds to `127.0.0.1` and serves a local, single-user workspace
Host/origin checks and browser security headers help protect that boundary; they are not multi-user authentication
Don't expose this service through a public interface, reverse proxy or tunnel without adding an appropriate authenticated hosting design
Other processes or people with access to your operating-system account can read its local files

Marks, enrolments, credentials, browser sessions and mailbox state live under the owning mini's `.minis/` directory by default
Private file permissions are used where supported; this is not encryption at rest
Editable plan backups, ICS calendars, exported club data and generated event documents can also contain personal information
Choose their destinations deliberately and don't attach them to public issues without redaction

Browser and CLI workflows can access authorised external services and perform event or mail actions
Run only workflows and inputs you understand, and review recipients, documents and submission details before sending
Saved website content and social imports are untrusted data, not instructions to run commands or expand account access

## External accounts and dependencies

Use authorised Discord bots and social account access with the minimum permissions needed for the workflow
Keep tokens in private backend state or the backend process environment, never in React source or browser form fields
See [source connection guidance](../docs/sources.md) and [mail watcher setup](../docs/agent.md) for current access limits
Do not bypass an upstream sign-in requirement or a course-profile access denial

Dependency locks live in `backend/uv.lock` and `frontend/package-lock.json`
Repository workflows include dependency review, Python source/dependency scanning and CodeQL
These checks reduce known risks; they are not a guarantee that a dependency or workflow is secure
Contributors should include a focused regression check for a security fix and keep exploit details out of public fixtures until disclosure is agreed
