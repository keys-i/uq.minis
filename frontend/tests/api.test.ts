import { test, expect, vi } from "vitest";
import assert from "node:assert/strict";
import { z } from "zod";
import { api, read, request, bind } from "../src/shared/api.ts";
import {
  planSchema,
  profileSchema,
  researchSchema,
  teachersSchema,
  courseInfoSchema,
  clubResultSchema,
} from "../src/study/model.ts";
import { portalSchema, formSchema } from "../src/shared/schema.ts";
import { syncProfile } from "../src/study/courses.ts";
import { assessment, course, plan as makePlan } from "./fixtures.ts";

const reply = (value: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(value), { status, headers });
const plan = {
  revision: 1,
  courses: [],
  assessments: [],
  announcements: [],
  settings: { buffer: 2, target: 75, future: "preserve" },
  future: { editable: true },
};

test("API responses validate before returning and retain cancellation and request encoding", async () => {
  const controller = new AbortController(),
    requests: RequestInit[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_path, options) => {
    requests.push(options || {});
    return reply({ count: 3 });
  });
  const schema = z.object({ count: z.number() });
  assert.deepEqual(await api("/api/count", schema, { value: 1 }, controller.signal), { count: 3 });
  assert.equal(requests[0].body, '{"value":1}');
  assert.equal(new Headers(requests[0].headers).get("Content-Type"), "application/json");
  assert.equal(requests[0].signal, controller.signal);
  const file = new Blob(["media"], { type: "video/mp4" }),
    form = new FormData();
  for (const body of [file, form]) {
    await api("/api/upload", schema, body);
    assert.equal(requests[requests.length - 1].body, body);
    assert.deepEqual([...new Headers(requests[requests.length - 1].headers)], []);
  }
  const reason = new DOMException("Cancelled", "AbortError");
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    throw reason;
  });
  await assert.rejects(
    api("/api/count", schema, undefined, controller.signal),
    (error) => error === reason,
  );
});

test("a missing guest cookie reports failure without a reload loop", async () => {
  const reload = vi.fn(),
    workspace = "guest:" + "a".repeat(64);
  vi.stubGlobal("location", { reload });
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    reply({ error: "Reload Minis to prepare your workspace" }, 401),
  );
  bind(workspace);
  assert.equal((await request("/api/plan")).status, 401);
  expect(reload).not.toHaveBeenCalled();
  bind(workspace, "a@uq.edu.au");
  await request("/api/minis/event");
  expect(reload).toHaveBeenCalledOnce();
});

test("malformed JSON shapes fail without leaking payload values", async () => {
  for (const value of [null, [], {}, { count: "private value" }])
    await expect(read(reply(value), z.object({ count: z.number() }))).rejects.toMatchObject({
      status: 502,
      message: "The server returned unexpected data; try again shortly",
    });
  await expect(read(new Response("<html>Offline</html>"), z.object({}))).rejects.toThrow(
    "unreadable response",
  );
});
test("server errors retain their status and retry delay before success-schema validation", async () => {
  await expect(
    read(reply({ detail: "Busy" }, 429, { "Retry-After": "2" }), planSchema),
  ).rejects.toMatchObject({ message: "Busy", status: 429, retryAfter: 2 });
  for (const value of [null, { error: { private: "value" } }])
    await expect(read(reply(value, 503), planSchema)).rejects.toMatchObject({
      status: 503,
      message: expect.stringContaining("connection is back"),
    });
});

test("saved-plan schemas reject invalid nested data and preserve additional editable fields", () => {
  assert.deepEqual(planSchema.parse(plan), plan);
  for (const value of [
    { ...plan, revision: -1 },
    { ...plan, settings: { buffer: "2", target: 75 } },
    { ...plan, courses: [{ id: "incomplete" }] },
    { ...plan, announcements: [{ id: "event", title: null, notes: "" }] },
  ])
    assert.equal(planSchema.safeParse(value).success, false);
  const course = {
    id: "course",
    code: "CSSE1001",
    name: "Programming",
    profile: "",
    prerequisites: "",
    notes: "",
    verified: false,
    future: "preserve",
  };
  assert.deepEqual(planSchema.parse({ ...plan, courses: [course] }).courses[0], course);
});

