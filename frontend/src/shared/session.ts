import { sessionSchema } from "./schema.ts";
import { create } from "zustand";
import { api, bind } from "./api.ts";

interface Session {
  user: string | null;
  error: string;
  hosted: boolean | null;
  workspace: string | null;
  load: () => Promise<void>;
  complete: (user: string) => void;
  logout: () => Promise<void>;
}

/** Share verified access across gates; opening a sign-in window stays local to its initiator */
export const useSession = create<Session>((set, get) => {
  let pending: Promise<void> | null = null;
  let controller: AbortController | null = null;
  return {
    user: null,
    error: "",
    hosted: null,
    workspace: null,
    load() {
      if (pending) return pending;
      if (get().user !== null) return Promise.resolve();
      controller = new AbortController();
      const active = controller;
      pending = api("/api/session", sessionSchema, undefined, active.signal)
        .then((result) => {
          if (!active.signal.aborted) {
            const workspace = result.hosted ? result.workspace || result.user : null;
            bind(workspace ?? undefined, result.user);
            set({ user: result.user, workspace, error: "", hosted: !!result.hosted });
          }
        })
        .catch((error) => {
          if (!active.signal.aborted) set({ error: error.message });
        })
        .finally(() => {
          if (controller === active) {
            pending = null;
            controller = null;
          }
        });
      return pending;
    },
    complete(user) {
      // An older status response must not undo a sign-in that completed while it was loading
      controller?.abort();
      controller = null;
      pending = null;
      if (get().hosted) bind(get().workspace || user, user);
      set({ user, error: "" });
    },
    async logout() {
      try {
        await api("/api/session/logout", sessionSchema, {});
        if (get().hosted) {
          try {
            localStorage.setItem("minis-account", "");
          } catch {
            /* Storage is optional */
          }
          location.reload();
        } else get().complete("");
      } catch (error) {
        set({ error: (error as Error).message });
      }
    },
  };
});
