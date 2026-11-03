import { test } from "vitest";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { animalAt, animals, reactions } from "../src/wildlife/animals.ts";
import { atlases, pose } from "../src/wildlife/frames.ts";
import { lives, activity, habitatTime, sleepProfile } from "../src/wildlife/life.ts";

import * as cards from "../src/shared/cards.tsx";
import * as mascots from "../src/wildlife/mascot.tsx";
import * as artwork from "../src/wildlife/animal.tsx";
import * as calendar from "../src/study/calendar.tsx";
import * as places from "../src/wildlife/place.tsx";
import * as navigation from "../src/shared/menu.tsx";
import * as display from "../src/shared/display.tsx";
import * as research from "../src/study/research.tsx";
import * as language from "../src/shared/language.tsx";
import * as picker from "../src/shared/picker.tsx";
import * as forms from "../src/shared/forms.tsx";
import { voices as recordings } from "../src/wildlife/voices.ts";
import { announcement, info, plan, readiness } from "./fixtures.ts";
import type { Schema } from "../src/shared/schema.ts";

test("SVG markup stays in asset files rather than application source", () => {
  assert.equal(existsSync("src/assets"), false);
  for (const root of ["src", "../backend/src"])
    for (const path of readdirSync(root, { recursive: true, encoding: "utf8" }))
      if (/\.(?:ts|tsx|py)$/.test(path))
        assert.doesNotMatch(readFileSync(`${root}/${path}`, "utf8"), /<svg\b/i, path);
});

test("mini habitats keep whole cartoons and accessible controls", () => {
  for (const name of ["planny", "scrappy", "clubby", "event", "timey", "auth", "agent"]) {
    const html = renderToStaticMarkup(React.createElement(mascots.Pal, { name }));
    assert.match(html, /class="animal animal-/);
    assert.match(html, /aria-hidden="true"/);
    assert.doesNotMatch(html, /\/api\/habitat|<text\b/);
    assert.match(html, /popoverTarget="[^"]+" aria-label="My story/);
    assert.doesNotMatch(html, /Species story/);
    assert.doesNotMatch(html, /Next animal|animal-next/);
    assert.match(html, /data-portrait=/);
    const links = [...html.matchAll(/<a\b[^>]*>(.*?)<\/a>/gs)];
    assert.ok(links.length >= 1);
    assert.ok(links.every((link) => !/<button|<summary|<a\b/.test(link[1])));
  }
  assert.match(
    renderToStaticMarkup(React.createElement(mascots.Pal, { name: "new-mini" })),
    /data-animal="otter"/,
  );
});

test("all residents have complete bounded poses and small portraits", () => {
  assert.equal(animals.length, 50);
  assert.equal(new Set(animals.map((animal) => animal.id)).size, 50);
  for (const animal of animals) {
    const html = renderToStaticMarkup(React.createElement(artwork.Animal, { animal }));
    assert.match(html, new RegExp(`data-animal="${animal.id}"`));
    assert.match(html, /class="cartoon-still"/);
    assert.doesNotMatch(html, /<svg|<filter|animal-frame|animal-lid/);
    const atlas = atlases[animal.id];
    assert.ok([2, 3].includes(atlas.frames.length));
    assert.equal([...html.matchAll(/class="cartoon-pose"/g)].length, 1);
    for (const [x, y, w, h] of atlas.frames)
      assert.ok(
        x >= 0 && y >= 0 && w > 0 && h > 0 && x + w <= atlas.size[0] && y + h <= atlas.size[1],
        animal.id,
      );
    for (const action of [...lives[animal.id].acts, "sleep", "wake"])
      assert.ok(pose(animal, action) >= 0 && pose(animal, action) < atlas.frames.length);
    const source = readFileSync(
      new URL(`../assets/wildlife/cartoons/${animal.id}.webp`, import.meta.url),
    );
    assert.equal(source.toString("ascii", 8, 12), "WEBP");
    assert.ok(source.length < 400 * 1024, animal.id);
    assert.ok(
      readFileSync(
        new URL(`../assets/wildlife/cartoons/portraits/${animal.id}.webp`, import.meta.url),
      ).length <
        12 * 1024,
    );
    assert.ok(animal.source.startsWith("https://"));
  }
});

