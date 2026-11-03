/** Optional bounded preview storage accelerates revisits without owning accepted state */
import { useSession } from "../shared/session.ts";

const version = "timey-preview-v2",
  shelf = "minis-timey-previews",
  retired = "minis-timey-previews-v1",
  limit = 24,
  bytes = 24 * 1024 ** 2;
let writing = false,
  migrated = false;

async function save(cache: Cache, key: string, result: Blob) {
  if (writing || result.size > 2 * 1024 ** 2) return;
  writing = true;
  try {
    await cache.delete(key);
    await cache.put(
      key,
      new Response(result, {
        headers: {
          "Content-Type": result.type,
          "X-Saved": String(Date.now()),
          "X-Size": String(result.size),
        },
      }),
    );
    const keys = await cache.keys();
    let total = 0,
      kept = 0;
    for (const request of keys.toReversed()) {
      const entry = await cache.match(request);
      total += Number(entry?.headers.get("X-Size")) || 0;
      if (++kept > limit || total > bytes) await cache.delete(request);
    }
  } catch {
    // Quota changes and blocked storage never prevent the preview from appearing
  } finally {
    writing = false;
  }
}

export async function remember(
  body: FormData,
  signal: AbortSignal,
  create: () => Promise<Blob>,
): Promise<Blob> {
  let cache: Cache | undefined,
    key = "";
  if (typeof caches !== "undefined" && typeof crypto?.subtle !== "undefined") {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const lookup = async () => {
        const entries = [...body.entries()].sort(([a], [b]) => a.localeCompare(b));
        if (entries.some(([, value]) => typeof value !== "string")) return;
        const owner = useSession.getState();
        const digest = await crypto.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(
            JSON.stringify(owner.hosted ? [version, owner.workspace, entries] : [version, entries]),
          ),
        );
        key = `${location.origin}/__timey/preview/${Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("")}`;
        cache = await caches.open(shelf);
        if (!migrated && typeof caches.delete === "function") {
          migrated = true;
          void caches.delete(retired).catch(() => false);
        }
        const hit = await cache.match(key);
        if (
          hit &&
          (hit.headers.get("Content-Type") || "").startsWith("image/") &&
          Date.now() - Number(hit.headers.get("X-Saved")) < 86400000
        )
          return hit.blob();
      };
      const hit = await Promise.race([
        lookup(),
        new Promise<undefined>((resolve) => {
          timer = setTimeout(() => resolve(undefined), 120);
        }),
      ]);
      signal.throwIfAborted();
      if (hit) return hit;
    } catch {
      signal.throwIfAborted();
      cache = undefined;
    } finally {
      clearTimeout(timer);
    }
  }
  const result = await create();
  signal.throwIfAborted();
  if (cache) void save(cache, key, result);
  return result;
}
