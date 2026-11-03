import type { Field, Schema } from "./schema.ts";

const VERSION = 2;
const LIMIT = 128 * 1024;
const FORBIDDEN =
  /password|passcode|token|secret|oauth|device.?code|consent|confirm|authori[sz]|credential|username|login|mailbox|client.?id|tenant.?id|state.?dir/i;

type Values = Record<string, string>;

interface DraftEnvelope {
  version: typeof VERSION;
  workspace: string;
  mini: string;
  form: "main";
  schema: string;
  savedAt: string;
  values: Values;
}

function hash(value: string) {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

export function fingerprint(schema: Schema) {
  return hash(
    JSON.stringify(
      schema.fields.map(({ name, type, min, max, step, maxLength, required, options, when }) => ({
        name,
        type,
        min,
        max,
        step,
        maxLength,
        required,
        options,
        when,
      })),
    ),
  );
}

function scope(workspace: string) {
  return hash(workspace || "local");
}

function key(workspace: string, mini: string) {
  return `minis.draft.v2:${scope(workspace)}:${mini}`;
}

function editable(field: Field) {
  return !["file", "password", "hidden"].includes(field.type || "") && !FORBIDDEN.test(field.name);
}

function filtered(schema: Schema, values: Values) {
  const names = new Set(schema.fields.filter(editable).map((field) => field.name));
  return Object.fromEntries(
    Object.entries(values).filter(
      ([name, value]) => names.has(name) && typeof value === "string" && value.length <= 6000,
    ),
  );
}

export function restoreDraft(workspace: string, mini: string, schema: Schema, fallback: Values) {
  try {
    const raw = localStorage.getItem(key(workspace, mini));
    if (!raw || raw.length > LIMIT) return { values: fallback, found: false };
    const saved = JSON.parse(raw) as Partial<DraftEnvelope>;
    const valid =
      saved.version === VERSION &&
      saved.workspace === scope(workspace) &&
      saved.mini === mini &&
      saved.form === "main" &&
      saved.schema === fingerprint(schema) &&
      saved.values &&
      typeof saved.values === "object";
    if (!valid) {
      localStorage.removeItem(key(workspace, mini));
      return { values: fallback, found: false };
    }
    return { values: { ...fallback, ...filtered(schema, saved.values as Values) }, found: true };
  } catch {
    return { values: fallback, found: false };
  }
}

export function saveDraft(workspace: string, mini: string, schema: Schema, values: Values) {
  try {
    const envelope: DraftEnvelope = {
      version: VERSION,
      workspace: scope(workspace),
      mini,
      form: "main",
      schema: fingerprint(schema),
      savedAt: new Date().toISOString(),
      values: filtered(schema, values),
    };
    const raw = JSON.stringify(envelope);
    if (raw.length <= LIMIT) localStorage.setItem(key(workspace, mini), raw);
  } catch {
    // Browser storage is optional
  }
}

export function clearDraft(workspace: string, mini: string) {
  try {
    localStorage.removeItem(key(workspace, mini));
  } catch {
    // Browser storage is optional
  }
}

export function autocomplete(field: Field) {
  if (field.autocomplete) return field.autocomplete;
  const name = field.name.toLowerCase().replaceAll(/[._-]/g, " ");
  if (FORBIDDEN.test(name)) return "off";
  if (/e ?mail/.test(name)) return "email";
  if (/given|first name/.test(name)) return "given-name";
  if (/family|surname|last name/.test(name)) return "family-name";
  if (/full name|contact name|^name$/.test(name)) return "name";
  if (/organisation|organization|society|club/.test(name)) return "organization";
  if (/phone|mobile|telephone|^tel$/.test(name)) return "tel";
  if (/post ?code|postal/.test(name)) return "postal-code";
  if (/country/.test(name)) return "country-name";
  if (/street|address/.test(name)) return "street-address";
  if (/\burl\b|website/.test(name)) return "url";
  return "off";
}
