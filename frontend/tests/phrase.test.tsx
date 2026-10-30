// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { interpret } from "../src/shared/interpret.ts";
import { matches, terms } from "../src/shared/search.ts";
import { MiniForm } from "../src/shared/forms.tsx";
import { TaskEditor } from "../src/study/planner.tsx";
import { Courses } from "../src/study/course.tsx";
import { Research } from "../src/study/research.tsx";
import { years } from "../src/study/courses.ts";
import { assessment, course, json, plan } from "./fixtures.ts";
import type { Field } from "../src/shared/schema.ts";

afterEach(cleanup);
const fields: Field[] = [
  { name: "title", label: "Name" },
  { name: "due", label: "Deadline" },
  { name: "weight", label: "Weight", min: 0, max: 100 },
  { name: "course", label: "Course", options: [["course", "CSSE1001"]] },
];
const now = new Date(2026, 9, 23, 10);

test("a brief proposes fields and follow-ups retain unrelated edits", () => {
  const draft = interpret("CSSE1001 essay worth 30% due next Friday at 5pm", fields, {}, now);
  expect(draft.values).toMatchObject({
    title: "essay",
    course: "course",
    weight: "30",
    due: "2026-10-30T17:00",
  });
  expect(interpret("Make it 40% instead", fields, draft.values, now).values).toEqual({
    weight: "40",
  });
  expect(interpret('Rename it to "Final essay"', fields, draft.values, now).values).toEqual({
    title: "Final essay",
  });
  expect(interpret("Move it to tomorrow", fields, draft.values, now).values).toEqual({
    due: "2026-10-24T17:00",
  });
  const uncertain = interpret("essay due Friday", fields, {}, now);
  expect(uncertain.values.due).toBeUndefined();
  expect(uncertain.notes).toContain("Add a deadline time below");
  expect(interpret("essay worth 120%", fields, {}, now).values.weight).toBeUndefined();
  expect(interpret("MATH1051 essay", fields, {}, now).notes).toContain(
    "MATH1051 isn't in your selected courses",
  );
});

test("local searches understand topics and exclusions", () => {
  expect(matches("Bushwalking society", terms("gaming or hiking clubs", "clubs"))).toBe(true);
  expect(
    matches("Photography and alcohol", terms("clubs without gaming and alcohol", "clubs")),
  ).toBe(false);
  expect(matches("Software Society", terms("I'd like to join a coding club", "clubs"))).toBe(true);
  expect(matches("Games and alcohol", terms("gaming clubs without alcohol", "clubs"))).toBe(false);
  expect(matches("Eagle in Australia", terms("show birds from Australia", "animals"))).toBe(true);
});

test("filling an event brief never submits it", async () => {
  const user = userEvent.setup(),
    submit = vi.fn();
  render(
    <MiniForm
      schema={{
        fields: [
          { name: "input", label: "Source", type: "select", options: [["new", "New"]] },
          { name: "event.title", label: "Event name" },
          { name: "attendance", label: "Guests", type: "number", min: 1, max: 10000 },
          { name: "event.date", label: "Date", type: "date" },
          { name: "schedule.event_start", label: "Start", type: "time" },
          { name: "schedule.event_end", label: "End", type: "time" },
        ],
      }}
      submit={submit}
    />,
  );
  await user.type(
    screen.getByPlaceholderText(/Movie night/),
    '"Movie night" for 50 people on 24 October 2026 from 6pm to 8pm{Enter}',
  );
  await waitFor(() => expect(screen.getByLabelText("Event name")).toHaveValue("Movie night"));
  expect(screen.getByLabelText("Guests")).toHaveValue(50);
  expect(screen.getByLabelText("Date")).toHaveValue("2026-10-24");
  expect(screen.getByLabelText("Start")).toHaveValue("18:00");
  expect(screen.getByLabelText("End")).toHaveValue("20:00");
  expect(submit).not.toHaveBeenCalled();
});

test("published facts stay read-only and PAF is limited to group projects", async () => {
  const user = userEvent.setup(),
    item = assessment({
      source: "profile",
      url: "https://course-profiles.uq.edu.au/current",
      due_text: "5–20 Sep 2026",
      notes: "Build and explain a small program",
    }),
    current = plan({ courses: [course()], assessments: [item] }),
    change = vi.fn(async (edit: (value: typeof current) => void) => edit(current));
  render(<TaskEditor item={item} plan={current} change={change} close={vi.fn()} />);
  expect(screen.getByText("5–20 Sep 2026")).toBeVisible();
  await user.click(screen.getByText("Published task details"));
  expect(screen.getByText("Build and explain a small program")).toBeVisible();
  expect(screen.queryByLabelText("Assessment name")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Course weight (%)")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Remove assessment/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText(/Your mark/)).toBeEnabled();
  expect(screen.queryByLabelText("Peer assessment factor (PAF)")).not.toBeInTheDocument();
  await user.click(screen.getByLabelText("This is a group project"));
  const factor = screen.getByLabelText("Peer assessment factor (PAF)");
  await user.clear(factor);
  await user.type(factor, "0.8");
  await user.click(screen.getByRole("button", { name: "Save result and plan" }));
  await waitFor(() => expect(change).toHaveBeenCalledOnce());
  expect(current.assessments[0]).toMatchObject({ team: true, factor: 0.8 });
});

test("course profiles stay a background detail with one direct link", async () => {
  const offerings = [
    {
      period: "Semester 1, 2025",
      campus: "St Lucia",
      profile: "https://course-profiles.uq.edu.au/old",
    },
    {
      period: "Semester 2, 2026",
      campus: "St Lucia",
      profile: "https://course-profiles.uq.edu.au/new",
    },
    { period: "Undated", campus: "Gatton" },
  ];
  expect(years(offerings).latest).toEqual(offerings.slice(1));
  const future = { period: "Semester 1, 2027", campus: "St Lucia" };
  expect(years([...offerings, future]).latest).toEqual(offerings.slice(1));
  expect(years([...offerings, future]).more).toEqual([offerings[0], future]);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    json({ rows: [], total: 0, faculties: [], study_year: 2026, updated: "2026-10-23" }),
  );
  render(
    <Courses
      plan={plan({ courses: [course({ profile: offerings[1].profile })] })}
      change={vi.fn()}
      modal={vi.fn()}
      continuePlan={vi.fn()}
    />,
  );
  const link = screen.getByRole("link", { name: "View CSSE1001 on UQ" });
  expect(link).toHaveAttribute("href", offerings[1].profile);
  expect(screen.queryByText(/Sync the assessments|Read profile|View assessments/i)).toBeNull();
});

test("Scrappy prepares missing public course data without showing maintenance tools", async () => {
  let ready = false,
    searches = 0,
    refreshes = 0;
  const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (path) => {
    const url = String(path);
    if (url === "/api/research/refresh") {
      ready = true;
      refreshes += 1;
      return json({});
    }
    if (url.startsWith("/api/research?")) {
      searches += 1;
      return json({
        rows: [],
        total: 0,
        faculties: [],
        study_year: 2026,
        updated: ready ? "2026-10-23T00:00:00Z" : "",
      });
    }
    throw new Error(`Unexpected request ${url}`);
  });
  render(
    <Research
      plan={plan()}
      change={async () => {}}
      choose={async () => {}}
      compared={new Set()}
      toggle={() => {}}
    />,
  );
  await waitFor(() => expect(searches).toBeGreaterThanOrEqual(2));
  expect(refreshes).toBe(1);
  expect(screen.queryByText("Course data tools")).not.toBeInTheDocument();
  request.mockRestore();
});