test("profile imports accept proposed assessments before course IDs are assigned", () => {
  const value = {
    assessments: [
      { title: "Essay", weight: 30, due: "", due_text: "Week 5", notes: "Review the date" },
    ],
    rules: "Check the profile",
    notice: "Review before saving",
  };
  assert.deepEqual(profileSchema.parse(value), value);
  assert.equal(
    profileSchema.safeParse({ ...value, assessments: [{ title: "Essay", weight: "30" }] }).success,
    false,
  );
});

test("profile sync replaces official facts and retains marks", () => {
  const selected = course({ profile: "https://course-profiles.uq.edu.au/current" }),
    saved = assessment({
      source: "profile",
      url: "https://course-profiles.uq.edu.au/older",
      score: 82,
      done: true,
    }),
    manual = assessment({ id: "manual", title: "Personal reminder" }),
    current = makePlan({ courses: [selected], assessments: [saved, manual] });
  syncProfile(current, selected, {
    assessments: [
      {
        title: "Assignment",
        weight: 35,
        due: "",
        due_text: "5–20 Sep 2026",
        notes: "Build and explain a small program",
      },
    ],
    rules: "",
    notice: "Synced",
  });
  assert.equal(current.assessments.length, 2);
  assert.deepEqual(current.assessments[0], manual);
  assert.deepEqual(current.assessments[1], {
    ...saved,
    weight: 35,
    due: "",
    due_text: "5–20 Sep 2026",
    notes: "Build and explain a small program",
    url: selected.profile,
    maximum: 100,
    team: false,
    factor: 1,
    penalty: 0,
  });
});

test("portal packets require a verified-identity shape or complete frame", () => {
  assert.equal(portalSchema.safeParse({ user: true }).success, false);
  assert.equal(portalSchema.safeParse({ image: "pixels" }).success, false);
  assert.equal(portalSchema.safeParse({ user: "s1234567@student.uq.edu.au" }).success, true);
});

test("form choices retain numeric values supplied by the backend", () => {
  const value = {
    fields: [
      {
        name: "fps",
        label: "Motion",
        type: "select",
        options: [
          [24, "Cinematic"],
          [60, "Smooth"],
        ],
      },
    ],
  };
  assert.deepEqual(formSchema.parse(value), value);
  assert.equal(
    formSchema.safeParse({ fields: [{ ...value.fields[0], options: [[true, "Invalid"]] }] })
      .success,
    false,
  );
});

test("research accepts empty feedback and teacher results while course readiness stays required", () => {
  const readiness = {
    status: "review",
    missing: [],
    incompatible: [],
    wording: "",
    skills: [],
    required: [],
  };
  const info = {
    course: null,
    details: {},
    readiness,
    url: "https://programs-courses.uq.edu.au/course.html?course_code=CSSE1001",
    reviews: [],
    secat: [],
    offerings: [],
    feedback: {},
  };
  assert.deepEqual(courseInfoSchema.parse(info), info);
  const result = {
    rows: [{ code: "teacher", name: "Lecturer", faculty: "Science", metrics: {}, readiness: {} }],
    total: 1,
    faculties: ["Science"],
    study_year: 2026,
  };
  assert.equal(teachersSchema.parse(result).rows[0].name, "Lecturer");
  assert.equal(researchSchema.safeParse(result).success, false);
  assert.deepEqual(clubResultSchema.parse({ rows: [], total: 0 }).categories, []);
});

test("hosted jobs preserve account binding and final errors", async () => {
  vi.useFakeTimers();
  bind("a@uq.edu.au");
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(reply({}, 202, { Location: "/api/jobs/owned" }))
    .mockResolvedValueOnce(reply({ error: "Render failed" }, 422));
  try {
    const pending = request("/api/minis/timey", { method: "POST", body: "{}" });
    await vi.runAllTimersAsync();
    const response = await pending;
    assert.equal(response.status, 422);
    for (const [, init] of fetcher.mock.calls)
      assert.equal(new Headers(init?.headers).get("X-Minis-Account"), "a@uq.edu.au");
  } finally {
    bind();
    vi.useRealTimers();
  }
});