test("every animal has a regional story, useful conservation context and its own response", () => {
  assert.equal(new Set(Object.values(reactions)).size, animals.length);
  const css = readFileSync(new URL("../src/wildlife/animal.css", import.meta.url), "utf8")
    .replace(/\s+/g, "")
    .replaceAll('"', "");
  for (const animal of animals) {
    const html = renderToStaticMarkup(
      React.createElement(mascots.Story, { animal, id: `story-${animal.id}` }),
    );
    assert.match(html, /popover="auto"/);
    assert.match(html, new RegExp(`data-region="${animal.region}"`));
    assert.ok(html.includes(animal.home));
    assert.doesNotMatch(html, /\p{Regional_Indicator}|[🌎🌍🌏🌐]/u);
    assert.match(html, /class="place-(flag|globe)"/);
    assert.ok(html.includes(animal.care));
    assert.match(html, /Close my story/);
    assert.match(html, /class="home-clock"/);
    assert.match(html, /class="protector-link"/);
    assert.ok(html.indexOf("Close my story") < html.indexOf("status-badge"));
    assert.doesNotMatch(
      html,
      /Habitat weather|Choose a resident|animal-note-head|My voice|volume-balanced|voice-credit/,
    );
    assert.match(html, animal.status === "extinct" ? /What happened/ : /What I need/);
    assert.ok(animal.story.length > 70 && animal.story.length < 230);
    assert.ok(Number.isInteger(animal.scene) && animal.scene >= 0 && animal.scene < 20);
    assert.match(css, /--home:/);
  }
  assert.equal(animals.find((animal) => animal.id === "horse")?.scene, 10);
  assert.equal(animals.find((animal) => animal.id === "axolotl")?.scene, 11);
  assert.equal(animals.find((animal) => animal.id === "panda")?.scene, 9);
  assert.doesNotMatch(css, /is-explaining/);
  assert.match(css, /\.status-badge:hover{transform:/);
});

test("flags and ranges are drawn locally in the illustration style", () => {
  const css = readFileSync(new URL("../src/wildlife/animal.css", import.meta.url), "utf8")
    .replace(/\s+/g, "")
    .replaceAll('"', "");
  assert.match(css, /\.flag-cloth\[data-live=true\]{animation:flag-wave/);
  assert.match(css, /@keyframesflag-wave/);
  for (const animal of animals) {
    const html = renderToStaticMarkup(React.createElement(places.Place, { animal }));
    assert.doesNotMatch(html, /<svg|<path|<text|<image|https?:|\p{Regional_Indicator}/u);
    assert.equal((html.match(/<img /g) || []).length, animal.places.length);
    for (const place of animal.places) {
      const asset = readFileSync(new URL(`../assets/places/${place}.svg`, import.meta.url), "utf8")
        .replace(/\s+/g, "")
        .replaceAll('"', "");
      assert.match(asset, /<path/);
      assert.doesNotMatch(asset, /<image|<script/);
    }
  }
});

test("visitors have no scenery and form habitats keep interactive content above the backdrop", () => {
  const visitor = renderToStaticMarkup(
    React.createElement(mascots.Pal, { name: "visitor", controls: false, thoughts: true }),
  );
  assert.doesNotMatch(visitor, /class="habitat"|habitats-.*webp|homes-.*webp/);
  assert.match(visitor, /aria-label="Hear Dodo"/);
  assert.doesNotMatch(visitor, /imagined thought/);
  const page = renderToStaticMarkup(
    React.createElement(
      mascots.Pal,
      { name: "timey", page: true, thoughts: true },
      React.createElement("form", {}, React.createElement("input", { name: "duration" })),
    ),
  );
  assert.match(page, /habitat-page/);
  assert.match(page, /class="page-habitat"/);
  assert.match(page, /class="habitat-content"><form>/);
  assert.match(page, /name="duration"/);
  assert.match(page, /habitat-clearing/);
});

test("navigation has a touch menu and a useful footer without play or pause buttons", () => {
  const menu = renderToStaticMarkup(
    React.createElement(navigation.Menu, {
      tools: { timey: { title: "Timey", about: "Countdowns" } },
      tool: "timey",
      choose: () => {},
      account: () => {},
    }),
  );
  assert.match(menu, /aria-controls="mini-menu"/);
  assert.match(menu, /aria-expanded="false"/);
  assert.match(menu, /aria-current="page"/);
  assert.match(menu, /aria-label="Timey" data-tip="Timey"/);
  const css = readFileSync(new URL("../src/style.css", import.meta.url), "utf8")
    .replace(/\s+/g, "")
    .replaceAll('"', "");
  assert.match(css, /grid-template-columns:76pxminmax\(0,1fr\)/);
  assert.doesNotMatch(css, /\.sidebar>\*\{opacity:0/);
  const footer = renderToStaticMarkup(React.createElement(navigation.Footer));
  assert.match(footer, /Accessibility/);
  assert.match(footer, /Made with/);
  assert.match(footer, /love by/);
  assert.match(footer, /keys-i/);
  assert.match(footer, /aria-label="UQ minis on GitHub"/);
  assert.match(footer, /role="dialog"/);
  assert.match(footer, />Contrast</);
  assert.match(footer, /Reading size/);
  assert.match(footer, />Voices</);
  assert.doesNotMatch(footer, /Source<|Report a bug|Use Tab to/);
  assert.match(footer, />Motion</);
  assert.doesNotMatch(footer, /Play animals|Pause animals|animal-pause/);
});

test("residents vary activity without repeating, using their own habitat clocks", () => {
  for (const animal of animals) {
    const profile = lives[animal.id];
    assert.ok(new Set(profile.acts).size >= 3);
    let previous = "";
    const actions = new Set<string>();
    for (let turn = 0; turn < 80; turn++) {
      const next = activity(animal, turn, 12, previous);
      assert.notEqual(next, previous);
      actions.add(next);
      previous = next;
    }
    assert.ok(actions.size >= 3);
    assert.ok(habitatTime(animal, new Date("2026-01-01T00:00:00Z")).time);
    if (["kakapo", "dodo", "penguin", "auk"].includes(animal.id)) assert.ok(!actions.has("fly"));
  }
  const now = new Date("2026-01-01T00:00:00Z");
  assert.equal(habitatTime(animals[0], now).phase, "night");
  assert.equal(habitatTime(animals[1], now).time, "08:00");
  assert.equal(habitatTime(animals[17], now).time, "05:45");
  assert.equal(habitatTime(animals[17], now).phase, "dawn");
  assert.equal(habitatTime(animals[6], now).time, "13:00");
  assert.equal(habitatTime(animals[6], new Date("2026-07-01T00:00:00Z")).time, "12:00");
});

test("a chosen resident stays through many activities and recordings remain bounded", () => {
  let value = { index: 7, turn: 0 };
  for (let turn = 0; turn < 5000; turn++) {
    value = mascots.nextResident(value, () => 0.75);
    assert.equal(value.index, 7);
    assert.ok(value.turn >= 0 && value.turn < 4096);
  }
  assert.deepEqual(
    [0, 0.5, 0.999].map((random) => mascots.nextResident({ index: 7, turn: 0 }, () => random).turn),
    [1, 16, 31],
  );
  const panda = animals.find((animal) => animal.id === "panda")!,
    quoll = animals.find((animal) => animal.id === "quoll")!;
  assert.ok(sleepProfile(panda).wake > sleepProfile(quoll).wake);
  assert.match(sleepProfile(quoll).line, /woke me up/);
  let bytes = 0;
  for (const [id, voice] of Object.entries(recordings)) {
    const animal = animals.find((animal) => animal.id === id);
    assert.ok(animal);
    assert.ok(voice);
    assert.ok(!animal.status.startsWith("extinct"));
    assert.ok(voice.source.startsWith("https://commons.wikimedia.org/wiki/File:"));
    assert.match(voice.credit, /CC|public domain/);
    bytes += readFileSync(new URL(`../assets/audio/${id}.mp3`, import.meta.url)).length;
  }
  assert.ok(bytes < 128 * 1024);
});

test("display preferences reject corrupt and out-of-range saved values", () => {
  assert.deepEqual(display.preferences("broken"), {
    still: false,
    contrast: false,
    sound: false,
    size: 1,
    theme: "system",
  });
  assert.deepEqual(display.preferences('{"still":true,"contrast":true,"sound":true,"size":1.2}'), {
    still: true,
    contrast: true,
    sound: true,
    size: 1.2,
    theme: "system",
  });
  assert.deepEqual(display.preferences('{"still":"yes","size":1000}'), {
    still: false,
    contrast: false,
    sound: false,
    size: 1,
    theme: "system",
  });
});

test("status badges retain accessible names without visible status labels", () => {
  for (const [status, kind] of [
    ["extinct", "extinct"],
    ["critically endangered", "critical"],
    ["endangered / AU", "endangered"],
  ]) {
    const html = renderToStaticMarkup(React.createElement(mascots.Badge, { status }));
    assert.match(html, new RegExp(`status-${kind}`));
    assert.ok(html.includes(`aria-label="${status}"`));
    assert.doesNotMatch(html, />critically endangered<|>extinct<|>endangered/);
  }
});

test("each habitat cycles through every species before repeating", () => {
  for (let seed = 0; seed < 7; seed++) {
    const cycle = Array.from({ length: animals.length }, (_, turn) => animalAt(seed + 7 * turn).id);
    assert.equal(new Set(cycle).size, animals.length);
    assert.equal(animalAt(seed + 7 * animals.length).id, cycle[0]);
  }
  assert.equal(animalAt(-1), animals.at(-1));
});

test("calendar settings offer subscriptions without a snapshot download or nested controls", () => {
  const html = renderToStaticMarkup(
    React.createElement(calendar.CalendarSettings, { base: "http://127.0.0.1:8765" }),
  );
  assert.match(html, /Google Calendar/);
  assert.match(html, /Outlook on the web/);
  assert.match(html, /href="webcal:\/\/127.0.0.1:8765\/calendar.ics"/);
  assert.doesNotMatch(html, /download="planny.ics"|Download calendar snapshot/);
});

test("event cards show supplied artwork and keep Save outside the source link", () => {
  const item = announcement({
    title: "Movie night",
    club: "Film club",
    source: "Rubric",
    notes: "Bring a snack",
    url: "https://example.org/movie",
    banner: "https://example.org/banner.png",
    logo: "https://example.org/logo.png",
    start: "2026-10-25T08:00:00Z",
  });
  const html = renderToStaticMarkup(
    React.createElement(
      cards.EventCard,
      { item },
      React.createElement("button", { type: "button" }, "Save"),
    ),
  );
  assert.match(html, /src="https:\/\/example.org\/banner.png"/);
  assert.match(html, /src="https:\/\/example.org\/logo.png"/);
  assert.match(html, /<time[^>]+dateTime="2026-10-25T08:00:00Z"/);
  const links = [...html.matchAll(/<a\b[^>]*>(.*?)<\/a>/gs)];
  assert.equal(links.length, 1);
  assert.match(links[0][1], /Movie night/);
  assert.doesNotMatch(links[0][1], /<button/);
  assert.match(html, /<button type="button">Save<\/button>/);
  assert.doesNotMatch(html, /Original source/);
  assert.doesNotMatch(html, />Rubric</);
  assert.doesNotMatch(html, /↗|→|Movie night \/ Rubric/);
});

test("club cards use their logo as a cover when no event banner is available", () => {
  const club = {
    name: "Film club",
    directory_url: "https://example.org/club",
    logo: "https://example.org/logo.png",
    instagram: "https://www.instagram.com/filmclub/",
  };
  const html = renderToStaticMarkup(
    React.createElement(
      cards.ClubCard,
      { club },
      React.createElement("button", { type: "button" }, "Follow"),
    ),
  );
  assert.equal([...html.matchAll(/src="https:\/\/example.org\/logo.png"/g)].length, 2);
  assert.doesNotMatch(html, /Meet the club|>UQ<|Next up/);
  const links = [...html.matchAll(/<a\b[^>]*>(.*?)<\/a>/gs)];
  assert.equal(links.length, 2);
  assert.ok(links.every((link) => !link[1].includes("<button")));
  assert.match(html, /<button type="button">Follow<\/button>/);
});

test("a club's next event supplies real artwork and useful details", () => {
  const club = {
    name: "Film club",
    directory_url: "https://example.org/club",
    logo: "https://example.org/logo.png",
  };
  const nextEvent = announcement({
    title: "Movie night",
    start: "2026-10-25T08:00:00Z",
    banner: "https://example.org/movie.png",
  });
  const html = renderToStaticMarkup(React.createElement(cards.ClubCard, { club, nextEvent }));
  assert.match(html, /src="https:\/\/example.org\/movie.png"/);
  assert.match(html, /Next up \/ 25 Oct/);
  assert.match(html, /Movie night/);
});

test("cards without artwork or event dates retain usable content", () => {
  const item = announcement({
    title: "An update",
    source: "Instagram",
    notes: "Read the club update",
    url: "https://example.org/post",
  });
  const html = renderToStaticMarkup(React.createElement(cards.EventCard, { item }));
  assert.match(html, /An update/);
  assert.match(html, /Announcement/);
  assert.doesNotMatch(html, /<img|<time/);
});

test("script transitions preserve complete Indic and Arabic text runs", () => {
  for (const text of [
    "प्रोग्रामिंग और पाठ्यक्रम",
    "متطلبات المقرر الدراسي",
    "বাংলা ভাষায় কোর্স",
    "English course notes",
  ]) {
    const markup = renderToStaticMarkup(
      React.createElement(language.T, { source: "auto", original: true }, text),
    );
    assert.ok(markup.includes(text));
    assert.match(markup, /dir="auto"/);
    assert.equal([...markup.matchAll(/<span/g)].length, 2);
    assert.doesNotMatch(markup, /aria-hidden|dangerouslySetInnerHTML/);
  }
});

test("the course trail is keyboard-operable and keeps alternative rules readable", () => {
  const detail = info({
    course: { code: "CSSE2002", name: "Programming" },
    readiness: readiness({
      required: ["CSSE1001", "ENGG1001"],
      missing: ["CSSE1001", "ENGG1001"],
      status: "missing",
      wording: "CSSE1001 or ENGG1001",
    }),
  });
  const markup = renderToStaticMarkup(
    React.createElement(research.CourseMap, { info: detail, open: () => {} }),
  );
  assert.equal([...markup.matchAll(/<button type="button"/g)].length, 3);
  assert.match(markup, /Some branches are alternatives/);
  assert.match(markup, /CSSE1001 or ENGG1001/);
  assert.match(markup, /A few steps to go/);
});

test("research keeps refinements behind one clear control and never fabricates ratings", () => {
  const markup = renderToStaticMarkup(
    React.createElement(research.Research, {
      plan: plan(),
      compared: new Set<string>(),
      change: async () => {},
      choose: async () => {},
      toggle: () => {},
    }),
  );
  for (const label of [
    "Refine results",
    "Completed courses",
    "Skills and topics",
    "All faculties",
    "Highest first",
    "Lowest first",
    "Professors",
    "Usefulness",
    "Difficulty",
    "Fun",
  ])
    assert.ok(markup.includes(label), label);
  assert.doesNotMatch(markup, /When are you studying|Now \/ next|name="semester"/);
  assert.match(markup, /type="range"[^>]+aria-label="Minimum ratings for ranking"/);
  assert.doesNotMatch(markup, /Talkwall blend|Refresh public research/);
  assert.doesNotMatch(markup, /5\.0\/5|human-reviewed|guaranteed/);
});

test("theme selection is validated and doesn't change animal artwork", () => {
  assert.equal(display.preferences('{"theme":"dark"}').theme, "dark");
  assert.equal(display.preferences('{"theme":"unexpected"}').theme, "system");
  const animal = animals.find((item) => item.id === "otter");
  assert.ok(animal);
  const render = (theme: "light" | "dark") =>
    renderToStaticMarkup(
      React.createElement(
        display.Motion.Provider,
        {
          value: {
            reduced: true,
            hidden: false,
            paused: false,
            now: new Date("2026-10-20T12:00:00Z"),
            preferences: { ...display.preferences(null), theme },
            change() {},
            speak() {},
          },
        },
        React.createElement(artwork.Animal, {
          animal,
        }),
      ),
    );
  assert.equal(render("light"), render("dark"));
});

test("pocket filters retain native selection and named popover controls", () => {
  const html = renderToStaticMarkup(
    React.createElement(picker.Picker, {
      label: "Faculty",
      value: "science",
      options: [
        ["", "All faculties"],
        ["science", "Science"],
      ],
      onChange() {},
    }),
  );
  assert.match(html, /popover="auto" role="dialog" aria-label="Choose faculty"/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.match(html, /type="radio"[^>]+checked=""[^>]+value="science"/);
  assert.match(html, /aria-label="Close faculty choices"/);
  const theme = renderToStaticMarkup(React.createElement(display.ThemePicker));
  assert.match(theme, /class="theme-toggle"/);
  assert.match(theme, /<select aria-label="App theme"/);
  assert.match(theme, /<option value="system" selected="">System<\/option>/);
  assert.match(theme, /<option value="light">Day<\/option>/);
  assert.match(theme, /<option value="dark">Night<\/option>/);
});

test("club cards keep useful descriptions, named social icons and local profile controls", () => {
  const club = {
    name: "Film club",
    directory_url: "https://example.org/club",
    interests: "Hobby",
    description: "Weekly film nights and discussions",
    instagram: "https://www.instagram.com/filmclub/",
    sources: "old provenance",
  };
  const html = renderToStaticMarkup(React.createElement(cards.ClubCard, { club, open() {} }));
  assert.match(html, /Weekly film nights and discussions/);
  assert.match(html, /<button type="button" class="card-open">Film club<\/button>/);
  assert.match(html, /aria-label="Film club \/ Instagram"/);
  assert.doesNotMatch(
    html,
    /old provenance|↗|>Instagram<|<a[^>]+href="https:\/\/example.org\/club"/,
  );
});

test("mini forms keep required details visible and offer precise slider entry", () => {
  const schema: Schema = {
    fields: [
      {
        name: "action",
        label: "Create",
        type: "select",
        options: [
          ["render", "Video"],
          ["upload", "Upload"],
        ],
      },
      { name: "title", label: "Event name", required: true, group: "Your event" },
      {
        name: "size",
        label: "Timer size",
        type: "range",
        min: 0.5,
        max: 3,
        step: 0.1,
        value: 2.4,
        group: "Make it yours",
      },
      {
        name: "confirm",
        label: "Authorise this upload",
        type: "checkbox",
        when: { action: ["upload"] },
      },
    ],
  };
  const html = renderToStaticMarkup(
    React.createElement(forms.MiniForm, { schema, async submit() {} }),
  );
  assert.match(html, /<section class="form-settings"><h3>/);
  assert.match(html, /aria-label="Timer size \/ exact value"/);
  assert.match(html, /type="range"/);
  assert.doesNotMatch(html, /Authorise this upload/);
  const section = html.match(/<section class="form-settings">(.*?)<\/section>/);
  assert.ok(section);
  assert.match(section[1], /<input(?=[^>]*name="title")(?=[^>]*required="")[^>]*>/);
});
