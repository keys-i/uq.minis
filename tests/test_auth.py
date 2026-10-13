from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest
from dotenv import dotenv_values
from typer.testing import CliRunner

from tests import fakes
from tests.fixtures import Screen
from uq_minis import cli
from uq_minis.cli import auth as command
from uq_minis.core.common import MiniError
from uq_minis.core.forms import FormProfile
from uq_minis.minis import auth
from uq_minis.minis.auth import browser as capture
from uq_minis.minis.auth.credentials import write_env


class TestAuth:
    @pytest.mark.parametrize(
        "path,method,action,captured",
        [
            ("tenant/forms('form')/responses", "POST", call.abort(), True),
            ("tenant/forms('form')/questions", "GET", call.continue_(), True),
            ("other/responses", "POST", call.abort(), False),
        ],
        ids=["submission", "read", "foreign-form"],
    )
    def test_capture(
        self, profile: FormProfile, path: str, method: str, action: Any, captured: bool
    ) -> None:
        values: dict[str, Any] = {}
        headers = {
            "__requestverificationtoken": "token",
            "x-usersessionid": "session",
            "x-ms-form-muid": "muid",
        }
        route = Mock(
            request=SimpleNamespace(
                url=f"https://forms.cloud.microsoft/formapi/api/{path}",
                method=method,
                all_headers=lambda: headers,
            )
        )
        capture._guard(route, profile, values)
        assert route.method_calls == [action]
        assert values == (
            {"TOKEN": "token", "SESSION": "session", "MUID": "muid"} if captured else {}
        )

    @pytest.mark.parametrize(
        "name,value,expected",
        [
            ("__requestverificationtoken", "token", ""),
            ("AADAuth.forms", "auth", "AADAuth.forms=auth"),
        ],
        ids=["csrf-cookie", "authentication-cookie"],
    )
    def test_cookie(self, name: str, value: str, expected: str) -> None:
        cookie = {"name": name, "value": value, "domain": ".forms.cloud.microsoft"}
        assert capture._cookie_header([cookie]) == expected

    def test_private(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        write_env(path, {"TOKEN": "secret"}, force=False)
        assert "TOKEN='secret'" in path.read_text()
        if os.name == "posix":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        with pytest.raises(MiniError, match="Refusing"):
            write_env(path, {"TOKEN": "replacement"}, force=False)

    def test_dependency(self, monkeypatch: pytest.MonkeyPatch, profile: FormProfile) -> None:
        import sys

        monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
        with pytest.raises(MiniError, match="uv run --extra auth playwright install chromium"):
            capture.capture(profile, browser="chromium", timeout=1)

    def test_refresh(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("KEEP='yes'\nTOKEN='old'\n")
        write_env(path, {"TOKEN": "new'quoted"}, force=True)
        assert dotenv_values(path) == {"KEEP": "yes", "TOKEN": "new'quoted"}
        with pytest.raises(MiniError, match="control"):
            write_env(path, {"TOKEN": "bad\nvalue"}, force=True)
        assert dotenv_values(path) == {"KEEP": "yes", "TOKEN": "new'quoted"}

    @pytest.mark.parametrize(
        "url",
        [
            "http://forms.cloud.microsoft/formapi/api/tenant/forms('form')/questions",
            "https://forms.cloud.microsoft.evil.test/formapi/api/tenant/forms('form')/questions",
            "https://user@forms.cloud.microsoft/formapi/api/tenant/forms('form')/questions",
            "https://forms.cloud.microsoft:444/formapi/api/tenant/forms('form')/questions",
            "https://forms.cloud.microsoft/formapi/api/tenant/forms('other')/questions",
        ],
        ids=["http", "host", "userinfo", "port", "form"],
    )
    def test_origin(self, profile: FormProfile, url: str) -> None:
        request = Mock(url=url, method="GET")
        route = Mock(request=request)
        values: dict[str, Any] = {}
        capture._guard(route, profile, values)
        assert not values
        request.all_headers.assert_not_called()
        route.continue_.assert_called_once()


class TestCapture:
    @pytest.mark.parametrize(
        "name,engine,channel",
        [
            ("chromium", "chromium", None),
            ("firefox", "firefox", None),
            ("webkit", "webkit", None),
            ("chrome", "chromium", "chrome"),
            ("edge", "chromium", "msedge"),
        ],
        ids=["chromium", "firefox", "webkit", "chrome", "edge"],
    )
    def test_browser(
        self, browser: SimpleNamespace, name: str, engine: str, channel: None | str
    ) -> None:
        assert capture._launch(browser.runtime, name) is browser.instance
        options = {"headless": False, **({"channel": channel} if channel else {})}
        getattr(browser.runtime, engine).launch.assert_called_once_with(**options)

    @pytest.mark.parametrize("missing", [None, "headers", "cookie"])
    def test_session(
        self,
        browser: SimpleNamespace,
        profile: FormProfile,
        monkeypatch: pytest.MonkeyPatch,
        missing: None | str,
    ) -> None:
        headers = {
            "__requestverificationtoken": "token",
            "x-usersessionid": "session",
            "x-ms-form-muid": "muid",
        }
        route = Mock(
            request=SimpleNamespace(
                url=profile.endpoint,
                method="POST",
                all_headers=lambda: headers,
            )
        )

        def load(*args: Any, **kwargs: Any):
            if missing != "headers":
                browser.context.route.call_args.args[1](route)

        browser.page.goto.side_effect = load
        if missing == "cookie":
            browser.context.cookies.return_value = []
        monkeypatch.setattr(time, "monotonic", Mock(side_effect=[0, 0, 2]))
        if missing:
            with pytest.raises(MiniError, match="Timed out"):
                capture.capture(profile, browser="chromium", timeout=1)
            browser.page.wait_for_timeout.assert_called_once_with(250)
        else:
            values = capture.capture(profile, browser="chromium", timeout=1)
            assert values == {
                "COOKIE": "AADAuth.forms=signed-in",
                "TOKEN": "token",
                "SESSION": "session",
                "MUID": "muid",
            }
            route.abort.assert_called_once()
            browser.page.wait_for_timeout.assert_not_called()
        browser.instance.new_context.assert_called_once_with(service_workers="block")
        browser.context.close.assert_called_once()
        browser.instance.close.assert_called_once()

    def test_failure(self, browser: SimpleNamespace, profile: FormProfile) -> None:
        browser.runtime.chromium.launch.side_effect = fakes.BrowserError("not installed")
        with pytest.raises(MiniError, match="Could not start chromium"):
            capture.capture(profile, browser="chromium", timeout=1)


class TestCommand:
    @pytest.mark.parametrize("live", [False, True], ids=["plain", "terminal"])
    @pytest.mark.parametrize("force", [False, True], ids=["new", "refresh"])
    def test_save(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        screen: Screen,
        live: bool,
        force: bool,
    ) -> None:
        console, output = screen(live=live)
        monkeypatch.setattr(command, "CONSOLE", console)
        captured = Mock(return_value={"TOKEN": "private-token"})
        monkeypatch.setattr(auth, "capture", captured)
        target = tmp_path / "private.env"
        if force:
            target.write_text("KEEP='yes'\nTOKEN='old'\n")
        result = runner.invoke(
            cli.app,
            [
                "auth",
                "-o",
                str(target),
                "--browser",
                "edge",
                "--timeout",
                "9",
                *(["--force"] if force else []),
            ],
        )
        assert result.exit_code == 0, result.output
        assert dotenv_values(target) == {
            **({"KEEP": "yes"} if force else {}),
            "TOKEN": "private-token",
        }
        assert captured.call_args.kwargs == {"browser": "edge", "timeout": 9}
        assert "private-token" not in result.output + output.getvalue()

    @pytest.mark.parametrize("reason", ["unattended", "exists", "symlink"])
    def test_refuse(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner, reason: str
    ) -> None:
        target = tmp_path / "private.env"
        target.write_text("TOKEN='keep'\n")
        output = tmp_path / "linked.env" if reason == "symlink" else target
        if reason == "symlink":
            output.symlink_to(target)
        captured = Mock()
        monkeypatch.setattr(auth, "capture", captured)
        result = runner.invoke(
            cli.app,
            [
                "auth",
                "-o",
                str(output),
                *(["--no-input"] if reason == "unattended" else []),
            ],
        )
        assert result.exit_code == 2 and "Traceback" not in result.output
        assert target.read_text() == "TOKEN='keep'\n"
        captured.assert_not_called()

    @pytest.mark.parametrize("error", [MiniError, OSError, ValueError], ids=["auth", "io", "value"])
    def test_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        error: type[Exception],
    ) -> None:
        target = tmp_path / "private.env"
        monkeypatch.setattr(auth, "capture", Mock(side_effect=error("sign-in failed")))
        result = runner.invoke(cli.app, ["auth", "-o", str(target)])
        assert result.exit_code == 2
        assert "› sign-in failed" in result.output and "Traceback" not in result.output
        assert not target.exists()
