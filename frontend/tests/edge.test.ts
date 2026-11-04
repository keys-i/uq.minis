import assert from "node:assert/strict";
import { expect, test, vi } from "vitest";
import worker from "../../deploy/edge.ts";

function assets() {
  return {
    fetch: vi.fn(async (request: Request) => {
      const pathname = new URL(request.url).pathname;
      if (pathname === "/index.html")
        return new Response("<main>UQ Minis</main>", {
          headers: { "Content-Type": "text/html", ETag: "release" },
        });
      if (pathname === "/assets/app.js")
        return new Response("export {}", {
          headers: { "Cache-Control": "public, max-age=31536000" },
        });
      return new Response("missing", { status: 404 });
    }),
  };
}

test("the UQ Worker serves scoped assets and deep links without an origin server", async () => {
  const binding = assets();
  const deepLink = await worker.fetch(new Request("https://uni.keysi.dev/mini/planny"), {
    ASSETS: binding,
  });
  assert.equal(deepLink.status, 200);
  assert.equal(await deepLink.text(), "<main>UQ Minis</main>");
  assert.equal(deepLink.headers.get("X-Frame-Options"), "DENY");
  assert.equal(deepLink.headers.get("Cache-Control"), "no-cache");
  expect(binding.fetch).toHaveBeenNthCalledWith(1, expect.objectContaining({ method: "GET" }));
  assert.equal(new URL(binding.fetch.mock.calls[0][0].url).pathname, "/planny");
  assert.equal(new URL(binding.fetch.mock.calls[1][0].url).pathname, "/index.html");

  const asset = await worker.fetch(new Request("https://uni.keysi.dev/mini/assets/app.js"), {
    ASSETS: binding,
  });
  assert.equal(asset.status, 200);
  assert.equal(asset.headers.get("Cache-Control"), "public, max-age=31536000");
  assert.equal(new URL(binding.fetch.mock.calls[2][0].url).pathname, "/assets/app.js");
});

test("the UQ Worker keeps backend failures explicit and private", async () => {
  const binding = assets();
  const response = await worker.fetch(new Request("https://uni.keysi.dev/api/health"), {
    ASSETS: binding,
  });
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal((await response.json()).status, "degraded");
  expect(binding.fetch).not.toHaveBeenCalled();

  const redirect = await worker.fetch(new Request("https://uni.keysi.dev/mini"), {
    ASSETS: binding,
  });
  assert.equal(redirect.status, 308);
  assert.equal(redirect.headers.get("Location"), "https://uni.keysi.dev/mini/");
  assert.equal(
    (await worker.fetch(new Request("https://example.com/mini/"), { ASSETS: binding })).status,
    404,
  );
});
