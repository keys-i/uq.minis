from unittest.mock import AsyncMock, Mock

import pytest
from playwright import async_api

from uq_minis.core.window import window


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

    browser.close.assert_awaited_once()
