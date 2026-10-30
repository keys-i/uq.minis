// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { Buzzy } from "../src/study/buzzy.tsx";
import { json, plan } from "./fixtures.ts";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("Buzzy switches directly between its week and month calendars", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json({ rows: [], warning: "" })),
  );
  const user = userEvent.setup();
  render(
    <Buzzy
      plan={plan()}
      change={async () => {}}
      modal={() => {}}
      calendar={() => {}}
      choose={() => {}}
    />,
  );

  const week = screen.getByRole("grid", { name: "Buzzy weekly calendar" });
  expect(within(week).getAllByRole("gridcell")).toHaveLength(7);
  expect(document.querySelector("summary")).not.toBeInTheDocument();
  expect(screen.queryByText("Deadlines, breathing room and time with your people")).toBeNull();

  await user.click(screen.getByRole("button", { name: "Month" }));
  const month = screen.getByRole("grid", { name: "Buzzy monthly calendar" });
  expect(within(month).getAllByRole("gridcell")).toHaveLength(42);
  expect(screen.getByRole("button", { name: "Previous month" })).toBeVisible();
  await waitFor(() => expect(fetch).toHaveBeenCalled());
});
