// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { Planner } from "../src/study/planner.tsx";
import { assessment, course, json, plan } from "./fixtures.ts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("Planny syncs published assessments without asking the student", async () => {
  const selected = plan({
    courses: [
      course({
        id: "course",
        profile: "https://course-profiles.uq.edu.au/current",
      }),
    ],
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      json({
        assessments: [
          {
            title: "Project",
            weight: 40,
            due: "2026-11-10T06:00:00Z",
            due_text: "",
            notes: "Published task",
          },
        ],
        rules: "",
        notice: "",
      }),
    ),
  );
  const change = vi.fn(async (edit: (value: typeof selected) => void) => edit(selected));

  const view = render(
    <Planner plan={selected} change={change} modal={() => {}} courses={() => {}} />,
  );

  await waitFor(() => expect(selected.assessments).toHaveLength(1));
  expect(selected.assessments[0].title).toBe("Project");
  expect(view.queryByText(/bring in the published assessments/i)).toBeNull();
});

test("courses group coloured assessment types and open their marks calculator", async () => {
  const user = userEvent.setup(),
    selected = plan({
      courses: [
        course({ id: "software", code: "CSSE2002", name: "Software Engineering" }),
        course({ id: "design", code: "DECO2500", name: "Design Computing" }),
      ],
      assessments: [
        assessment({ id: "exam", course: "software", title: "Final exam", weight: 60 }),
        assessment({ id: "project", course: "design", title: "Team project", weight: 40 }),
      ],
    });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      json({
        software: {
          completed: 0,
          count: 1,
          projection: 75,
          high: 100,
          low: 0,
          required: 70,
          warnings: [],
        },
        design: {
          completed: 0,
          count: 1,
          projection: 80,
          high: 100,
          low: 0,
          required: 65,
          warnings: [],
        },
      }),
    ),
  );

  const view = render(
    <Planner plan={selected} change={vi.fn()} modal={() => {}} courses={() => {}} />,
  );
  expect(view.container.querySelector(".enrolled-summary")).toBeNull();
  expect(screen.getByRole("img", { name: "Exam assessment" }).closest(".task-row")).toHaveAttribute(
    "data-kind",
    "exam",
  );
  expect(
    screen.getByRole("img", { name: "Project assessment" }).closest(".task-row"),
  ).toHaveAttribute("data-kind", "project");

  await user.click(screen.getByRole("button", { name: "View DECO2500 Design Computing marks" }));
  expect(screen.getByRole("button", { name: "Marks" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("Course")).toHaveValue("design");
  expect(await screen.findByLabelText("DECO2500 projected percentage")).toBeVisible();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
