import { remember } from "./cache.ts";
import { api, read, request, type Failure } from "../shared/api.ts";
import { acknowledgement } from "../shared/schema.ts";
import { clipSchema, uploadSchema, type Clip } from "./model.ts";

async function retry<T>(request: () => Promise<T>, signal: AbortSignal): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    signal.throwIfAborted();
    try {
      return await request();
    } catch (caught) {
      const error = caught as Failure;
      if (signal.aborted || error.status !== 429 || attempt >= 14) throw error;
      await new Promise<void>((resolve, reject) => {
        const cancel = () => {
          clearTimeout(timer);
          reject(signal.reason);
        };
        const timer = setTimeout(
          () => {
            signal.removeEventListener("abort", cancel);
            resolve();
          },
          Math.min(5, Math.max(1, error.retryAfter || 2)) * 1000,
        );
        signal.addEventListener("abort", cancel, { once: true });
        if (signal.aborted) cancel();
      });
    }
  }
}

export function prepare(body: FormData, signal: AbortSignal) {
  return retry(() => api("/api/timey/clip", clipSchema, body, signal), signal);
}

export async function backdrop(
  source: string,
  start: number,
  signal: AbortSignal,
  ready: (clip: Clip) => void,
  quality: { height?: string; fps?: string } = {},
) {
  const body = new FormData();
  body.set("source", source);
  body.set("start", String(start));
  if (quality.height != null) body.set("height", quality.height);
  if (quality.fps != null) body.set("fps", quality.fps);
  const first = await prepare(body, signal);
  signal.throwIfAborted();
  ready({ ...first, start: first.complete ? 0 : start, source });
  if (first.kind === "image" || first.complete) return;
  body.set("complete", "on");
  const full = await prepare(body, signal);
  signal.throwIfAborted();
  ready({ ...full, start: 0, source });
}

export function preview(body: FormData, signal: AbortSignal): Promise<Blob> {
  return remember(body, signal, () =>
    retry(async () => {
      const response = await request("/api/timey/preview", { method: "POST", body, signal });
      if (response.ok) return response.blob();
      await read(response, acknowledgement);
      throw new Error("Preview couldn't update");
    }, signal),
  );
}

/** Public media links use browser CORS, never an unrestricted backend URL fetch */
export function mediaLink(value: string): string | null {
  try {
    const url = new URL(value.trim());
    return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

/** Share upload limits, cancellation and remote-file handling across the three inputs */
export async function importMedia(
  input: File | string,
  kind: "background" | "music" | "font",
  signal: AbortSignal,
) {
  const maximum = (kind === "font" ? 8 : 512) * 1024 ** 2;
  let file: File;
  if (typeof input === "string") {
    const url = mediaLink(input);
    if (!url) throw new Error("Use an HTTP or HTTPS file link, or choose a file from your device");
    let response: Response;
    try {
      response = await fetch(url, { signal, credentials: "omit", referrerPolicy: "no-referrer" });
    } catch (error) {
      signal.throwIfAborted();
      if (!(error instanceof TypeError)) throw error;
      throw new Error(
        "This site won't share the file directly. Download it, then drop or paste the file here",
      );
    }
    if (!response.ok || !response.body)
      throw new Error(
        "That file link is unavailable. Open it to check access, or choose a local copy",
      );
    const reader = response.body.getReader(),
      parts: BlobPart[] = [];
    let size = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > maximum)
          throw new Error(`Choose a ${kind === "font" ? "font under 8" : "file under 512"} MiB`);
        parts.push(value);
      }
    } finally {
      await reader.cancel();
      reader.releaseLock();
    }
    file = new File(
      [new Blob(parts)],
      decodeURIComponent(new URL(url).pathname.split("/").pop() || "media"),
      { type: response.headers.get("Content-Type") || "application/octet-stream" },
    );
  } else file = input;
  if (!file.size) throw new Error("This file is empty. Choose the original file and try again");
  if (file.size > maximum)
    throw new Error(`Choose a ${kind === "font" ? "font under 8" : "file under 512"} MiB`);
  const query = new URLSearchParams({ name: file.name });
  if (kind === "music") query.set("audio", "on");
  if (kind === "font") query.set("font", "on");
  if (file.size <= 8 * 1024 ** 2)
    return api(`/api/timey/source?${query}`, uploadSchema, file, signal);
  const key = crypto.randomUUID().replaceAll("-", "");
  const size = 8 * 1024 ** 2;
  for (let offset = 0; offset < file.size; offset += size) {
    signal.throwIfAborted();
    query.set("offset", String(offset));
    const final = offset + size >= file.size;
    if (final) query.set("final", "on");
    const response = await request(`/api/timey/parts/${key}?${query}`, {
      method: "POST",
      body: file.slice(offset, offset + size, file.type),
      signal,
    });
    if (final) return read(response, uploadSchema);
    await read(response, acknowledgement);
  }
  throw new Error("This upload was interrupted; choose the file again");
}
