from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from uq_minis.helper.common import MiniError
from uq_minis.helper.forms import FormProfile
from uq_minis.minis.auth.browser import _cookie_header, _guard, capture
from uq_minis.minis.auth.credentials import write_env


def _profile() -> FormProfile:
    return FormProfile(
        Path("profile.toml"),
        "https://forms.cloud.microsoft/formapi/api/tenant/forms('form')/responses",
        "https://forms.cloud.microsoft/pages/responsepage.aspx?id=form",
        "https://forms.cloud.microsoft",
        "business",
        "en-AU",
        False,
        (),
        "COOKIE",
        "TOKEN",
        "SESSION",
        "MUID",
    )


class Request:
    def __init__(self, url: str, method: str, headers: dict[str, str]) -> None:
        self.url, self.method, self.headers = url, method, headers

    def all_headers(self):
        return {key.casefold(): value for key, value in self.headers.items()}


class Route:
    def __init__(self, request: Request) -> None:
        self.request, self.action = request, ""

    def abort(self) -> None:
        self.action = "abort"

    def continue_(self) -> None:
        self.action = "continue"


def test_capture_is_scoped_and_blocks_only_response_post() -> None:
    profile, values = _profile(), {}
    guarded = Route(
        Request(
            profile.endpoint,
            "POST",
            {
                "__RequestVerificationToken": "token",
                "x-userSessionId": "session",
                "x-ms-form-muid": "muid",
            },
        )
    )
    _guard(guarded, profile, values)
    assert guarded.action == "abort"
    assert values == {"TOKEN": "token", "SESSION": "session", "MUID": "muid"}

    foreign = Route(
        Request(
            "https://forms.cloud.microsoft/formapi/api/other/responses",
            "POST",
            {"__RequestVerificationToken": "wrong"},
        )
    )
    _guard(foreign, profile, values)
    assert foreign.action == "abort"
    assert "wrong" not in values.values()


def test_cookie_requires_forms_auth_cookie() -> None:
    assert not _cookie_header(
        [
            {
                "name": "__requestverificationtoken",
                "value": "token",
                "domain": ".forms.cloud.microsoft",
            }
        ]
    )
    assert (
        _cookie_header(
            [
                {
                    "name": "AADAuth.forms",
                    "value": "auth",
                    "domain": ".forms.cloud.microsoft",
                }
            ]
        )
        == "AADAuth.forms=auth"
    )


def test_env_is_private_and_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    write_env(path, {"TOKEN": "secret"}, force=False)
    assert "TOKEN='secret'" in path.read_text()
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(MiniError, match="Refusing"):
        write_env(path, {"TOKEN": "replacement"}, force=False)


def test_missing_playwright_gives_runnable_setup_command(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(MiniError, match="uv run --extra auth playwright install chromium"):
        capture(_profile(), browser="chromium", timeout=1)


def test_auth_captures_get_headers_and_preserves_existing_env(tmp_path: Path) -> None:
    profile, values = _profile(), {}
    route = Route(
        Request(
            profile.endpoint.replace("/responses", "/questions"),
            "GET",
            {
                "__requestverificationtoken": "fresh",
                "x-usersessionid": "session",
                "x-ms-form-muid": "id",
            },
        )
    )
    _guard(route, profile, values)
    assert route.action == "continue" and values["TOKEN"] == "fresh"
    path = tmp_path / ".env"
    path.write_text("KEEP='yes'\nTOKEN='old'\n")
    write_env(path, {"TOKEN": "new'quoted"}, force=True)
    from dotenv import dotenv_values

    assert dotenv_values(path) == {"KEEP": "yes", "TOKEN": "new'quoted"}
    with pytest.raises(MiniError, match="control"):
        write_env(path, {"TOKEN": "bad\nvalue"}, force=True)
