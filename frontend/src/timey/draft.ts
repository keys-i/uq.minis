/** Keep the editable project alive across stage changes and an in-site sign-in */
import { create } from "zustand";
import * as z from "zod/mini";
import { useSession } from "../shared/session.ts";
import { resultSchema } from "../shared/schema.ts";
import type { Values } from "./model.ts";

export const timerResultSchema = z.extend(resultSchema, {
  questions: z.optional(z.array(z.string())),
  design: z.optional(z.object({ id: z.string(), name: z.string() })),
});
const draftSchema = z.object({
  values: z.record(z.string(), z.string()),
  shared: z.catch(z.nullable(z.object({ code: z.string(), revision: z.number() })), null),
  recovery: z.catch(z.nullable(z.record(z.string(), z.string())), null),
  phase: z.enum(["edit", "preview", "video"]),
  questions: z.catch(z.array(z.string()), []),
  movie: z.nullable(
    z.object({
      phase: z.enum(["preview", "video"]),
      quality: z.string(),
      data: timerResultSchema,
    }),
  ),
});
export type Draft = z.infer<typeof draftSchema>;

function key() {
  const { hosted, workspace } = useSession.getState();
  if (hosted === null || (hosted && !workspace)) return null;
  return hosted ? `minis-timey-draft:${workspace}` : "minis-timey-draft";
}

let active = key();

function restore(): Draft {
  try {
    const saved = draftSchema.safeParse(
      JSON.parse(active ? sessionStorage.getItem(active) || "null" : "null"),
    );
    if (saved.success) return saved.data;
  } catch {
    // Blocked storage never prevents editing or holding a draft in memory
  }
  return { values: {}, phase: "edit", movie: null, questions: [], shared: null, recovery: null };
}
export const useDraft = create<Draft>(() => restore());
useDraft.subscribe((draft) => {
  if (!active) return;
  try {
    sessionStorage.setItem(active, JSON.stringify(draft));
  } catch {
    /* The in-memory project remains usable if tab storage fills or is denied */
  }
});
useSession.subscribe(() => {
  const next = key();
  if (next === active) return;
  const editing = active === null ? useDraft.getState().values : {};
  active = next;
  const saved = restore();
  useDraft.setState({ ...saved, values: { ...saved.values, ...editing } });
});
export function setValues(next: Values | ((current: Values) => Values)) {
  useDraft.setState((draft) => ({
    values: typeof next === "function" ? next(draft.values) : next,
  }));
}
