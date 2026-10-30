import { test } from "vitest";
import { assessment, announcement } from "./fixtures.ts";
import assert from "node:assert/strict";
import {
  deadline,
  format,
  included,
  localInput,
  personal,
  timestamp,
  upcoming,
  weekStart,
} from "../src/study/dates.ts";

test("personal targets retain official dates and respect item overrides", () => {
  const item = assessment({ due: "2026-10-25T08:00:00Z", buffer: null });
  assert.equal(personal(item, 2), "2026-10-23T08:00:00.000Z");
  assert.equal(item.due, "2026-10-25T08:00:00Z");
  assert.equal(personal(assessment({ ...item, buffer: 0 }), 2), "2026-10-25T08:00:00.000Z");
  assert.equal(personal(assessment({ due: "" }), 2), "");
});
test("assessment dates stay in Brisbane and retain published ranges", () => {
  assert.equal(
    format("2026-10-25T08:00:00Z", { hour: "numeric", minute: "2-digit" }),
    "25 Oct, 6:00 pm",
  );
  assert.equal(localInput("2026-10-25T08:00:00Z"), "2026-10-25T18:00");
  assert.equal(timestamp("2026-10-25T18:00"), "2026-10-25T08:00:00.000Z");
  assert.equal(deadline(assessment({ due: "", due_text: "5–20 Sep 2026" })), "5–20 Sep 2026");
});
test("calendar selections include followed clubs and individually saved events", () => {
  assert.equal(included(announcement({ saved: false, club_url: "club" }), []), false);
  assert.equal(included(announcement({ saved: false, club_url: "club" }), ["club"]), true);
  assert.equal(included(announcement({ saved: true }), []), true);
});
test("weeks start on Monday, including a Sunday and year boundary", () => {
  assert.equal(weekStart(0, new Date(2026, 9, 25)).getDate(), 19);
  const next = weekStart(1, new Date(2026, 11, 31));
  assert.equal(next.getFullYear(), 2027);
  assert.equal(next.getMonth(), 0);
  assert.equal(next.getDate(), 4);
});
test("announcements keep ordinary posts and ongoing events while hiding past or cancelled events", () => {
  const now = Date.parse("2026-10-19T08:00:00Z");
  assert.equal(upcoming(announcement({ start: "" }), now), true);
  assert.equal(upcoming(announcement({ start: "2026-10-18T08:00:00Z" }), now), false);
  assert.equal(
    upcoming(announcement({ start: "2026-10-19T07:00:00Z", end: "2026-10-19T09:00:00Z" }), now),
    true,
  );
  assert.equal(
    upcoming(announcement({ start: "2026-10-20T08:00:00Z", status: "cancelled" }), now),
    false,
  );
});
