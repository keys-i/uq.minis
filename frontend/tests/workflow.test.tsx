import { test } from "vitest";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { assessment, announcement, clip, course, plan, readiness } from "./fixtures.ts";
import type { Values } from "../src/timey/model.ts";
import { enrol, badges } from "../src/study/courses.ts";
import { calendarEvents, onDay } from "../src/study/dates.ts";
import { connected, layout } from "../src/study/trail.ts";
import {
  configuration,
  resume,
  seconds,
  video,
  transferred,
  placement,
  dock,
  move,
  resize,
  scale,
  clock,
  dial,
  phase,
  recoil,
  wind,
} from "../src/timey/model.ts";

test("selecting a course needs no live catalogue or profile and refuses duplicates", () => {
  const selected = plan();
  enrol(selected, {
    code: "CSSE2002",
    name: "Programming",
    readiness: readiness({ wording: "CSSE1001" }),
  });
  assert.equal(selected.courses[0].code, "CSSE2002");
  assert.equal(selected.courses[0].profile, "");
  assert.equal(selected.courses[0].verified, false);
  assert.throws(() => enrol(selected, { course_code: "CSSE2002" }), /already selected/);
  assert.equal(selected.courses.length, 1);
  assert.deepEqual(
    badges("Semester 1, 2026 / St Lucia / In Person / Semester 2, 2026 / St Lucia / In Person"),
    ["Sem 1 & 2", "St Lucia", "In Person"],
  );
});

test("timer manipulation stays inside landscape and portrait footage and resizing holds its corner", () => {
  for (const [width, height] of [
    [960, 540],
    [304, 540],
  ]) {
    const values = { position: "centre", size: "2.4" },
      box = placement(values, width, height);
    const moved = placement(
      { ...values, ...move(values, width, height, 100000, -100000) },
      width,
      height,
    );
    assert.equal(moved.left, width - moved.w - moved.margin);
    assert.equal(moved.top, moved.margin);
    const smaller = placement(
      { ...values, ...resize(values, width, height, -50, -20) },
      width,
      height,
    );
    assert.ok(smaller.w < box.w);
    assert.ok(Math.abs(smaller.left - box.left) <= 1);
    assert.ok(Math.abs(smaller.top - box.top) <= 1);
    const largest = placement(
      { ...values, ...resize(values, width, height, 100000, 100000) },
      width,
      height,
    );
    assert.ok(largest.left + largest.w <= width - largest.margin);
    assert.ok(largest.top + largest.h <= height - largest.margin);
    const smallest = resize(values, width, height, -100000, -100000);
    assert.equal(smallest.overlay_width, "0.05");
    assert.equal(smallest.overlay_height, "0.05");
  }
  assert.deepEqual(placement({ size: "2.4", position: "centre" }, 960, 540), {
    left: 156,
    top: 129,
    w: 648,
    h: 281,
    margin: 14,
    dx: 284,
    dy: 231,
    x: 0.5,
    y: 0.5,
  });
  assert.equal(clock(3723), "1:02:03");
});

test("Buzzy combines deadlines, personal targets and selected society events", () => {
  const selected = plan({
    settings: { buffer: 2, target: 75, following: ["club"] },
    assessments: [
      assessment({ id: "task", due: "2026-10-22T09:00:00Z", buffer: null, done: false }),
    ],
  });
  const feed = [
    { id: "followed", club_url: "club", start: "2026-10-23T08:00:00Z" },
    { id: "saved", saved: true, start: "2026-10-21T08:00:00Z" },
    { id: "other", start: "2026-10-21T08:00:00Z" },
    { id: "cancelled", saved: true, start: "2026-10-23T08:00:00Z", status: "cancelled" },
  ];
  const rows = calendarEvents(
    selected,
    feed.map((item) => announcement(item)),
  );
  assert.deepEqual(
    rows.map((row) => row.kind),
    ["personal", "club", "official", "club"],
  );
  assert.deepEqual(
    rows.filter((row) => row.kind === "club").map((row) => row.id),
    ["saved", "followed"],
  );
  assert.equal(selected.assessments[0].due, "2026-10-22T09:00:00Z");
  assert.equal(
    calendarEvents({ ...selected, settings: { ...selected.settings, buffer: 0 } }, []).length,
    1,
  );
  const overnight = { when: "2026-10-21T21:00:00Z", end: "2026-10-22T00:00:00Z" };
  assert.equal(onDay(overnight, new Date("2026-10-21T00:00:00Z")), true);
  assert.equal(onDay(overnight, new Date("2026-10-22T00:00:00Z")), false);
});

