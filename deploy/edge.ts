interface Assets {
  fetch(request: Request): Promise<Response>;
}

interface D1Statement {
  bind(...values: unknown[]): D1Statement;
  first<T>(): Promise<T | null>;
}

interface D1Database {
  prepare(statement: string): D1Statement;
}

interface Environment {
  ASSETS: Assets;
  DB: D1Database;
}

type Plan = Record<string, unknown> & {
  revision: number;
  settings: Record<string, unknown>;
  courses: Array<Record<string, unknown>>;
  assessments: Array<Record<string, unknown>>;
  announcements: Array<Record<string, unknown>>;
};

const COOKIE = "__Host-minis_workspace";
const OWNER = /^guest:[a-f0-9]{64}$/;
const TOKEN = /^[a-f0-9]{64}$/;
const ID = /^[A-Za-z0-9_:-]{1,120}$/;
const COURSE = /^[A-Z]{4}\d{4}[A-Z]?$/;
const csp =
  "default-src 'self'; script-src 'self'; style-src 'self'; style-src-elem 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data: blob: https://resources.getqpay.com https://resources.hellorubric.com https://i.ytimg.com; font-src 'self' data:; media-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self' wss://uni.keysi.dev; object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
const catalogue = {
  scrappy: { title: "Scrappy", about: "Choose courses and explore their profiles" },
  planny: { title: "Planny", about: "Assessments, personal targets and marks" },
  buzzy: { title: "Buzzy", about: "Deadlines and society events in one calendar" },
  clubby: { title: "Clubby", about: "Find clubs and collect scheduled events" },
  event: { title: "Eventy", about: "Prepare events and follow booking replies" },
  timey: { title: "Timey", about: "Make a countdown video" },
};
const emptyPlan = (): Plan => ({
  revision: 0,
  updated: new Date().toISOString(),
  settings: { buffer: 2, target: 75, following: [], completed: [], skills: "" },
  courses: [],
  assessments: [],
  announcements: [],
});
const installer = `#!/bin/sh
set -eu

if command -v uv >/dev/null 2>&1; then
  UV=uv
elif [ -x "\${HOME}/.local/bin/uv" ]; then
  UV="\${HOME}/.local/bin/uv"
else
  echo "Installing uv from Astral's official installer"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  UV="\${HOME}/.local/bin/uv"
fi

"\${UV}" tool install --upgrade --python 3.15 'uq-minis[agent,browser,timey] @ git+https://github.com/keys-i/uq.minis.git@92631d86d84b75e744c15ff08d53cffe761936d8#subdirectory=backend'
echo "Installed UQ Minis. Run: mini list"
`;

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

function json(value: unknown, status = 200, headers?: HeadersInit): Response {
  return secured(Response.json(value, { status, headers }), true);
}

function failure(error: string, status: number): Response {
  return json({ error }, status);
}

