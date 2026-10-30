import { test, vi } from "vitest";
import assert from "node:assert/strict";

import { useStudy } from "../src/study/store.ts";
import { useSession } from "../src/shared/session.ts";
const empty = () => ({
  revision: 0,
  courses: [],
  assessments: [],
  announcements: [],
  settings: { buffer: 2, target: 75 },
});
const reply = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

test("queued edits and imports keep the latest accepted revision", async () => {
  useStudy.setState({ plan: empty() });
  const seen: unknown[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (path, options) => {
    const document = JSON.parse(String(options?.body));
    seen.push([path, document.revision]);
    await new Promise((resolve) => setTimeout(resolve, 1));
    const result =
      path === "/api/import"
        ? {
            ...useStudy.getState().plan,
            revision: 2,
            announcements: [{ id: "club", title: "Meetup", notes: "" }],
          }
        : { ...document, revision: document.revision + 1 };
    return reply(result);
  });
  const edit = useStudy.getState().change((plan) =>
    plan.courses.push({
      id: "course",
      code: "CSSE1001",
      name: "Introduction to Software Engineering",
      profile: "",
      prerequisites: "",
      notes: "",
      verified: false,
    }),
  );
  const imported = useStudy.getState().source("/api/import", {});
  const last = useStudy.getState().change((plan) => {
    plan.settings.buffer = 5;
  });
  await Promise.all([edit, imported, last]);
  assert.deepEqual(seen, [
    ["/api/plan", 0],
    ["/api/import", undefined],
    ["/api/plan", 2],
  ]);
  assert.equal(accepted().revision, 3);
  assert.equal(accepted().courses.length, 1);
  assert.equal(accepted().announcements.length, 1);
  assert.equal(accepted().settings.buffer, 5);
  assert.equal(useStudy.getState().saving, false);
});

test("a failed edit preserves the saved plan and releases the next edit", async () => {
  useStudy.setState({ plan: empty() });
  let attempts = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_path, options) =>
    ++attempts === 1
      ? reply({ error: "Another tab saved" }, 409)
      : reply({ ...JSON.parse(String(options?.body)), revision: 1 }),
  );
  await assert.rejects(
    useStudy.getState().change((plan) => {
      plan.settings.buffer = 9;
    }),
    /Another tab/,
  );
  assert.equal(accepted().settings.buffer, 2);
  await useStudy.getState().change((plan) => {
    plan.settings.target = 80;
  });
  assert.equal(accepted().settings.target, 80);
  assert.equal(accepted().settings.buffer, 2);
  assert.equal(useStudy.getState().saving, false);
});

test("invalid imports cannot replace accepted state and refresh counts do not replace the plan", async () => {
  const accepted = empty();
  useStudy.setState({ plan: accepted });
  let value: unknown = { ...empty(), revision: "broken" };
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => reply(value));
  await assert.rejects(useStudy.getState().source("/api/import", {}), /unexpected data/);
  assert.equal(useStudy.getState().plan, accepted);
  assert.equal(useStudy.getState().saving, false);
  value = { count: 4 };
  assert.deepEqual(await useStudy.getState().source("/api/catalogues", {}), value);
  assert.equal(useStudy.getState().plan, accepted);
});

test("unmounted startup cannot publish a late plan", async () => {
  useStudy.setState({ plan: null });
  const controller = new AbortController();
  vi.spyOn(globalThis, "fetch").mockImplementation(async (path) =>
    reply(path === "/api/minis" ? {} : empty()),
  );
  const loaded = useStudy.getState().load(controller.signal);
  controller.abort();
  await loaded;
  assert.equal(useStudy.getState().plan, null);
});

test("gates share a status request and a late response cannot undo login", async () => {
  useSession.setState({ user: null, error: "" });
  let resolve: (response: Response) => void = () => {
    throw new Error("Status was never requested");
  };
  let requests = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(() => {
    requests++;
    return new Promise((done) => {
      resolve = done;
    });
  });
  const first = useSession.getState().load(),
    second = useSession.getState().load();
  assert.equal(first, second);
  assert.equal(requests, 1);
  useSession.getState().complete("student@student.uq.edu.au");
  resolve(reply({ user: "" }));
  await first;
  assert.equal(useSession.getState().user, "student@student.uq.edu.au");
});

test("logout failures keep access visible and a later success clears every gate", async () => {
  useSession.getState().complete("student@student.uq.edu.au");
  let failed = true;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    failed ? reply({ error: "Offline" }, 503) : reply({ user: "" }),
  );
  await useSession.getState().logout();
  assert.equal(useSession.getState().user, "student@student.uq.edu.au");
  assert.equal(useSession.getState().error, "Offline");
  failed = false;
  await useSession.getState().logout();
  assert.equal(useSession.getState().user, "");
  assert.equal(useSession.getState().error, "");
});

function accepted() {
  const value = useStudy.getState().plan;
  assert.ok(value);
  return value;
}

test("cached plans paint immediately and queued edits use the revalidated revision", async () => {
  const { queries } = await import("../src/shared/query.ts");
  queries.setQueryData(["private", undefined, "plan"], empty(), { updatedAt: Date.now() - 60_000 });
  useStudy.setState({ plan: null });
  let finish!: (response: Response) => void;
  const revisions: number[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_path, init) => {
    if (!init?.body)
      return new Promise<Response>((resolve) => {
        finish = resolve;
      });
    const plan = JSON.parse(String(init.body));
    revisions.push(plan.revision);
    return reply({ ...plan, revision: plan.revision + 1 });
  });
  const load = useStudy.getState().load();
  assert.equal(accepted().revision, 0);
  const edit = useStudy.getState().change((plan) => {
    plan.settings.buffer = 4;
  });
  finish(reply({ ...empty(), revision: 5 }));
  await Promise.all([load, edit]);
  assert.deepEqual(revisions, [5]);
  assert.equal(accepted().revision, 6);
  assert.equal(accepted().settings.buffer, 4);
});
