from unittest.mock import AsyncMock, Mock

import pytest
from playwright import async_api

from uq_minis.core.window import Window, window


@pytest.mark.anyio
async def test_revision_retries_navigation_and_reads_allowed_frames() -> None:
    page = Mock(url="https://example.test/sign-in")
    page.is_closed = Mock(return_value=False)
    page.evaluate = AsyncMock(
        side_effect=[async_api.Error("Execution context was destroyed"), "main"]
    )
    frame = Mock(url="https://example.test/challenge")
    frame.evaluate = AsyncMock(return_value="frame")
    blocked = Mock(url="https://outside.test/")
    blocked.evaluate = AsyncMock()
    page.frames = [page, frame, blocked]
    page.context = Mock(pages=[page])

    revision = await Window(
        page, lambda url: url.startswith("https://example.test/"), "Test"
    ).revision()

    assert len(revision) == 64
    assert page.evaluate.await_count == 2
    frame.evaluate.assert_awaited_once()
    blocked.evaluate.assert_not_awaited()


@pytest.mark.anyio
async def test_window_ignores_a_disconnected_browser_during_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = Mock(url="https://example.test/")
    page.goto = AsyncMock()
    context = Mock()
    context.route = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    browser = Mock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock(side_effect=async_api.Error("Connection closed"))
    playwright = Mock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = AsyncMock()
    manager.__aenter__.return_value = playwright
    manager.__aexit__.return_value = False
    monkeypatch.setattr(async_api, "async_playwright", Mock(return_value=manager))

    async with window("https://example.test/", lambda _url: True, "Test") as opened:
        assert opened.page is page

    browser.new_context.assert_awaited_once_with(
        service_workers="block",
        accept_downloads=False,
        viewport={"width": 760, "height": 480},
        device_scale_factor=2,
    )
    browser.close.assert_awaited_once()