test("upgrading a cached section retains playback while seeking a new section starts at its requested frame", () => {
  const previous = { source: "video", time: 84 };
  assert.equal(resume(previous, clip({ source: "video", start: 0, complete: true }), 300, 80), 84);
  assert.equal(resume(previous, clip({ source: "video", start: 80, complete: false }), 10, 80), 4);
  assert.equal(resume(previous, clip({ source: "video", start: 50, complete: false }), 10, 50), 0);
  assert.equal(resume(previous, clip({ source: "other", start: 0, complete: true }), 300, 20), 20);
});

test("prerequisite paths handle shared branches and cycles without highlighting siblings", () => {
  const nodes = [
    { code: "A", name: "A", required: ["B", "C"], depth: 0 },
    { code: "B", name: "B", required: ["D"], depth: 1 },
    { code: "C", name: "C", required: ["D"], depth: 1 },
    { code: "D", name: "D", required: ["B"], depth: 2 },
  ];
  assert.deepEqual([...connected(nodes, "C")].sort(), ["A", "B", "C", "D"]);
  assert.deepEqual(
    [
      ...connected(
        [
          { code: "A", required: ["B", "C"] },
          { code: "B", required: [] },
          { code: "C", required: [] },
        ],
        "B",
      ),
    ].sort(),
    ["A", "B"],
  );
  const positions = layout(nodes);
  assert.equal(positions.points.size, 4);
  const first = positions.points.get("A"),
    last = positions.points.get("D");
  assert.ok(first && last);
  assert.ok(last.x < first.x);
});

test("YouTube links preserve start times and reject unrelated hosts", () => {
  assert.equal(seconds("1h 2m 3s"), 3723);
  assert.equal(seconds("1:23"), 83);
  assert.equal(seconds("1:75"), null);
  assert.equal(video("https://youtu.be/abcdefghijk?t=1m20s")?.start, 80);
  assert.equal(video("https://youtube.com.evil.test/watch?v=abcdefghijk"), null);
  assert.equal(video("javascript:alert(1)"), null);
});

import * as app from "../src/study/planner.tsx";
import * as eventPage from "../src/event.tsx";
import * as timer from "../src/timey/index.tsx";
import * as canvas from "../src/timey/canvas.tsx";
import * as timing from "../src/timey/dial.tsx";
import * as look from "../src/timey/look.tsx";
test("media transfers preserve one file or a link", () => {
  const file = new File(["image"], "garden.png", { type: "image/png" });
  const data = (files: File[] = [], text = ""): Pick<DataTransfer, "files" | "getData"> => ({
    files: Object.assign(files, { item: (index: number) => files[index] ?? null }),
    getData: () => text,
  });
  assert.equal(transferred(data([file])), file);
  assert.throws(() => transferred(data([file, file])), /one file/);
  const value = transferred(data([], "# A link\r\nhttps://youtu.be/abcdefghijk?t=1m20s"));
  assert.equal(typeof value, "string");
  const link = video(String(value));
  assert.ok(link);
  assert.equal(link.start, 80);
  assert.equal(link.url, "https://www.youtube.com/watch?v=abcdefghijk");
  assert.equal(
    transferred(data([], "https://example.org/image.png")),
    "https://example.org/image.png",
  );
});

