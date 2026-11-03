/** Runtime contracts shared by forms, transport and the private sign-in window */
import * as z from "zod/mini";

export const acknowledgement = z.object({});
export const errorSchema = z.object({
  error: z.optional(z.string()),
  detail: z.optional(z.string()),
});
export const sessionSchema = z.object({
  user: z.union([z.literal(""), z.email()]),
  hosted: z.optional(z.boolean()),
  workspace: z.optional(
    z.union([z.literal(""), z.email(), z.string().check(z.regex(/^guest:[a-f0-9]{64}$/))]),
  ),
  window: z.optional(z.literal("/api/session/window")),
});
export const languagesSchema = z.object({
  languages: z.record(z.string(), z.string()),
  configured: z.boolean(),
  provider: z.optional(z.string()),
});
export const translationSchema = z.object({ text: z.string() });
export const downloadSchema = z.object({ name: z.string(), url: z.string() });
export const resultSchema = z.object({
  result: z.string(),
  downloads: z.optional(z.array(downloadSchema)),
});
export const fieldSchema = z.object({
  name: z.string(),
  type: z.optional(z.string()),
  label: z.string(),
  group: z.optional(z.string()),
  value: z.optional(z.union([z.string(), z.number()])),
  checked: z.optional(z.boolean()),
  min: z.optional(z.number()),
  max: z.optional(z.number()),
  step: z.optional(z.number()),
  maxLength: z.optional(z.number()),
  autocomplete: z.optional(z.string()),
  required: z.optional(z.boolean()),
  options: z.optional(z.array(z.tuple([z.union([z.string(), z.number()]), z.string()]))),
  when: z.optional(z.record(z.string(), z.array(z.string()))),
  help: z.optional(z.string()),
});
export const formSchema = z.object({
  fields: z.array(fieldSchema),
  submit: z.optional(z.string()),
});
export const miniSchema = z.extend(formSchema, {
  about: z.optional(z.string()),
  result: z.optional(z.string()),
  note: z.optional(z.string()),
  image: z.optional(z.string()),
  downloads: z.optional(z.array(downloadSchema)),
  rows: z.optional(
    z.array(z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()]))),
  ),
  columns: z.optional(z.array(z.string())),
});
export const roomsSchema = z.object({
  rows: z.array(
    z.object({
      campus: z.string(),
      room: z.string(),
      seats: z.number(),
      building: z.string(),
      kind: z.string(),
      photo: z.optional(z.string()),
      tour: z.optional(z.string()),
    }),
  ),
  total: z.number(),
  maximum: z.number(),
});
const controlSchema = z.object({
  id: z.string(),
  type: z.string(),
  label: z.string(),
  x: z.number(),
  y: z.number(),
  width: z.number().check(z.positive()),
  height: z.number().check(z.positive()),
  disabled: z.boolean(),
  checked: z.boolean(),
  options: z
    .array(z.object({ value: z.string(), label: z.string(), selected: z.boolean() }))
    .check(z.maxLength(64)),
});
export const portalViewSchema = z.object({
  mode: z.optional(z.enum(["form", "window"])),
  image: z.string().check(z.maxLength(2 * 1024 ** 2)),
  host: z.string(),
  title: z.string(),
  text: z.string(),
  width: z.number().check(z.positive()),
  height: z.number().check(z.positive()),
  controls: z.array(controlSchema).check(z.maxLength(64)),
});
export const portalSchema = z.union([
  z.object({ user: z.email() }),
  z.object({ error: z.string() }),
  portalViewSchema,
]);
export const connectionSchema = z.union([
  z.object({ connected: z.literal(true) }),
  z.object({ acknowledged: z.literal(true) }),
  z.object({ error: z.string() }),
  portalViewSchema,
]);
export const preferencesSchema = z.object({
  still: z.catch(z.boolean(), false),
  contrast: z.catch(z.boolean(), false),
  sound: z.catch(z.boolean(), false),
  size: z.catch(z.union([z.literal(1), z.literal(1.1), z.literal(1.2), z.literal(1.3)]), 1),
  theme: z.catch(z.enum(["light", "dark", "system"]), "system"),
});

export type Field = z.infer<typeof fieldSchema>;
export type Schema = z.infer<typeof formSchema>;
export type MiniResult = z.infer<typeof miniSchema>;
export type Preferences = z.infer<typeof preferencesSchema>;
export type PortalView = z.infer<typeof portalViewSchema>;
export type PortalMessage = z.infer<typeof portalSchema>;
export type Room = z.infer<typeof roomsSchema>["rows"][number];
