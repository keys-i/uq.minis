import { test, vi } from "vitest";
import assert from "node:assert/strict";
import type { Clip } from "../src/timey/model.ts";
import { backdrop, prepare, preview } from "../src/timey/media.ts";
const clip = (extra: Partial<Omit<Clip, "source" | "start">> & { url: string }) => ({
  width: 960,
  height: 540,
  duration: 120,
  kind: "video",
  complete: false,
  ...extra,
});

test("the first cached section is shown while the complete video is still downloading", async () => {
  const shown: Clip[] = [];
  const calls: Record<string, FormDataEntryValue>[] = [];
  let finish: () => void = () => {
    throw new Error("The complete cache was never requested");
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => {
    assert.ok(options?.body instanceof FormData);
    calls.push(Object.fromEntries(options.body));
    return calls.length === 1
      ? new Response(
          JSON.stringify(clip({ url: "/download/first", complete: false, kind: "video" })),
        )
      : new Promise<Response>((resolve) => {
          finish = () =>
            resolve(new Response(JSON.stringify(clip({ url: "/download/full", complete: true }))));
        });
  });
  const waiting = backdrop("video", 80, new AbortController().signal, (clip) => shown.push(clip));
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(
    shown.map((clip) => [clip.url, clip.start]),
    [["/download/first", 80]],
  );
  assert.equal(calls[0].complete, undefined);
  assert.equal(calls[1].complete, "on");
  finish();
  await waiting;
  assert.deepEqual(
    shown.map((clip) => [clip.url, clip.start]),
    [
      ["/download/first", 80],
      ["/download/full", 0],
    ],
  );
});

test("leaving after the first section cancels background caching and images need no second download", async () => {
  let calls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    calls++;
    return new Response(JSON.stringify(clip({ url: "/download/first", kind: "video" })));
  });
  const controller = new AbortController();
  await assert.rejects(
    backdrop("video", 0, controller.signal, () => controller.abort()),
    { name: "AbortError" },
  );
  assert.equal(calls, 1);
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    calls++;
    return new Response(JSON.stringify(clip({ url: "/download/image", kind: "image" })));
  });
  await backdrop("picture", 0, new AbortController().signal, () => {});
  assert.equal(calls, 2);
});

test("an already complete cached backdrop needs one request and keeps its absolute timeline", async () => {
  let calls = 0;
  let shown: Clip | undefined;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    calls++;
    return new Response(
      JSON.stringify(clip({ url: "/download/full", complete: true, kind: "video" })),
    );
  });
  await backdrop("video", 80, new AbortController().signal, (clip) => {
    shown = clip;
  });
  assert.equal(calls, 1);
  assert.ok(shown);
  assert.equal(shown.start, 0);
  assert.equal(shown.complete, true);
});

test("a busy preview waits and succeeds instead of becoming unavailable", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  let calls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    ++calls === 1
      ? new Response(JSON.stringify({ detail: "Preparing another backdrop" }), {
          status: 429,
          headers: { "Retry-After": "2" },
        })
      : new Response(JSON.stringify(clip({ url: "/download/sample" }))),
  );
  const waiting = prepare(new FormData(), new AbortController().signal);
  await new Promise<void>((resolve) => setImmediate(resolve));
  vi.advanceTimersByTime(2000);
  assert.equal((await waiting).url, "/download/sample");
  assert.equal(calls, 2);
});

test("leaving a busy hover preview cancels its queued retry", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  let calls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    calls++;
    return new Response(JSON.stringify({ detail: "Preparing another backdrop" }), { status: 429 });
  });
  const controller = new AbortController(),
    waiting = prepare(new FormData(), controller.signal);
  const cancelled = assert.rejects(waiting, { name: "AbortError" });
  await new Promise<void>((resolve) => setImmediate(resolve));
  controller.abort();
  vi.advanceTimersByTime(30000);
  await cancelled;
  assert.equal(calls, 1);
});

test("a permanent preview error keeps its explanation without retrying", async () => {
  let calls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    calls++;
    return new Response(JSON.stringify({ error: "This video is unavailable" }), { status: 400 });
  });
  await assert.rejects(
    prepare(new FormData(), new AbortController().signal),
    /This video is unavailable/,
  );
  assert.equal(calls, 1);
});

test("busy animated overlays reuse the cancellable preview retry", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  let calls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    ++calls === 1
      ? new Response(JSON.stringify({ detail: "The preview is catching up" }), {
          status: 429,
          headers: { "Retry-After": "1" },
        })
      : new Response("animated", { headers: { "Content-Type": "image/webp" } }),
  );
  const pending = preview(new FormData(), new AbortController().signal);
  await new Promise<void>((resolve) => setImmediate(resolve));
  vi.advanceTimersByTime(1000);
  const blob = await pending;
  assert.equal(blob.type, "image/webp");
  assert.equal(await blob.text(), "animated");
  assert.equal(calls, 2);
});
