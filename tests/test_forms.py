from __future__ import annotations

import json
from pathlib import Path

import pytest

from uq_minis.helper.common import MiniError, read_toml
from uq_minis.helper.forms import create_payload, load_form_profile
from uq_minis.helper.risk_docx import load_event_config


def answer_map(payload: dict[str, object]) -> dict[str, str | None]:
    answers = json.loads(str(payload["answers"]))
    return {entry["questionId"]: entry["answer1"] for entry in answers}


def test_builds_exact_ordered_form_payload(event_toml: Path) -> None:
    raw = read_toml(event_toml)
    payload = create_payload(raw, load_event_config(event_toml), load_form_profile())
    answers = json.loads(payload["answers"])
    mapped = answer_map(payload)

    assert len(answers) == 34
    assert payload["startDate"] == "2026-09-04T02:31:00.471Z"
    assert payload["submitDate"] == "2026-09-04T02:41:24.046Z"
    assert mapped["r269b9fb3ee6b4200aca94638bffdc547"] == "Sample Event"
    assert mapped["rdbe4e31ee21b4b9fbcc76f0fc37275de"] == "2026-09-15"
    assert mapped["r3577a1357f1b43e2b02b74973dbfbe63"] == "A small indoor club event."
    assert mapped["r8c601fac8a5349dcb71efd9e3727d0df"] == "Pizza + drinks"
    assert mapped["rcdf4b49320c24f5b8e85f2c39a0607de"] is None
    assert not any("cookie" in key.casefold() for key in payload)


def test_missing_named_form_value_is_rejected(event_toml: Path) -> None:
    event_toml.write_text(event_toml.read_text().replace('terms = "Agree"\n', ""))
    with pytest.raises(MiniError, match=r"Missing \[form.values\] keys: terms"):
        create_payload(read_toml(event_toml), load_event_config(event_toml), load_form_profile())


def test_custom_profile_cannot_leave_microsoft_forms(event_toml: Path, tmp_path: Path) -> None:
    profile = tmp_path / "profile.toml"
    profile.write_text(
        """
[request]
endpoint = "https://example.com/responses"
referer = "https://forms.cloud.microsoft/page"

[auth]

[[answers]]
question_id = "one"
value = "x"
""".strip()
        + "\n"
    )
    with pytest.raises(MiniError, match="forms.cloud.microsoft"):
        load_form_profile(profile)


def test_submit_reads_dotenv_without_overriding_environment(tmp_path, monkeypatch):
    import httpx

    from uq_minis.helper import forms

    monkeypatch.chdir(tmp_path)
    for name in (
        "UQ_FORMS_COOKIE",
        "UQ_FORMS_VERIFICATION_TOKEN",
        "UQ_FORMS_SESSION_ID",
        "UQ_FORMS_MUID",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "UQ_FORMS_COOKIE='example=${UNCHANGED}'\nUQ_FORMS_VERIFICATION_TOKEN='file-token'\n"
        "UQ_FORMS_SESSION_ID='session'\nUQ_FORMS_MUID='muid'\n"
    )
    monkeypatch.setenv("UQ_FORMS_VERIFICATION_TOKEN", "environment-token")
    client_type = httpx.Client
    options = {}

    def respond(request):
        assert request.url.host == "forms.cloud.microsoft"
        assert request.headers["cookie"] == "example=${UNCHANGED}"
        assert request.headers["__requestverificationtoken"] == "environment-token"
        return httpx.Response(201)

    def client(**kwargs):
        options.update(kwargs)
        return client_type(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(forms.httpx, "Client", client)
    assert forms.submit_payload(load_form_profile(), {"answers": "[]"}) == 201
    assert options["follow_redirects"] is False and options["trust_env"] is False
