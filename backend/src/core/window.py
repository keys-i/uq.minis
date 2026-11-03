"""Relay bounded provider pixels and semantic controls in an isolated browser

Callers own the exact HTTPS allowlist and any identity verification
The transport never reads input values, saves passwords or permits downloads
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from uq_minis.core.common import MiniError

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page, Route


class Window:
    """Own the live page and its bounded, accessible control references"""

    def __init__(
        self,
        page: Page,
        allowed: Callable[[str], bool],
        label: str,
        form_host: str = "",
    ) -> None:
        """Start without retained screenshots or credential values"""
        self.page = page
        self.allowed = allowed
        self.label = label
        self.form_host = form_host
        self.controls: dict[str, tuple[Locator, str]] = {}

    async def _active(self) -> Page:
        """Select the provider's active allowed page"""
        pages = [page for page in self.page.context.pages if not page.is_closed()]
        if not pages or len(pages) > 4:
            raise MiniError("The sign-in window closed; try signing in again")
        self.page = pages[-1]
        if not self.allowed(self.page.url):
            raise MiniError("The provider opened an unsupported sign-in page; cancel and try again")
        return self.page

    async def revision(self) -> str:
        """Describe meaningful visible state without capturing provider pixels"""
        from playwright.async_api import Error

        failure: Error | None = None
        for _attempt in range(5):
            page = await self._active()
            try:
                snapshots = [
                    cast(
                        str,
                        await frame.evaluate("""() => JSON.stringify([
                          location.href, document.title, scrollX, scrollY, innerWidth,
                          innerHeight, (document.body?.innerText || '').slice(0, 4096),
                          [...document.querySelectorAll(
                            'h1,h2,[role=alert],input,textarea,select,button,a[href],img,canvas,svg'
                          )].filter(el => {
                            const r = el.getBoundingClientRect(), s = getComputedStyle(el);
                            return r.width > 0 && r.height > 0 && r.bottom > 0
                              && r.top < innerHeight && s.visibility !== 'hidden'
                              && s.display !== 'none';
                          }).slice(0, 64).map(el => {
                            const r = el.getBoundingClientRect();
                            return [el.tagName, el.type || '',
                              el.getAttribute('aria-label') || el.alt || el.title
                                || el.placeholder || el.innerText || '', !!el.disabled,
                              !!el.checked, Math.round(r.x), Math.round(r.y),
                              Math.round(r.width), Math.round(r.height),
                              el.tagName === 'IMG' ? el.currentSrc : ''];
                          })
                        ])"""),
                    )
                    for frame in page.frames[:8]
                    if self.allowed(frame.url)
                ]
                return sha256("\0".join(snapshots).encode()).hexdigest()
            except Error as exc:
                if page.is_closed():
                    raise MiniError("The sign-in window closed; try signing in again") from exc
                failure = exc
                await asyncio.sleep(0.05)
        assert failure is not None
        raise failure

    async def view(self) -> dict[str, Any]:
        """Describe the provider form or relay its pixels without reading credential values"""
        await self._active()
        controls: list[dict[str, Any]] = []
        self.controls.clear()
        for frame in self.page.frames:
            if not self.allowed(frame.url):
                continue
            offset = {"x": 0.0, "y": 0.0}
            if frame != self.page.main_frame:
                box = await (await frame.frame_element()).bounding_box()
                if box is None:
                    continue
                offset = box
            items = cast(
                list[dict[str, Any]],
                await frame.evaluate("""() => [...document.querySelectorAll(
                  'input:not([type=hidden]), textarea, select, button, a[href], [role=button]'
                )].filter(el => {
                  const r = el.getBoundingClientRect(), s = getComputedStyle(el);
                  return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight
                    && s.visibility !== 'hidden' && s.display !== 'none';
                }).slice(0, 64).map(el => {
                  const r = el.getBoundingClientRect();
                  const form = document.querySelector('input[type=password]')?.form;
                  el.dataset.minisControl ||= crypto.randomUUID();
                  const type = el.tagName === 'SELECT' ? 'select'
                    : el.tagName === 'TEXTAREA' ? 'text'
                    : el.tagName === 'INPUT' ? el.type : 'button';
                  return { id: el.dataset.minisControl, type, form: !!form?.contains(el),
                    label: (el.getAttribute('aria-label') || el.labels?.[0]?.innerText
                      || el.title || el.placeholder || (['submit', 'button'].includes(type)
                        ? el.value || el.innerText : el.name) || 'Sign-in control').slice(0, 200),
                    x: r.x, y: r.y, width: r.width, height: r.height,
                    disabled: !!el.disabled, checked: !!el.checked,
                    options: type === 'select' ? [...el.options].slice(0, 64).map(o => ({
                      value: o.value, label: o.text, selected: o.selected })) : [] };
                })"""),
            )
            for item in items:
                if len(controls) >= 64 or item["type"] in {"file", "image"}:
                    continue
                item["x"] += offset["x"]
                item["y"] += offset["y"]
                self.controls[item["id"]] = (
                    frame.locator(f'[data-minis-control="{item["id"]}"]'),
                    item["type"],
                )
                controls.append(item)
        size = self.page.viewport_size or {"width": 760, "height": 480}
        fields = {item["type"] for item in controls if item["form"]}
        form = (
            urlsplit(self.page.url).hostname == self.form_host
            and {"password", "submit"} <= fields
            and bool(fields & {"text", "email"})
        )
        if form:
            controls = [item for item in controls if item["form"]]
        for item in controls:
            item.pop("form", None)
        return {
            "mode": "form" if form else "window",
            "image": ""
            if form
            else base64.b64encode(await self.page.screenshot(type="png", timeout=5000)).decode(),
            "host": urlsplit(self.page.url).hostname,
            "title": (await self.page.title())[:200],
            "text": "\n".join(
                await self.page.locator(
                    "[role=alert],.alert-box,.error"
                    if form
                    else "h1,h2,[role=alert],.alert-box,.error"
                ).all_inner_texts()
            )[:1600],
            "controls": controls,
            **size,
        }

    async def act(self, event: dict[str, Any]) -> None:
        """Forward bounded input only to controls supplied by the current provider page"""
        kind = event.get("kind")
        if kind == "submit":
            fields, target = event.get("fields"), event.get("id")
            if (
                urlsplit(self.page.url).hostname != self.form_host
                or not self.allowed(self.page.url)
                or not isinstance(fields, dict)
                or not isinstance(target, str)
                or target not in self.controls
                or self.controls[target][1] != "submit"
            ):
                raise MiniError("Invalid sign-in form")
            fields = cast(dict[str, Any], fields)
            if not 1 <= len(fields) <= 8:
                raise MiniError("Invalid sign-in form")
            for key, value in fields.items():
                if (
                    key not in self.controls
                    or self.controls[key][1] not in {"text", "email", "password"}
                    or not isinstance(value, str)
                    or len(value) > 4096
                ):
                    raise MiniError("Invalid sign-in field")
            for key, value in fields.items():
                await self.controls[key][0].fill(value, timeout=2000)
            await self.controls[target][0].click(timeout=2000)
            return
        if kind == "resize":
            width, height = event.get("width"), event.get("height")
            if type(width) is not int or type(height) is not int:
                raise MiniError("Invalid sign-in window size")
            await self.page.set_viewport_size({
                "width": max(320, min(960, width)),
                "height": max(480, min(900, height)),
            })
            return
        if kind == "scroll":
            value = event.get("y")
            if type(value) is not int or not -900 <= value <= 900:
                raise MiniError("Invalid sign-in scroll")
            await self.page.mouse.wheel(0, value)
            return
        target = event.get("id")
        if not isinstance(target, str) or target not in self.controls:
            return
        control, field = self.controls[target]
        if not await control.count():
            return
        if kind == "click":
            await control.click(timeout=2000)
        elif kind == "enter":
            await control.press("Enter", timeout=2000)
        elif kind == "fill" and field not in {
            "button",
            "submit",
            "checkbox",
            "radio",
            "select",
        }:
            value = event.get("value")
            if not isinstance(value, str) or len(value) > 4096:
                raise MiniError("The sign-in value is too long")
            await control.fill(value, timeout=2000)
        elif kind == "select" and field == "select":
            value = event.get("value")
            if not isinstance(value, str) or len(value) > 1024:
                raise MiniError("Invalid sign-in choice")
            await control.select_option(value, timeout=2000)
        else:
            raise MiniError("Invalid sign-in control")


