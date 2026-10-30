/** Keep the university site on Pages and send only Minis traffic to its private tunnel */
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.hostname !== "uni.keysi.dev") return new Response("Not found", { status: 404 });
    if (url.pathname === "/mini" || url.pathname.startsWith("/mini/"))
      url.pathname = url.pathname.slice(5) || "/";
    else if (!/^\/(api\/|download\/|calendar\.ics$)/.test(url.pathname)) return fetch(request);
    url.hostname = "minis-origin.keysi.dev";
    try {
      return await fetch(new Request(url, request));
    } catch {
      return Response.json(
        { error: "Your workspace is reconnecting; try again shortly" },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
  },
};
