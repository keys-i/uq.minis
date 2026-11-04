interface Assets {
  fetch(request: Request): Promise<Response>;
}

interface Environment {
  ASSETS: Assets;
}

const backendPaths = ["/api", "/download"];
const csp =
  "default-src 'self'; script-src 'self'; style-src 'self'; style-src-elem 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data: blob: https://resources.getqpay.com https://resources.hellorubric.com https://i.ytimg.com; font-src 'self' data:; media-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self' wss://uni.keysi.dev; object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";

function secured(response: Response, privateResponse = false): Response {
  const headers = new Headers(response.headers);
  headers.set("Content-Security-Policy", csp);
  headers.set("Cross-Origin-Opener-Policy", "same-origin-allow-popups");
  headers.set("Cross-Origin-Resource-Policy", "same-origin");
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()");
  headers.set("Referrer-Policy", "no-referrer");
  headers.set("Strict-Transport-Security", "max-age=31536000");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  if (privateResponse) headers.set("Cache-Control", "no-store");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function unavailable(): Response {
  return secured(
    Response.json(
      {
        error: "This workspace can't open right now. Try again shortly",
        status: "degraded",
      },
      { status: 503 },
    ),
    true,
  );
}

function assetRequest(request: Request, pathname: string): Request {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

async function minis(request: Request, environment: Environment, url: URL): Promise<Response> {
  if (url.pathname === "/mini") return secured(Response.redirect(new URL("/mini/", url), 308));
  if (request.method !== "GET" && request.method !== "HEAD")
    return secured(new Response("Method not allowed", { status: 405 }), true);

  const pathname = url.pathname.slice("/mini".length) || "/";
  const name = pathname.split("/").pop() || "";
  let response = await environment.ASSETS.fetch(
    assetRequest(request, name.includes(".") ? pathname : "/index.html"),
  );
  if (!name.includes(".")) {
    const headers = new Headers(response.headers);
    headers.set("Cache-Control", "no-cache");
    response = new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  }
  return secured(response);
}

export default {
  async fetch(request: Request, environment: Environment): Promise<Response> {
    const url = new URL(request.url);
    if (url.hostname !== "uni.keysi.dev") return new Response("Not found", { status: 404 });
    if (url.pathname === "/calendar.ics") return unavailable();
    if (backendPaths.some((path) => url.pathname === path || url.pathname.startsWith(`${path}/`)))
      return unavailable();
    if (url.pathname === "/mini" || url.pathname.startsWith("/mini/"))
      return minis(request, environment, url);
    return new Response("Not found", { status: 404 });
  },
};
