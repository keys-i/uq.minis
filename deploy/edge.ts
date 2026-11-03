/** Keep the university site on Pages and send only exact service paths to the private tunnel */
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.hostname !== "uni.keysi.dev") return new Response("Not found", { status: 404 });
    const minis =
      url.pathname === "/mini" ||
      url.pathname.startsWith("/mini/") ||
      url.pathname === "/api" ||
      url.pathname.startsWith("/api/") ||
      url.pathname === "/download" ||
      url.pathname.startsWith("/download/") ||
      url.pathname === "/calendar.ics";
    const society = url.pathname === "/soc" || url.pathname.startsWith("/soc/");
    if (!minis && !society) return fetch(request);
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
