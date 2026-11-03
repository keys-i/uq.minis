import { webcrypto } from "node:crypto";
import { afterEach, expect, test, vi } from "vitest";
import { useSession } from "../src/shared/session.ts";
import { remember } from "../src/timey/cache.ts";

afterEach(() => useSession.setState({ hosted: null, user: null }));

const body = () => {
  const form = new FormData();
  form.set("style", "minimal");
  return form;
};

function memoryCache() {
  const store = new Map<string, Response>();
  return {
    store,
    cache: {
      match: async (key: string | Request) =>
        store.get(typeof key === "string" ? key : key.url)?.clone(),
      put: async (key: string, value: Response) => {
        store.set(key, value.clone());
      },
      keys: async () => [...store.keys()].map((key) => new Request(key)),
      delete: async (key: string | Request) =>
        store.delete(typeof key === "string" ? key : key.url),
    },
  };
}

test("blocked browser storage never prevents rendering", async () => {
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("location", new URL("https://local.test"));
  vi.stubGlobal("caches", {
    open: async () => {
      throw new DOMException("Storage blocked", "SecurityError");
    },
  });
  const create = vi.fn(async () => new Blob(["preview"], { type: "image/png" }));
  expect(await (await remember(body(), new AbortController().signal, create)).text()).toBe(
    "preview",
  );
  expect(create).toHaveBeenCalledOnce();
});

test.each([false, true])(
  "preview cache isolates accounts and stays bounded (hosted=%s)",
  async (hosted) => {
    useSession.setState({ hosted, user: "a@uq.edu.au", workspace: "a@uq.edu.au" });
    vi.stubGlobal("crypto", webcrypto);
    vi.stubGlobal("location", new URL("https://local.test"));
    const { store, cache } = memoryCache();
    for (let index = 0; index < 26; index++)
      store.set(
        `https://local.test/old-${index}`,
        new Response("old", { headers: { "X-Size": "3" } }),
      );
    vi.stubGlobal("caches", {
      open: async () => cache,
    });
    const create = vi.fn(async () => new Blob(["preview"], { type: "image/png" }));
    await remember(body(), new AbortController().signal, create);
    await vi.waitFor(() => expect(store.size).toBe(24));
    expect(await (await remember(body(), new AbortController().signal, create)).text()).toBe(
      "preview",
    );
    expect(create).toHaveBeenCalledOnce();
    if (hosted) {
      useSession.setState({ user: "b@uq.edu.au", workspace: "b@uq.edu.au" });
      await remember(body(), new AbortController().signal, create);
      expect(create).toHaveBeenCalledTimes(2);
    }
    const controller = new AbortController();
    controller.abort();
    await expect(remember(body(), controller.signal, create)).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(create).toHaveBeenCalledTimes(hosted ? 2 : 1);
  },
);

test("preview meaning controls reuse and invalidation", async () => {
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("location", new URL("https://local.test"));
  const { store, cache } = memoryCache();
  const retire = vi.fn(async () => true);
  vi.stubGlobal("caches", { open: async () => cache, delete: retire });
  const create = vi.fn(
    async () => new Blob([String(create.mock.calls.length)], { type: "image/png" }),
  );
  const first = new FormData();
  first.set("style", "minimal");
  first.set("label", "Starting soon");
  const reordered = new FormData();
  reordered.set("label", "Starting soon");
  reordered.set("style", "minimal");
  const changed = new FormData();
  changed.set("style", "minimal");
  changed.set("label", "Welcome");
  await remember(first, new AbortController().signal, create);
  await vi.waitFor(() => expect(store.size).toBe(1));
  await remember(reordered, new AbortController().signal, create);
  await remember(changed, new AbortController().signal, create);
  expect(create).toHaveBeenCalledTimes(2);
  expect(retire).toHaveBeenCalledWith("minis-timey-previews-v1");
});

test("a stalled cache body falls back to rendering", async () => {
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("location", new URL("https://local.test"));
  const hit = new Response("stored", {
    headers: { "Content-Type": "image/png", "X-Saved": String(Date.now()) },
  });
  vi.spyOn(hit, "blob").mockImplementation(() => new Promise<Blob>(() => {}));
  vi.stubGlobal("caches", {
    open: async () => ({
      match: async () => hit,
      delete: async () => false,
      put: async () => {},
      keys: async () => [],
    }),
  });
  const create = vi.fn(async () => new Blob(["fresh"], { type: "image/png" }));
  expect(await (await remember(body(), new AbortController().signal, create)).text()).toBe("fresh");
  expect(create).toHaveBeenCalledOnce();
});
