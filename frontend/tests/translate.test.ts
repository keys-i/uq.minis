import { test, afterEach, vi } from "vitest";
import assert from "node:assert/strict";
import { matchLanguage, orderLanguages } from "../src/shared/locale.ts";
import { Translations } from "../src/shared/translate.ts";
import { json } from "./fixtures.ts";

const languages = {
  en: "English",
  ko: "한국어",
  ar: "العربية",
  hi: "हिन्दी",
  de: "Deutsch",
  "zh-Hans": "简体中文",
  "zh-Hant": "繁體中文",
};
afterEach(() => {
  delete globalThis.Translator;
  delete globalThis.LanguageDetector;
});

test("browser preferences lead the language list across regions and scripts", () => {
  for (const [tag, code] of [
    ["ko-KR", "ko"],
    ["ar-AE", "ar"],
    ["hi-IN", "hi"],
    ["de-AT", "de"],
    ["zh-TW", "zh-Hant"],
    ["zh-CN", "zh-Hans"],
  ]) {
    assert.equal(matchLanguage(languages, tag), code);
    assert.deepEqual(orderLanguages(languages, [tag, "en-AU", tag]).slice(0, 2), [code, "en"]);
  }
  assert.equal(orderLanguages(languages, ["invalid_locale"])[0], "en");
  assert.equal(orderLanguages(languages, ["fr-FR"])[0], "en");
  assert.equal(
    new Set(orderLanguages(languages, ["ko", "ar", "ko"])).size,
    Object.keys(languages).length,
  );
});

test("native translation detects the source, caches completed text and releases engines", async () => {
  let created = 0,
    translated = 0,
    destroyed = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    throw new Error("Native translation must stay on device");
  });
  globalThis.Translator = {
    create: async () => {
      created++;
      return {
        translate: async () => {
          translated++;
          return "पाठ्यक्रम";
        },
        destroy: () => destroyed++,
      };
    },
  };
  globalThis.LanguageDetector = {
    create: async () => ({
      detect: async () => [{ detectedLanguage: "en" }],
      destroy: () => destroyed++,
    }),
  };
  const service = new Translations();
  await service.prepare("hi");
  assert.equal(await service.read("Course", "auto", "hi"), "पाठ्यक्रम");
  assert.equal(await service.read("Course", "auto", "hi"), "पाठ्यक्रम");
  assert.equal(created, 1);
  assert.equal(translated, 1);
  service.dispose();
  await Promise.resolve();
  assert.equal(destroyed, 2);
});

test("unsupported native pairs fall back, and an alternate explicitly uses the service", async () => {
  const requests: unknown[] = [];
  globalThis.Translator = {
    create: async () => {
      throw new DOMException("Unavailable pair", "NotSupportedError");
    },
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, request) => {
    requests.push([url, JSON.parse(String(request?.body))]);
    return json({ text: "مقرر" });
  });
  const service = new Translations();
  await assert.rejects(service.read("Course", "en", "ar"), { name: "NotSupportedError" });
  assert.equal(await service.read("Course", "en", "ar", { server: true }), "مقرر");
  assert.equal(await service.read("Course", "en", "ar", { server: true, alternate: true }), "مقرر");
  assert.deepEqual(
    requests,
    Array(2).fill(["/api/translate", { text: "Course", target: "ar", source: "en" }]),
  );
  service.dispose();
});

test("a cancelled reader cannot poison a later translation of the same text", async () => {
  let release: () => void = () => {
    throw new Error("Translation did not start");
  };
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  globalThis.Translator = {
    create: async () => ({
      translate: async () => {
        await waiting;
        return "한국어";
      },
      destroy() {},
    }),
  };
  const service = new Translations(),
    controller = new AbortController();
  const old = service.read("Course", "en", "ko", { signal: controller.signal });
  await Promise.resolve();
  controller.abort();
  const current = service.read("Course", "en", "ko");
  release();
  await assert.rejects(old, { name: "AbortError" });
  assert.equal(await current, "한국어");
  service.dispose();
});

test("translation caches and native engines stay bounded", async () => {
  let destroyed = 0;
  globalThis.Translator = {
    create: async () => ({
      translate: async (text) => text + " translated",
      destroy: () => destroyed++,
    }),
  };
  const service = new Translations();
  for (const target of ["ko", "ar", "hi", "de"]) await service.read("Course", "en", target);
  assert.equal(service.engines.size, 3);
  assert.equal(destroyed, 1);
  for (let index = 0; index < 130; index++) await service.read(String(index), "en", "de");
  assert.equal(service.cache.size, 128);
  service.dispose();
  await Promise.resolve();
  assert.equal(destroyed, 4);
});

test("a browser's internal abort falls back without treating it as a reader cancellation", async () => {
  globalThis.Translator = {
    create: async () => {
      throw new DOMException("Native model stopped", "AbortError");
    },
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () => new Response(JSON.stringify({ text: "पाठ्यक्रम" })),
  );
  const service = new Translations();
  assert.equal(await service.read("Course", "en", "hi", { server: true }), "पाठ्यक्रम");
  service.dispose();
});

test("provider cooldown prevents queued text from repeatedly calling a busy service", async () => {
  let calls = 0,
    now = 1000;
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    calls++;
    return calls === 1
      ? new Response(JSON.stringify({ detail: "Translation is resting" }), {
          status: 429,
          headers: { "Retry-After": "60" },
        })
      : new Response(JSON.stringify({ text: "مقرر" }));
  });
  const service = new Translations();
  for (let index = 0; index < 20; index++)
    await assert.rejects(
      service.read(`Course ${index}`, "en", "ar", { server: true }),
      /Translation is resting/,
    );
  assert.equal(calls, 1);
  now += 60001;
  assert.equal(await service.read("Course 0", "en", "ar", { server: true }), "مقرر");
  assert.equal(calls, 2);
  service.dispose();
});

test("malformed service results are never cached and recover after a short cooldown", async () => {
  let now = 1000,
    response = "";
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(response));
  const service = new Translations();
  for (const bad of [
    "not json",
    "null",
    "{}",
    '{"text":" "}',
    '{"text":5}',
    JSON.stringify({ text: "x".repeat(12001) }),
  ]) {
    response = bad;
    await assert.rejects(service.read("Course", "en", "hi", { server: true }));
    assert.equal(service.cache.size, 0);
    now += 5001;
  }
  response = JSON.stringify({ text: "पाठ्यक्रम" });
  assert.equal(await service.read("Course", "en", "hi", { server: true }), "पाठ्यक्रम");
  service.dispose();
});

test("cancellation never starts the fallback after a delayed native failure", async () => {
  let reject: (error: Error) => void = () => {
    throw new Error("Native creation did not start");
  };
  globalThis.Translator = {
    create: () =>
      new Promise((resolve, fail) => {
        reject = fail;
      }),
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
    throw new Error("Cancelled work must not reach the service");
  });
  const service = new Translations(),
    controller = new AbortController();
  const pending = service.read("Course", "en", "hi", { server: true, signal: controller.signal });
  await Promise.resolve();
  controller.abort();
  reject(new Error("Native model failed"));
  await assert.rejects(pending, { name: "AbortError" });
  service.dispose();
});