test("Planny starts with course selection and keeps only assessment views", () => {
  const selected = plan();
  const render = () =>
    renderToStaticMarkup(
      React.createElement(app.Planner, {
        plan: selected,
        async change() {},
        modal() {},
        courses() {},
      }),
    );
  assert.match(render(), /Select courses in Scrappy/);
  selected.courses.push(course({ id: "c", code: "CSSE2002" }));
  const html = render();
  assert.match(html, /Assessments/);
  assert.match(html, /Timeline/);
  assert.match(html, /Marks/);
  assert.match(html, /Personal target/);
  assert.doesNotMatch(html, /enrolled-summary/);
  assert.doesNotMatch(
    html,
    /Nudgy|favour for future you|plot twist|bring in the published assessments/,
  );
  assert.doesNotMatch(html, /Weeky|Gantty|Buzzy|Clubby/);
});

test("Eventy keeps its UQ gate while Timey starts with Google in the preview", () => {
  const event = renderToStaticMarkup(React.createElement(eventPage.Eventy));
  assert.match(event, /Prepare event/);
  assert.match(event, /Booking &amp; replies/);
  const html = renderToStaticMarkup(React.createElement(timer.Timey));
  assert.match(html, /aria-label="Timer studio"/);
  assert.match(
    html,
    /timer-stage[^]*timer-google-gate[^]*timer-google-reveal[^]*timer-google-paper[^]*timer-google-panel[^]*Checking Google/,
  );
  assert.doesNotMatch(
    html,
    /timer-connect-step|aria-label="Background preview"|Search anything here/,
  );
  assert.doesNotMatch(html, /Opening your timer studio/);
  assert.doesNotMatch(html, /<iframe/);
});

test("Timey renders a local player and directly editable timer without an embedded player", () => {
  const html = renderToStaticMarkup(
    React.createElement(canvas.Canvas, {
      clip: clip({ url: "/download/cached", start: 80, duration: 300, width: 960, height: 540 }),
      image: "blob:panel",
      onError() {},
      values: { size: "2.4", position: "centre", label: "Focus" },
      change() {},
    }),
  );
  assert.match(html, /<video[^>]+src="\/download\/cached"/);
  for (const name of [
    "Move timer",
    "Resize top left",
    "Resize top right",
    "Resize bottom left",
    "Resize bottom right",
    "Timer colour",
    "Timer label",
    "Video position",
    "Play preview",
    "Forward 10 seconds",
    "Back 10 seconds",
  ])
    assert.ok(html.includes(`aria-label="${name}"`), name);
  assert.doesNotMatch(html, /Start backdrop here|Use this frame/);
  assert.equal((html.match(/class="timer-handle"/g) || []).length, 4);
  assert.doesNotMatch(html, /title="[^"]*[·•]/);
  assert.doesNotMatch(
    html,
    /Arrange timer|Timer size|timer-placement|data-placement|iframe|Your changes appear here/,
  );
});

test("video quality offers named choices and cache refresh", () => {
  const html = renderToStaticMarkup(
    React.createElement(timer.Quality, { values: { height: "0", fps: "30" }, change() {} }),
  );
  for (const label of [
    "Original",
    "Small file (480p)",
    "HD (720p)",
    "Full HD (1080p)",
    "Smooth (60 fps)",
    "Refresh footage",
  ])
    assert.ok(html.includes(label), label);
  assert.doesNotMatch(html, /type="number"|Maximum height|0 keeps/);
  const custom = renderToStaticMarkup(
    React.createElement(timer.Quality, { values: { height: "900", fps: "24" }, change() {} }),
  );
  assert.doesNotMatch(custom, /Height in pixels|Custom size|type="number"/);
});

