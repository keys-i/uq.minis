// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { miniHref, requestedMini } from "../src/shared/route.ts";

afterEach(() => {
  history.replaceState(null, "", "/");
  vi.unstubAllEnvs();
});

test.each(["/", "/mini/"])("builds canonical mini links with base %s", (base) => {
  vi.stubEnv("BASE_URL", base);
  expect(miniHref("planny")).toBe("/mini/planny");
  expect(miniHref("agent")).toBe("/mini/agent");
  expect(miniHref("home")).toBe(base);
});

test.each(["buzzy", "agent"])("reads the direct %s path before legacy query routes", (name) => {
  vi.stubEnv("BASE_URL", "/");
  history.replaceState(null, "", `/mini/${name}?m=timey`);
  expect(requestedMini()).toBe(name);
});

test.each(["?m=timey", "?mini=scrappy"])("keeps the legacy %s route readable", (query) => {
  vi.stubEnv("BASE_URL", "/");
  history.replaceState(null, "", `/${query}`);
  expect(requestedMini()).toBe(query.endsWith("timey") ? "timey" : "scrappy");
});

test("replaces a legacy query route with its canonical path once", () => {
  vi.stubEnv("BASE_URL", "/");
  history.replaceState(null, "", "/?m=timey&theme=dark#preview");
  const replace = vi.spyOn(history, "replaceState");
  expect(requestedMini()).toBe("timey");
  expect(replace).toHaveBeenCalledOnce();
  expect(`${location.pathname}${location.search}${location.hash}`).toBe(
    "/mini/timey?theme=dark#preview",
  );
  replace.mockRestore();
});
