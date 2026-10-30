import { planSchema, sourceSchema, toolsSchema } from "./model.ts";
import { useSession } from "../shared/session.ts";
import { create } from "zustand";
import { queries } from "../shared/query.ts";
import { api, scope } from "../shared/api.ts";
import type { Change, Plan, Tools, SourceResult } from "./model.ts";
import catalogue from "../../../out/tools/minis.json";

interface Study {
  plan: Plan | null;
  tools: Tools;
  saving: boolean;
  catalogue: (signal?: AbortSignal) => Promise<void>;
  load: (signal?: AbortSignal) => Promise<void>;
  change: Change;
  source: (path: string, body?: object) => Promise<SourceResult>;
}

/** Own the saved plan and serialise every edit against the latest server revision */
export const useStudy = create<Study>((set, get) => {
  let queue = Promise.resolve();
  let loading: Promise<void> | undefined;
  let loadingSignal: AbortSignal | undefined;
  function publish(plan: Plan, owner = scope()) {
    if (scope() !== owner) return;
    queries.setQueryData(["private", owner, "plan"], plan);
    set({ plan });
    try {
      const raw = JSON.stringify(plan),
        key = `minis.plan.${owner || "local"}`;
      if (raw.length <= 2 * 1024 * 1024) sessionStorage.setItem(key, raw);
      else sessionStorage.removeItem(key);
    } catch {
      /* Storage is an optional shortcut */
    }
  }

  // Imports and ordinary edits share one queue so neither can overwrite a newer revision
  function commit<T>(operation: () => Promise<T>): Promise<T> {
    const owner = scope();
    const result = queue.then(async () => {
      if (owner !== scope())
        throw new Error("Your workspace changed; reload this tab before continuing");
      set({ saving: true });
      try {
        await loading;
        if (owner !== scope())
          throw new Error("Your workspace changed; reload this tab before continuing");
        const result = await operation();
        if (scope() !== owner)
          throw new Error("Your workspace changed; reload this tab before continuing");
        return result;
      } finally {
        set({ saving: false });
      }
    });
    // A rejected save must reach its caller without blocking the person's next edit
    queue = result.then(
      () => {},
      () => {},
    );
    return result;
  }

  return {
    plan: null,
    // The public shelf paints before any connection or identity check completes
    tools: catalogue,
    saving: false,
    async catalogue(signal) {
      const tools = await queries.fetchQuery({
        queryKey: ["minis"],
        queryFn: ({ signal: cancel }) =>
          api(
            "/api/minis",
            toolsSchema,
            undefined,
            signal ? AbortSignal.any([signal, cancel]) : cancel,
          ),
      });
      if (!signal?.aborted) set({ tools });
    },
    async load(signal) {
      if (loading) {
        const previous = loadingSignal;
        await loading;
        if (previous?.aborted && !signal?.aborted) return get().load(signal);
        return;
      }
      if (get().saving) await queue;
      const owner = scope();
      const cached = queries.getQueryData<Plan>(["private", owner, "plan"]);
      if (cached) set({ plan: cached });
      else {
        try {
          const raw = sessionStorage.getItem(`minis.plan.${owner || "local"}`);
          if (raw && raw.length <= 2 * 1024 * 1024) {
            const checked = planSchema.safeParse(JSON.parse(raw));
            if (checked.success) set({ plan: checked.data });
          }
        } catch {
          /* Server revalidation works without browser storage */
        }
      }
      loadingSignal = signal;
      loading = queries
        .fetchQuery({
          queryKey: ["private", owner, "plan"],
          staleTime: 30_000,
          queryFn: ({ signal: cancel }) =>
            api(
              "/api/plan",
              planSchema,
              undefined,
              signal ? AbortSignal.any([signal, cancel]) : cancel,
            ),
        })
        .then((plan) => {
          if (!signal?.aborted && owner === scope()) publish(plan, owner);
        })
        .catch((error) => {
          if (!signal?.aborted) throw error;
        })
        .finally(() => {
          loading = undefined;
        });
      return loading;
    },
    change(edit) {
      return commit(async () => {
        const current = get().plan;
        if (!current) throw new Error("Your plan is still loading; try again shortly");
        const draft = structuredClone(current);
        edit(draft);
        const owner = scope();
        const accepted = await api("/api/plan", planSchema, draft);
        publish(accepted, owner);
      });
    },
    source(path, body = {}) {
      return commit(async () => {
        const owner = scope();
        const result = await api(path, sourceSchema, body);
        if ("revision" in result) publish(result, owner);
        return result;
      });
    },
  };
});

// A new owner must never inherit the previous workspace's in-memory document
const unsubscribe = useSession.subscribe((state, previous) => {
  if (state.workspace !== previous.workspace) useStudy.setState({ plan: null });
});
if (import.meta.hot) import.meta.hot.dispose(unsubscribe);