test("Look unifies font search with named digit motion and an accessible loop fade", () => {
  const html = renderToStaticMarkup(
    React.createElement(look.Look, {
      values: {
        motion: "on",
        loop_blend: ".6",
        font: "https://fonts.google.com/specimen/Patrick+Hand",
      },
      change() {},
    }),
  );
  assert.match(html, /placeholder="Search any font…"/);
  assert.match(html, /Patrick Hand/);
  assert.match(html, /aria-label="Use theme font"/);
  assert.match(html, /aria-pressed="true"[^]*Rolling digits/);
  assert.match(html, /Simple countdown/);
  assert.match(
    html,
    /aria-label="Loop fade" aria-valuetext="0.6 second crossfade" min="0" max="2" step=".1"/,
  );
  assert.doesNotMatch(html, /type="number"|<select|Font file or|exact value/);
  const cut = renderToStaticMarkup(
    React.createElement(look.Look, { values: { motion: "off", loop_blend: "0" }, change() {} }),
  );
  assert.doesNotMatch(cut, /font-current|Theme font/);
  assert.match(cut, /aria-valuetext="Cut without fading"/);
  assert.match(cut, /aria-pressed="true"[^]*data-motion="off"/);
});

test("font search accepts trusted links and existing file paths without mistaking family names for files", () => {
  assert.equal(
    look.fontInput("  https://fonts.google.com/specimen/Patrick+Hand  "),
    "https://fonts.google.com/specimen/Patrick+Hand",
  );
  assert.equal(look.fontInput("Patrick Hand"), "");
  assert.equal(look.fontInput("rounded"), "");
  assert.equal(look.fontInput("/fonts/hand.ttf"), "/fonts/hand.ttf");
  assert.equal(look.fontInput("./hand.otf"), "./hand.otf");
  for (const source of [
    "http://fonts.google.com/specimen/Hand",
    "https://fonts.google.com.evil.test/Hand",
    "https://user@fonts.gstatic.com/a.ttf",
    "https://fonts.googleapis.com:444/css?family=Hand",
  ])
    assert.throws(() => look.fontInput(source), /HTTPS Google Fonts/);
  assert.equal(look.fontName(""), "Theme font");
  assert.equal(
    look.fontName("https://fonts.googleapis.com/css2?family=Baloo+2:wght@400"),
    "Baloo 2",
  );
  assert.equal(look.fontName("/fonts/hand.ttf"), "hand.ttf");
});

test("quality choices use compact dropdowns without duplicate headings", () => {
  const html = renderToStaticMarkup(
    React.createElement(timer.Quality, { values: { height: "1080" }, change() {} }),
  );
  assert.match(html, /Data saver \(360p\)/);
  assert.match(html, /Tiny file \(240p\)/);
  assert.equal([...html.matchAll(/data-compact="true"/g)].length, 2);
  assert.doesNotMatch(html, /picker-heading|popover-close/);
});

test("custom is a theme button with context settings and preserves its draft when another theme is selected", async () => {
  const { Themes } = await import("../src/timey/looks.tsx");
  const values = {
    style: "custom",
    instructions: "Leaves around a clock",
    custom_style: "",
    designer: "auto",
    metadata: "on",
  };
  const html = renderToStaticMarkup(
    React.createElement(Themes, { values, onDesign() {}, change() {} }),
  );
  assert.match(html, /aria-pressed="true" data-look="custom"[^>]*popoverTarget=/);
  assert.match(html, /role="dialog" aria-label="Custom artwork"/);
  assert.match(html, /What should it look like\?/);
  assert.doesNotMatch(html, /JSON path|Signed-in designer/);
  assert.doesNotMatch(html, /<details|<summary/);
  assert.equal(configuration(values).instructions, values.instructions);
  assert.equal(configuration(values).style, "minimal");
  assert.equal(configuration({ ...values, style: "glass" }).instructions, undefined);
  assert.equal(values.instructions, "Leaves around a clock");
  assert.equal(configuration(values, "sample").metadata, undefined);
});

test("publication controls retain draft notes without fixed audience or thumbnail choices", () => {
  const schema = {
    fields: [{ name: "metadata_instructions", label: "Writing notes", type: "textarea" }],
  };
  const render = (values: Values) =>
    renderToStaticMarkup(React.createElement(timer.Publication, { schema, values, change() {} }));
  assert.match(render({}), /Video details/);
  const html = render({ metadata: "on", metadata_instructions: "Friendly wording" });
  assert.match(html, /Writing notes/);
  assert.match(html, /Friendly wording/);
  assert.doesNotMatch(html, /Audience|synthetic|thumbnail|<details|<summary/);
});