function assetRequest(request: Request, pathname: string): Request {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

function cookie(request: Request): string {
  const values = request.headers.get("Cookie") || "";
  for (const entry of values.split(";")) {
    const [name, value] = entry.trim().split("=", 2);
    if (name === COOKIE && TOKEN.test(value || "")) return value;
  }
  return "";
}

async function workspace(token: string): Promise<string> {
  if (!TOKEN.test(token)) return "";
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  const value = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `guest:${value}`;
}

async function owner(request: Request): Promise<string> {
  return workspace(cookie(request));
}

async function session(request: Request): Promise<Response> {
  const current = cookie(request);
  const token = current || Array.from(crypto.getRandomValues(new Uint8Array(32)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  const headers = current
    ? undefined
    : {
        "Set-Cookie": `${COOKIE}=${token}; Max-Age=31536000; Path=/; Secure; HttpOnly; SameSite=Lax`,
      };
  return json(
    { configured: true, user: "", hosted: true, workspace: await workspace(token) },
    200,
    headers,
  );
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeText(value: unknown, maximum: number): value is string {
  return typeof value === "string" && value.length <= maximum;
}

function safeLink(value: unknown): boolean {
  if (value === undefined || value === "") return true;
  if (!safeText(value, 2048)) return false;
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

function validPlan(value: unknown): value is Plan {
  if (!record(value) || !Number.isSafeInteger(value.revision) || Number(value.revision) < 0)
    return false;
  if (!record(value.settings)) return false;
  const buffer = value.settings.buffer;
  const target = value.settings.target;
  if (
    typeof buffer !== "number" ||
    !Number.isFinite(buffer) ||
    buffer < 0 ||
    buffer > 30 ||
    typeof target !== "number" ||
    !Number.isFinite(target) ||
    target < 0 ||
    target > 100
  )
    return false;
  if (
    !Array.isArray(value.courses) ||
    !Array.isArray(value.assessments) ||
    !Array.isArray(value.announcements) ||
    value.courses.length > 100 ||
    value.assessments.length > 5000 ||
    value.announcements.length > 5000
  )
    return false;
  const ids = new Set<string>();
  const courses = new Set<string>();
  for (const item of value.courses) {
    if (
      !record(item) ||
      !safeText(item.id, 120) ||
      !ID.test(item.id) ||
      ids.has(item.id) ||
      !safeText(item.code, 20) ||
      !COURSE.test(item.code.toUpperCase()) ||
      !safeText(item.name, 300) ||
      !item.name ||
      !safeLink(item.profile)
    )
      return false;
    ids.add(item.id);
    courses.add(item.id);
  }
  for (const item of value.assessments) {
    if (
      !record(item) ||
      !safeText(item.id, 120) ||
      !ID.test(item.id) ||
      ids.has(item.id) ||
      !safeText(item.title, 300) ||
      !item.title ||
      !safeText(item.course, 120) ||
      !courses.has(item.course) ||
      typeof item.weight !== "number" ||
      !Number.isFinite(item.weight) ||
      !safeLink(item.url)
    )
      return false;
    ids.add(item.id);
  }
  for (const item of value.announcements) {
    if (
      !record(item) ||
      !safeText(item.id, 120) ||
      !ID.test(item.id) ||
      ids.has(item.id) ||
      !safeText(item.title, 300) ||
      !item.title ||
      !safeLink(item.url) ||
      !safeLink(item.club_url) ||
      !safeLink(item.banner) ||
      !safeLink(item.logo)
    )
      return false;
    ids.add(item.id);
  }
  return true;
}

async function readPlan(database: D1Database, account: string): Promise<Plan> {
  const row = await database
    .prepare("SELECT data FROM plans WHERE workspace = ?")
    .bind(account)
    .first<{ data: string }>();
  if (!row) return emptyPlan();
  const value: unknown = JSON.parse(row.data);
  if (!validPlan(value)) throw new Error("Stored plan failed validation");
  return value;
}

async function savePlan(database: D1Database, account: string, request: Request): Promise<Response> {
  if (!request.headers.get("Content-Type")?.toLowerCase().startsWith("application/json"))
    return failure("Send planner changes as JSON", 415);
  const size = Number(request.headers.get("Content-Length") || "0");
  if (size > 2 * 1024 * 1024) return failure("A planner can contain at most 2 MiB", 413);
  let value: unknown;
  try {
    value = await request.json();
  } catch {
    return failure("The planner changes are not valid JSON", 400);
  }
  if (!validPlan(value)) return failure("Check the planner fields and try again", 422);
  const next = structuredClone(value);
  const expected = next.revision;
  next.revision += 1;
  next.updated = new Date().toISOString();
  const data = JSON.stringify(next);
  if (data.length > 2 * 1024 * 1024) return failure("A planner can contain at most 2 MiB", 413);
  const saved = await database
    .prepare(
      "INSERT INTO plans (workspace, revision, data, updated_at) SELECT ?, 1, ?, unixepoch() WHERE ? = 0 ON CONFLICT(workspace) DO UPDATE SET revision = plans.revision + 1, data = ?, updated_at = unixepoch() WHERE plans.revision = ? RETURNING revision",
    )
    .bind(account, data, expected, data, expected)
    .first<{ revision: number }>();
  return saved ? json(next) : failure("Another tab changed the plan; reload before saving", 409);
}

async function api(request: Request, environment: Environment, url: URL): Promise<Response> {
  if (url.pathname === "/api/health" && request.method === "GET")
    return json({ status: "ok", service: "uq-minis-edge" });
  if (url.pathname === "/api/minis" && request.method === "GET") return json(catalogue);
  if (url.pathname === "/api/languages" && request.method === "GET")
    return json({ languages: { en: "English" }, configured: false });
  if (url.pathname === "/api/session" && request.method === "GET") return session(request);
  if (url.pathname === "/api/session/logout" && request.method === "POST") return session(request);

  const account = await owner(request);
  if (!OWNER.test(account)) return failure("Open Minis before using your private workspace", 401);
  if (url.pathname === "/api/plan" && request.method === "GET")
    return json(await readPlan(environment.DB, account));
  if (url.pathname === "/api/plan" && request.method === "POST")
    return savePlan(environment.DB, account, request);
  if (url.pathname === "/api/backup" && request.method === "GET") {
    const response = json(await readPlan(environment.DB, account));
    const headers = new Headers(response.headers);
    headers.set("Content-Disposition", 'attachment; filename="planny-backup.json"');
    return new Response(response.body, { status: response.status, headers });
  }
  return failure(
    "This action needs the Minis CLI on your computer. Install it from /mini/install",
    501,
  );
}

function install(request: Request): Response {
  const headers = new Headers({
    "Content-Type": "text/x-shellscript; charset=utf-8",
    "Content-Disposition": 'inline; filename="install-uq-minis.sh"',
    "Cache-Control": "public, max-age=300",
  });
  return secured(new Response(request.method === "HEAD" ? null : installer, { headers }));
}

async function minis(request: Request, environment: Environment, url: URL): Promise<Response> {
  if (url.pathname === "/mini") return secured(Response.redirect(new URL("/mini/", url), 308));
  if (url.pathname === "/mini/install") {
    if (request.method !== "GET" && request.method !== "HEAD")
      return secured(new Response("Method not allowed", { status: 405 }), true);
    return install(request);
  }
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
    if (url.pathname === "/mini" || url.pathname.startsWith("/mini/"))
      return minis(request, environment, url);
    if (
      url.pathname === "/api" ||
      url.pathname.startsWith("/api/") ||
      url.pathname === "/download" ||
      url.pathname.startsWith("/download/") ||
      url.pathname === "/calendar.ics"
    ) {
      if (
        request.method !== "GET" &&
        request.method !== "HEAD" &&
        request.headers.get("Origin") !== "https://uni.keysi.dev"
      )
        return failure("Open Minis before changing data", 403);
      try {
        return await api(request, environment, url);
      } catch {
        return failure("Your workspace couldn't finish that request; try again", 500);
      }
    }
    return new Response("Not found", { status: 404 });
  },
};
