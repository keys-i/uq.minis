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

function database() {
  const plans = new Map<string, { revision: number; data: string }>();
  return {
    plans,
    binding: {
      prepare(statement: string) {
        let values: unknown[] = [];
        return {
          bind(...next: unknown[]) {
            values = next;
            return this;
          },
          async first<T>() {
            if (statement.startsWith("SELECT data"))
              return (plans.get(String(values[0])) || null) as T;
            const [workspace, inserted, expected, updated, current] = values as [
              string,
              string,
              number,
              string,
              number,
            ];
            const saved = plans.get(workspace);
            if (!saved && expected === 0) {
              plans.set(workspace, { revision: 1, data: inserted });
              return { revision: 1 } as T;
            }
            if (saved?.revision === current) {
              plans.set(workspace, { revision: saved.revision + 1, data: updated });
              return { revision: saved.revision + 1 } as T;
            }
            return null;
          },
        };
      },
    },
  };
}

const environment = (binding = assets(), db = database().binding) => ({ ASSETS: binding, DB: db });

test("the UQ Worker serves scoped assets and deep links without an origin server", async () => {
  const binding = assets();
  const deepLink = await worker.fetch(
    new Request("https://uni.keysi.dev/mini/planny"),
    environment(binding),
  );
  assert.equal(deepLink.status, 200);
  assert.equal(await deepLink.text(), "<main>UQ Minis</main>");
  assert.equal(deepLink.headers.get("X-Frame-Options"), "DENY");
  assert.equal(deepLink.headers.get("Cache-Control"), "no-cache");
  expect(binding.fetch).toHaveBeenNthCalledWith(1, expect.objectContaining({ method: "GET" }));
  assert.equal(new URL(binding.fetch.mock.calls[0][0].url).pathname, "/index.html");

  const asset = await worker.fetch(
    new Request("https://uni.keysi.dev/mini/assets/app.js"),
    environment(binding),
  );
  assert.equal(asset.status, 200);
  assert.equal(asset.headers.get("Cache-Control"), "public, max-age=31536000");
  assert.equal(new URL(binding.fetch.mock.calls[1][0].url).pathname, "/assets/app.js");
});

test("the UQ Worker exposes health, redirects and its pinned installer", async () => {
  const binding = assets();
  const response = await worker.fetch(
    new Request("https://uni.keysi.dev/api/health"),
    environment(binding),
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.deepEqual(await response.json(), {
    status: "ok",
    service: "uq-minis-edge",
  });
  expect(binding.fetch).not.toHaveBeenCalled();

  const redirect = await worker.fetch(
    new Request("https://uni.keysi.dev/mini"),
    environment(binding),
  );
  assert.equal(redirect.status, 308);
  assert.equal(redirect.headers.get("Location"), "https://uni.keysi.dev/mini/");
  assert.equal(
    (await worker.fetch(new Request("https://example.com/mini/"), environment(binding))).status,
    404,
  );

  const install = await worker.fetch(
    new Request("https://uni.keysi.dev/mini/install"),
    environment(binding),
  );
  assert.equal(install.status, 200);
  assert.match(install.headers.get("Content-Type") || "", /text\/x-shellscript/);
  assert.match(await install.text(), /uv.*tool install.*611f93645d40cad80959124842202dd0d9a58434/s);
});

test("guest sessions isolate plans and reject stale or unsafe writes", async () => {
  const db = database();
  const open = async () => {
    const response = await worker.fetch(
      new Request("https://uni.keysi.dev/api/session"),
      environment(assets(), db.binding),
    );
    const setCookie = response.headers.get("Set-Cookie") || "";
    return {
      session: await response.json(),
      cookie: setCookie.split(";", 1)[0],
    };
  };
  const first = await open();
  const second = await open();
  assert.match(first.cookie, /^__Host-minis_workspace=[a-f0-9]{64}$/);
  assert.notEqual(first.session.workspace, second.session.workspace);

  const request = (path: string, cookie: string, init: RequestInit = {}) =>
    worker.fetch(
      new Request(`https://uni.keysi.dev${path}`, {
        ...init,
        headers: {
          Cookie: cookie,
          Origin: "https://uni.keysi.dev",
          ...init.headers,
        },
      }),
      environment(assets(), db.binding),
    );
  const empty = await request("/api/plan", first.cookie);
  const plan = await empty.json();
  assert.equal(plan.revision, 0);

  const saved = await request("/api/plan", first.cookie, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
  assert.equal(saved.status, 200);
  assert.equal((await saved.json()).revision, 1);
  assert.equal((await request("/api/plan", second.cookie)).status, 200);
  assert.equal((await (await request("/api/plan", second.cookie)).json()).revision, 0);

  const stale = await request("/api/plan", first.cookie, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
  assert.equal(stale.status, 409);

  const invalid = await request("/api/plan", first.cookie, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...plan, settings: { buffer: -1, target: 75 } }),
  });
  assert.equal(invalid.status, 422);

  const csrf = await worker.fetch(
    new Request("https://uni.keysi.dev/api/plan", {
      method: "POST",
      headers: {
        Cookie: first.cookie,
        Origin: "https://attacker.example",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(plan),
    }),
    environment(assets(), db.binding),
  );
  assert.equal(csrf.status, 403);
});