test("timer placement uses a native visual popover with nine size-preserving destinations", () => {
  const html = renderToStaticMarkup(
    React.createElement(canvas.Canvas, {
      clip: clip({ kind: "image", url: "/download/garden", width: 960, height: 540 }),
      image: "blob:panel",
      onError() {},
      values: { x: ".5", y: ".5" },
      change() {},
    }),
  );
  assert.match(html, /aria-label="Align timer"[^>]*aria-haspopup="dialog"[^>]*popoverTarget=/);
  assert.match(html, /popover="auto" role="dialog" aria-label="Timer placement"/);
  const matched = html.match(/<section[^>]*class="timer-layout"[\s\S]*?<\/section>/);
  assert.ok(matched);
  const menu = matched[0];
  for (const name of [
    "Left",
    "Right",
    "Top",
    "Bottom",
    "Top left",
    "Top right",
    "Bottom left",
    "Bottom right",
    "Centre",
  ])
    assert.ok(menu.includes(`aria-label="${name}"`), name);
  assert.equal((menu.match(/aria-pressed="true"/g) || []).length, 1);
  assert.equal((menu.match(/align-[0-9.]+-[0-9.]+\.svg/g) || []).length, 9);
  const destinations = [...menu.matchAll(/data-x="([\d.]+)" data-y="([\d.]+)"/g)];
  assert.equal(destinations.length, 9);
  assert.equal(new Set(destinations.map(([, x, y]) => `${x},${y}`)).size, 9);
  const values = { overlay_width: ".3", overlay_height: ".2" },
    before = placement(values, 960, 540);
  for (const [, x, y] of destinations) {
    const after = placement({ ...values, x, y }, 960, 540);
    assert.equal(after.w, before.w);
    assert.equal(after.h, before.h);
    assert.equal(after.x, Number(x));
    assert.equal(after.y, Number(y));
  }
  assert.doesNotMatch(menu, /type="range"|type="color"|Full screen/);
});

test("search results show bounded thumbnails without downloading or embedding videos on arrival", () => {
  const rows = [
    { url: "https://www.youtube.com/watch?v=abcdefghijk", title: "Forest & rain", length: "10:00" },
    { url: "https://evil.test/watch?v=abcdefghijk", title: "No thumbnail", length: "0:10" },
  ];
  const html = renderToStaticMarkup(React.createElement(timer.VideoResults, { rows, choose() {} }));
  assert.match(html, /role="group" aria-label="Background videos"/);
  assert.match(html, /Forest &amp; rain/);
  assert.match(html, /https:\/\/i.ytimg.com\/vi\/abcdefghijk\/mqdefault.jpg/);
  assert.equal((html.match(/<img /g) || []).length, 1);
  assert.match(html, /width="320" height="180" loading="lazy" referrerPolicy="no-referrer"/);
  assert.doesNotMatch(html, /<video|<iframe|src="https:\/\/evil/);
});

test("loading feedback lives inside the preview without creating premature timer controls", () => {
  const html = renderToStaticMarkup(
    React.createElement(canvas.Canvas, {
      values: {},
      change() {},
      clip: null,
      image: "",
      onError() {},
      loading: true,
      status: "Finding videos…",
    }),
  );
  assert.match(html, /class="timer-canvas"[^>]*data-loading="true"/);
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /class="timer-status" role="status" aria-atomic="true"[^]*Finding videos…/);
  assert.doesNotMatch(html, /Move timer|Timer tools|Video playback|timer-stage-status/);
});

test("the empty preview has no timer or playback tools", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      canvas.Canvas,
      {
        clip: null,
        onError() {},
        image: "blob:old",
        values: { size: "2.4", position: "centre" },
        change() {},
      },
      React.createElement("input", { type: "file", "aria-label": "Upload video" }),
    ),
  );
  assert.match(html, /Upload video/);
  assert.doesNotMatch(html, /Move timer|Timer tools|Video tools|Video settings|Video playback/);
});

