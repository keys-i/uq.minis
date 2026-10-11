"""Mail data and stateful test doubles"""

from copy import deepcopy
from email.message import EmailMessage
from types import SimpleNamespace

from uq_minis.worker import mail


class BrowserError(Exception):
    """A browser failure without requiring the optional Playwright package"""


def compose(filename="form.docx", *, ready=True, hidden=False):
    """Local compose controls with resolved recipients and file uploads"""
    recipient = mail.RETURN_TO if ready else mail.REQUEST_SENDER
    pickers = "".join(
        '<div class="ms-BasePicker-text">'
        + (
            f'<span class="ms-PickerItem-root" data-email="{recipient}">{recipient}</span>'
            if name == "To"
            else ""
        )
        + f'<input aria-label="{name}" onkeydown="recipients(event)"></div>'
        for name in ("To", "Cc", "Bcc")
    )
    return f"""<button onclick="document.querySelector('#compose').hidden=false">Reply</button>
    <div id="compose" {"" if ready else "hidden"}>
      <input id="subject" aria-label="Subject" value="{"UQU Risk Assessment Return Ref ID: 42" if ready else "Re: request"}" {"hidden" if hidden else ""}>
      <button onclick="document.querySelector('#edit').hidden=false">Reply options</button>
      <button id="edit" role="menuitem" hidden onclick="document.querySelector('#subject').hidden=false">Edit subject</button>
      {pickers}
      <div role="textbox" contenteditable="true" aria-label="Message body" style="white-space:pre-wrap">{mail.BODY if ready else ""}</div>
      <button onclick="document.querySelector('#browse').hidden=false">Attach file</button>
      <button id="browse" role="menuitem" hidden onclick="document.querySelector('#upload').click()">Browse this computer</button>
      <input id="upload" type="file" hidden onchange="attached(this)">
      <div id="attachments">{'<button aria-label="Remove ' + filename + ' attachment">Remove attachment</button>' if ready else ""}</div>
      <button onclick="window.sends++; document.querySelector('#notice').hidden=false">Send</button>
      <div id="notice" hidden>Message sent</div>
    </div>
    <script>
      window.sends = 0;
      function recipients(event) {{
        const input = event.target, picker = input.parentElement;
        if (event.key === 'Backspace') picker.querySelectorAll('.ms-PickerItem-root').forEach(chip => chip.remove());
        if (event.key === 'Enter' && input.value) {{
          const chip = document.createElement('span');
          chip.className = 'ms-PickerItem-root';
          chip.dataset.email = chip.textContent = input.value;
          picker.prepend(chip);
          input.value = '';
        }}
      }}
      function attached(input) {{
        const button = document.createElement('button');
        button.setAttribute('aria-label', 'Remove ' + input.files[0].name + ' attachment');
        button.textContent = 'Remove attachment';
        document.querySelector('#attachments').append(button);
      }}
    </script>"""


def message(
    identity,
    sender=mail.REQUEST_SENDER,
    *,
    request=False,
    event_id="42",
    title="Sample Event",
    thread="update",
    timestamp="2026-09-07T12:01:00Z",
    content=None,
):
    subject = f"Event Application Update{' Risk Assessment Request' if request else ''}  [Event ID: {event_id}] - {title}"
    result = {
        "id": identity,
        "from": {"emailAddress": {"address": sender}},
        "subject": subject,
        "conversationId": thread,
        "receivedDateTime": timestamp,
    }
    if content is not None:
        result.update(
            uniqueBody={"contentType": "text", "content": content},
            webLink="https://outlook.office.com/mail/test",
        )
    return result


class Mailbox:
    def __init__(self):
        self.incoming = []
        self.drafts = {}
        self.created = 0
        self.sent = 0
        self.attachments = []
        self.fail_send = None
        self.client = SimpleNamespace(close=lambda: None)

    def messages(self, since):
        return self.incoming

    def create_reply(self, request_id):
        self.created += 1
        identity = f"draft-{self.created}"
        self.drafts[identity] = {"id": identity, "isDraft": True}
        return identity

    def message(self, identity):
        return deepcopy(
            self.drafts.get(identity)
            or next(item for item in self.incoming if item["id"] == identity)
        )

    def prepare(self, identity, event_id, filename, document):
        self.attachments.append((filename, document))
        self.drafts[identity].update(
            subject=f"UQU Risk Assessment Return Ref ID: {event_id}",
            toRecipients=[{"emailAddress": {"address": mail.RETURN_TO}}],
            ccRecipients=[],
            bccRecipients=[],
        )

    def send(self, identity):
        self.sent += 1
        self.drafts[identity].update(isDraft=False, sentDateTime="2026-09-07T12:00:00Z")
        if self.fail_send:
            raise self.fail_send


def eml(*, message_id: str, sender: str, subject: str, body: str, to: str = "") -> bytes:
    message = EmailMessage()
    message["Message-ID"] = message_id
    message["From"] = sender
    if to:
        message["To"] = to
    message["Subject"] = subject
    message["Date"] = "Mon, 07 Sep 2026 12:00:00 +0000"
    message["Received"] = "from mail.example by outlook.example; Mon, 07 Sep 2026 12:01:00 +0000"
    message["References"] = "<request@example> <update@example>"
    message["In-Reply-To"] = "<update@example>"
    message.set_content(body)
    return message.as_bytes()


def request() -> dict:
    return {
        "id": "<request@example>",
        "from": {"emailAddress": {"address": mail.REQUEST_SENDER}},
        "subject": "Event Application Update Risk Assessment Request  [Event ID: 42] - Sample Event",
        "conversationId": "request-thread",
        "receivedDateTime": "2026-09-07T11:00:00+00:00",
        "webLink": "https://outlook.office.com/mail/id/request",
    }


def sent(document: bytes, *, body: str = mail.BODY) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = "<sent@example>"
    message["From"] = "rad@example.org"
    message["To"] = mail.RETURN_TO
    message["Subject"] = "UQU Risk Assessment Return Ref ID: 42"
    message["In-Reply-To"] = "<request@example>"
    message["References"] = "<request@example>"
    message["Date"] = "Mon, 07 Sep 2026 12:00:00 +0000"
    message.set_content(body)
    message.add_attachment(
        document, maintype="application", subtype="octet-stream", filename="form.docx"
    )
    return message.as_bytes()