@asynccontextmanager
async def window(url: str, allowed: Callable[[str], bool], label: str) -> AsyncGenerator[Window]:
    """Own an isolated provider browser for one bounded account connection

    Yields:
        Portal window exposing original pixels and bounded semantic controls

    Raises:
        MiniError: Browser support is missing or the provider page cannot be opened

    Only the caller's fixed HTTPS allowlist can load
    Completion, cancellation and failure close the context without saving cookies
    """
    if not allowed(url):
        raise MiniError("The sign-in destination is not allowed")
    try:
        from anyio import CancelScope
        from playwright.async_api import Error, async_playwright
    except ImportError as exc:
        raise MiniError("Enable browser support to connect this account") from exc

    async def guard(route: Route) -> None:
        if allowed(route.request.url):
            await route.continue_()
        else:
            await route.abort()

    try:
        async with async_playwright() as playwright:
            instance = await playwright.chromium.launch(headless=True)
            try:
                context = await instance.new_context(
                    service_workers="block",
                    accept_downloads=False,
                    viewport={"width": 760, "height": 480},
                    device_scale_factor=2,
                )
                await context.route("**/*", guard)
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                yield Window(page, allowed, label)
            finally:
                with CancelScope(shield=True):
                    with suppress(Error):
                        await instance.close()
    except Error as exc:
        raise MiniError("The sign-in window lost its connection; cancel and try again") from exc