test("the timer toolbar owns look, colour and music without a separate video menu", () => {
  const html = renderToStaticMarkup(
    React.createElement(canvas.Canvas, {
      clip: clip({ url: "/download/cached" }),
      image: "blob:panel",
      onError() {},
      values: {},
      change() {},
      look: React.createElement("input", { "aria-label": "Font file" }),
    }),
  );
  assert.equal((html.match(/role="toolbar"/g) || []).length, 1);
  assert.doesNotMatch(html, /Video settings|Video tools|Close video tools|timer-scene/);
  const toolbar = html.slice(html.indexOf('aria-label="Timer tools"'), html.indexOf("<section"));
  for (const name of [
    "Timer label",
    "Fine-tune the look",
    "Timer colour",
    "Align timer",
    "Music &amp; sound",
  ])
    assert.ok(toolbar.includes(`aria-label="${name}"`), name);
  assert.match(
    toolbar,
    /aria-label="Fine-tune the look"[^>]*aria-controls="[^"]+-look"[^>]*popoverTarget="[^"]+-look"/,
  );
  const panels = [
    ...html.matchAll(/<section[^>]*class="timer-settings timer-controls"[\s\S]*?<\/section>/g),
  ].map((match) => match[0]);
  assert.equal(panels.length, 3);
  assert.ok(panels.every((panel) => panel.includes('popover="auto" role="dialog"')));
  assert.match(panels[0], /Fine-tune the look.*aria-label="Font file"/);
  assert.match(panels[1], /Music &amp; sound.*aria-label="Music volume"/);
  assert.doesNotMatch(panels[0], /Music volume/);
});

test("an image backdrop keeps the editable timer without video playback controls", () => {
  const html = renderToStaticMarkup(
    React.createElement(canvas.Canvas, {
      clip: clip({
        kind: "image",
        url: "/download/garden",
        title: "Garden",
        width: 720,
        height: 540,
      }),
      image: "blob:panel",
      onError() {},
      values: { size: "2.4", position: "centre" },
      change() {},
    }),
  );
  assert.match(html, /class="timer-picture"[^>]+src="\/download\/garden"/);
  assert.match(html, /Move timer/);
  assert.doesNotMatch(html, /<video|Video playback|Video position/);
});

test("dial timing follows pointer positions", () => {
  assert.equal(dial(0, -1), 0);
  assert.equal(dial(1, 0), 1800);
  assert.equal(dial(0, 1), 3600);
  assert.equal(dial(-1, 0), 5400);
  assert.equal(dial(1, 0, 86400), 21600);
  assert.equal(dial(0, -1, 60, true), 0);
  assert.equal(dial(1, 0, 60, true), 15);
  for (const value of [1, 15, 600, 86400]) {
    const html = renderToStaticMarkup(React.createElement(timing.Dial, { value, change() {} }));
    assert.match(html, new RegExp(`aria-valuenow="${value}"`));
  }
  for (const value of [0, 5, 3600]) {
    const html = renderToStaticMarkup(
      React.createElement(timing.Dial, { value, gap: true, label: "Get-ready time", change() {} }),
    );
    assert.match(html, new RegExp(`aria-valuenow="${value}"`));
    assert.match(html, /aria-label="Get-ready time"/);
  }
});

test("dial winding follows full turns without jumping backwards across the top", () => {
  assert.equal(phase(0, -1), 0);
  assert.equal(phase(1, 0), 0.25);
  assert.ok(Math.abs(wind(0.95, 0.02) - 1.02) < 1e-9);
  assert.ok(Math.abs(wind(1.98, 0.02) - 2.02) < 1e-9);
  assert.ok(Math.abs(wind(0.02, 0.98) + 0.02) < 1e-9);
  assert.ok(Math.abs(wind(1.05, 0.9) - 0.9) < 1e-9);
});

