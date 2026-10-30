import type { ZodMiniType } from "zod/mini";
import { errorSchema } from "./schema.ts";
import { queries } from "./query.ts";

let account: string | undefined;
let university: string | undefined;
let prepared = false;

/** Bind requests to the account that owns the currently rendered workspace */
export function bind(workspace?: string, user?: string) {
  if (account !== workspace) {
    const key = ["private", account];
    void queries.cancelQueries({ queryKey: key });
    queries.removeQueries({ queryKey: key });
  }
  account = workspace;
  university = user;
  prepared = true;
}

/** Identify private snapshots without exposing the workspace credential */
export const scope = () => account;

/** Follow owned server jobs while preserving status, cancellation and binary responses */
export async function request(path: string, init: RequestInit = {}): Promise<Response> {
  if (
    !prepared &&
    typeof window !== "undefined" &&
    !/^\/api\/(?:session|languages|habitat|weather|brand)(?:\/|$)/.test(path) &&
    path !== "/api/minis" &&
    path !== "/api/minis/timey"
  ) {
    const { useSession } = await import("./session.ts");
    await useSession.getState().load();
    init.signal?.throwIfAborted();
    if (useSession.getState().hosted === null)
      throw new Error(useSession.getState().error || "Your workspace couldn't connect; try again");
  }
  const headers = new Headers(init.headers);
  if (account !== undefined) headers.set("X-Minis-Account", account);
  if (university) headers.set("X-Minis-User", university);
  let response = await fetch(path, { ...init, headers });
  let job = "";
  try {
    while (response.status === 202) {
      const location = response.headers.get("Location") || "";
      if (!/^\/api\/jobs\/[A-Za-z0-9_-]+$/.test(location))
        throw new Error("The task returned an invalid status link");
      job = location;
      const retry = Number(response.headers.get("Retry-After"));
      const delay = Number.isFinite(retry) ? Math.max(100, Math.min(5000, retry * 1000)) : 1000;
      await response.body?.cancel();
      await new Promise<void>((resolve, reject) => {
        const cancel = () => {
          clearTimeout(timer);
          reject(init.signal?.reason);
        };
        const timer = setTimeout(() => {
          init.signal?.removeEventListener("abort", cancel);
          resolve();
        }, delay);
        init.signal?.addEventListener("abort", cancel, { once: true });
        if (init.signal?.aborted) cancel();
      });
      response = await fetch(job, { headers, signal: init.signal });
    }
    if (
      response.status === 401 &&
      (university || (account && !account.startsWith("guest:"))) &&
      typeof location !== "undefined"
    ) {
      // A restarted gateway expires identity while the account's tab draft remains saved
      account = "";
      location.reload();
    }
    return response;
  } catch (error) {
    if (job) void fetch(job, { method: "DELETE", headers, body: "{}" }).catch(() => {});
    throw error;
  }
}

export type Failure = Error & { status?: number; retryAfter?: number };

/** Send JSON or multipart data without retrying mutations or hiding server rejections */
export async function api<T>(
  path: string,
  schema: ZodMiniType<T>,
  body?: FormData | Blob | object,
  signal?: AbortSignal,
): Promise<T> {
  const raw = body instanceof FormData || body instanceof Blob;
  const response = await request(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined || raw ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    signal,
  });
  return read(response, schema);
}

/** Reject malformed responses before publishing them to components or shared state */
export async function read<T>(response: Response, schema: ZodMiniType<T>): Promise<T> {
  let result: unknown;
  try {
    result = await response.json();
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw Object.assign(
      new Error("The server returned an unreadable response; try again shortly"),
      {
        status: response.ok ? 502 : response.status,
        retryAfter: Number(response.headers?.get("Retry-After")) || 0,
      },
    );
  }
  if (!response.ok) {
    const error = errorSchema.safeParse(result);
    throw Object.assign(
      new Error(
        (error.success && (error.data.error || error.data.detail)) ||
          "That didn't save. Try again when the connection is back",
      ),
      { status: response.status, retryAfter: Number(response.headers?.get("Retry-After")) || 0 },
    );
  }
  const checked = schema.safeParse(result);
  if (!checked.success)
    throw Object.assign(new Error("The server returned unexpected data; try again shortly"), {
      status: 502,
    });
  return checked.data;
}
