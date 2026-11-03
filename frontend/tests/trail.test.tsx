// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { Trail, TrailWorld, trailCameras, trailManifest } from "../src/wildlife/trail.tsx";

const names = ["scrappy", "planny", "buzzy", "clubby", "event", "timey"];
const tools = Object.fromEntries(
  names.map((name) => [name, { title: name[0].toUpperCase() + name.slice(1), about: name }]),
);

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

test("the expedition keeps its six stops and scenery layers in order", () => {
  vi.stubEnv("BASE_URL", "/");
  const { container } = render(
    <TrailWorld route="home">
      <Trail tools={tools} open={() => {}} />
    </TrailWorld>,
  );
  expect(trailManifest.map((stop) => stop.name)).toEqual(names);
  expect(trailCameras).toEqual({
    home: [0, 0, 1],
    planny: [-30, 6, 1.12],
    scrappy: [-18, -4, 1.15],
    buzzy: [-4, 7, 1.12],
    clubby: [10, 0, 1.14],
    event: [24, 5, 1.13],
    timey: [36, -10, 1.16],
  });
  expect(
    [...container.querySelectorAll(".trail-stop h2 a")].map((link) => link.getAttribute("href")),
  ).toEqual(names.map((name) => `/mini/${name}`));
  const layers = [...container.querySelectorAll("[data-trail-layer]")].map((layer) =>
    layer.getAttribute("data-trail-layer"),
  );
  expect(layers).toHaveLength(6);
  expect(new Set(layers).size).toBe(6);
  expect(container.querySelectorAll(".trail-habitat")).toHaveLength(6);
  expect(container.querySelectorAll(".trail-resident-loading")).toHaveLength(6);
});

test("modified trail links keep native browser navigation", () => {
  vi.stubEnv("BASE_URL", "/");
  const open = vi.fn(),
    { container } = render(
      <TrailWorld route="home">
        <Trail tools={tools} open={open} />
      </TrailWorld>,
    ),
    link = container.querySelector<HTMLAnchorElement>('.trail-stop a[href="/mini/planny"]')!;
  const navigation = vi.fn((event: MouseEvent) => {
    const handled = event.defaultPrevented;
    event.preventDefault();
    return handled;
  });
  document.addEventListener("click", navigation);
  try {
    for (const modifier of ["metaKey", "ctrlKey", "shiftKey", "altKey"]) {
      fireEvent.click(link, { [modifier]: true });
      expect(navigation).toHaveLastReturnedWith(false);
    }
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(link);
    expect(navigation).toHaveLastReturnedWith(true);
    expect(open).toHaveBeenCalledExactlyOnceWith("planny");
  } finally {
    document.removeEventListener("click", navigation);
  }
});

test("direct mini routes initialise at their final camera", () => {
  const { container } = render(
    <TrailWorld route="timey">
      <main />
    </TrailWorld>,
  );
  const world = container.querySelector(".expedition-world");
  expect(world).toHaveAttribute("data-camera", "timey");
  expect(container.querySelector<HTMLElement>(".trail-layer-sky")?.style.transform).toContain(
    "scale(1.160)",
  );
});