test("edge and corner resizing keep the opposite edges anchored", () => {
  const values = { size: "1", position: "centre" },
    before = placement(values, 960, 540);
  const edges: [string, number, number][] = [
    ["nw", -15, -15],
    ["n", 0, -15],
    ["ne", 15, -15],
    ["e", 15, 0],
    ["se", 15, 15],
    ["s", 0, 15],
    ["sw", -15, 15],
    ["w", -15, 0],
  ];
  for (const [edge, dx, dy] of edges) {
    const after = placement({ ...values, ...resize(values, 960, 540, dx, dy, edge) }, 960, 540);
    assert.equal(after.w > before.w, edge.includes("e") || edge.includes("w"), edge);
    assert.equal(after.h > before.h, edge.includes("n") || edge.includes("s"), edge);
    if (edge.includes("w"))
      assert.ok(Math.abs(after.left + after.w - before.left - before.w) <= 1, edge);
    if (edge.includes("e")) assert.ok(Math.abs(after.left - before.left) <= 1, edge);
    if (edge.includes("n"))
      assert.ok(Math.abs(after.top + after.h - before.top - before.h) <= 1, edge);
    if (edge.includes("s")) assert.ok(Math.abs(after.top - before.top) <= 1, edge);
  }
  const wide = { ...values, ...resize(values, 960, 540, 100, 0, "e") },
    resized = placement(wide, 960, 540);
  assert.equal(resized.h, before.h);
  assert.equal(resized.w, before.w + 100);
  const scaled = placement({ ...wide, ...scale(wide, 960, 540, 1.5) }, 960, 540);
  assert.ok(Math.abs(scaled.w / scaled.h - resized.w / resized.h) < 0.03);
  const capped = placement({ ...wide, ...scale(wide, 960, 540, 3) }, 960, 540);
  assert.ok(Math.abs(capped.w / capped.h - resized.w / resized.h) < 0.03);
  const tiny = scale({ size: "2.4", overlay_width: "0.05", overlay_height: "0.05" }, 304, 540, 2.4);
  assert.ok(Number(tiny.overlay_width) >= 0.05 && Number(tiny.overlay_height) >= 0.05);
});

test("edge snapping preserves dimensions and leaves the interior free", () => {
  for (const [width, height] of [
    [960, 540],
    [304, 540],
    [180, 100],
  ]) {
    const values = { size: "1.4", overlay_width: "0.4", overlay_height: "0.2", x: ".31", y: ".67" },
      before = placement(values, width, height);
    for (const [x, y] of [
      [0, 0],
      [0.5, 0],
      [1, 0],
      [0, 0.5],
      [1, 0.5],
      [0, 1],
      [0.5, 1],
      [1, 1],
    ]) {
      const patch = dock(width * x, height * y, width, height),
        box = placement({ ...values, ...patch }, width, height);
      assert.deepEqual(patch, { x: String(x), y: String(y) });
      assert.equal(box.w, before.w);
      assert.equal(box.h, before.h);
      assert.ok(box.left >= box.margin && box.left + box.w <= width - box.margin);
      assert.ok(box.top >= box.margin && box.top + box.h <= height - box.margin);
    }
    assert.equal(dock(width / 2, height / 2, width, height), null);
    assert.equal(dock(0, 0, width, height, true), null);
    assert.equal(dock(-1, 0, width, height), null);
    assert.equal(dock(width + 1, height, width, height), null);
    const patch = move(values, width, height, 0, 0);
    assert.equal(patch.x, "0.31");
    assert.equal(patch.y, "0.67");
    assert.equal("position" in patch, false);
  }
  assert.equal(dock(25, 200, 960, 540), null);
  assert.equal(dock(0, 0, 0, 0), null);
});

test("elastic return starts at the release point, recoils and settles", () => {
  for (const pull of [-0.1, 0.1]) {
    const frames = recoil(pull),
      rotation = frames.map((frame) => {
        const match = String(frame.transform).match(/rotate\(([-.\d]+)deg\)/);
        assert.ok(match);
        return Number(match[1]);
      });
    assert.equal(frames[0].offset, 0);
    assert.equal(rotation[0], pull * 360);
    assert.ok(rotation.some((angle) => Math.sign(angle) === -Math.sign(pull)));
    assert.equal(frames.at(-1)?.transform, "rotate(0deg) scale(1,1)");
    assert.equal(frames.at(-1)?.offset, 1);
  }
});

