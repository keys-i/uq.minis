import { expect, test, vi } from "vitest";
import edge from "../../deploy/edge.ts";

test("the Minis edge preserves paths, queries and request bodies while leaving Pages alone", async () => {
  const sent: Request[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
    sent.push(request as Request);
    return new Response("ok");
  });
  for (const path of [
    "/mini",
    "/mini/assets/app.js",
    "/api/plan",
    "/download/opaque",
    "/calendar.ics",
  ]) {
    const request = new Request(`https://uni.keysi.dev${path}?key=opaque`, {
      method: "POST",
      body: "data",
      headers: { Origin: "https://uni.keysi.dev" },
    });
    expect((await edge.fetch(request)).status).toBe(200);
    const proxied = sent.at(-1)!;
    expect(new URL(proxied.url).hostname).toBe("minis-origin.keysi.dev");
    expect(new URL(proxied.url).pathname).toBe(
      path.startsWith("/mini") ? path.slice(5) || "/" : path,
    );
    expect(new URL(proxied.url).search).toBe("?key=opaque");
    expect(proxied.headers.get("Origin")).toBe("https://uni.keysi.dev");
    expect(await proxied.text()).toBe("data");
  }
  const page = new Request("https://uni.keysi.dev/notes");
  await edge.fetch(page);
  expect(sent.at(-1)).toBe(page);
  expect((await edge.fetch(new Request("https://other.test/mini"))).status).toBe(404);
});