test("familiar timer looks have distinct symbols and accessible names", async () => {
  const { looks, Symbol } = await import("../src/timey/looks.tsx");
  const names = ["super-mario", "minions", "sonic", "pac-man"];
  const drawings = names.map((name) => renderToStaticMarkup(React.createElement(Symbol, { name })));
  assert.equal(new Set(drawings).size, names.length);
  for (const name of names) assert.ok(looks.some(([id, label]) => id === name && label.length));
  for (const drawing of drawings) {
    assert.match(drawing, /aria-hidden="true"/);
    assert.doesNotMatch(drawing, /<image|<script/);
  }
});

test("the floating timer toolbar also opens the existing music settings", () => {
  const html = renderToStaticMarkup(
    React.createElement(canvas.Canvas, {
      clip: clip({ url: "/download/video", width: 960, height: 540 }),
      image: "blob:panel",
      onError() {},
      values: {},
      change() {},
    }),
  );
  const toolbar = html.slice(html.indexOf('aria-label="Timer tools"'), html.indexOf("<section"));
  assert.match(toolbar, /aria-label="Music &amp; sound"[^>]*aria-controls="[^"]+-music"/);
  assert.equal((html.match(/role="dialog" aria-label="Music &amp; sound"/g) || []).length, 1);
});

test("colour wheel uses round-trip HSV, bounded pointer coordinates and editable controls", async () => {
  const { hsv, hex, wheel, Colour } = await import("../src/timey/colour.tsx");
  for (const value of ["#ff0000", "#00ff00", "#0000ff", "#ffffff", "#000000", "#e9edea", "#ed865f"])
    assert.equal(hex(hsv(value)), value);
  assert.deepEqual(wheel(0, -90, 90), [0, 1]);
  assert.deepEqual(wheel(180, 0, 90), [90, 1]);
  assert.deepEqual(wheel(0, 0, 90), [90, 0]);
  const html = renderToStaticMarkup(
    React.createElement(Colour, { value: "#e9edea", custom: false, change() {} }),
  );
  assert.match(html, /role="slider"[^>]*aria-label="Hue"/);
  assert.match(html, /Saturation/);
  assert.match(html, /Brightness/);
  assert.match(html, /aria-label="Hex colour"/);
  assert.doesNotMatch(html, /type="color"/);
});

test("music uses unified search, upload, a volume slider and named icon toggles", async () => {
  const { Sound, videoSound } = await import("../src/timey/sound.tsx");
  assert.equal(videoSound({}), true);
  assert.equal(videoSound({ music: "upload:track" }), false);
  assert.equal(videoSound({ music: "upload:track", mix_audio: "on" }), true);
  assert.equal(videoSound({ music: "upload:track", mix_audio: "on", mute: "on" }), false);
  const html = renderToStaticMarkup(
    React.createElement(Sound, {
      values: {},
      change() {},
      background: { current: null },
      onListen() {},
    }),
  );
  assert.match(html, /placeholder="Search anything here…"/);
  assert.match(html, /aria-label="Upload music"/);
  assert.match(html, /type="range"[^>]*aria-label="Music volume"/);
  assert.match(html, /aria-label="Mix video audio with music"[^>]*aria-pressed="false"/);
  assert.match(html, /aria-label="Video sound"[^>]*aria-pressed="true"/);
  assert.doesNotMatch(html, /type="checkbox"|Drop music here|sound-track|Play music preview/);
  const selected = renderToStaticMarkup(
    React.createElement(Sound, {
      values: { music: "upload:track" },
      change() {},
      background: { current: null },
      onListen() {},
    }),
  );
  assert.match(selected, /aria-label="Play music preview"/);
  assert.match(selected, /aria-label="Remove music"/);
});
