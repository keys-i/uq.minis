/** Propose supported details locally without submitting or changing saved work */
import { GB } from "chrono-node/en";
import { localInput } from "../study/dates.ts";
import type { Field } from "./schema.ts";

export function interpret(
  text: string,
  fields: Field[],
  current: Record<string, string>,
  now = new Date(),
) {
  const values: Record<string, string> = {},
    notes: string[] = [];
  const event = fields.some((field) => field.name === "event.title");
  const put = (name: string, value: string | undefined) => {
    const field = fields.find((field) => field.name === name);
    if (!field || !value) return;
    if (
      (field.min !== undefined && Number(value) < field.min) ||
      (field.max !== undefined && Number(value) > field.max) ||
      value.length > (field.maxLength || 6000)
    ) {
      notes.push(`Check ${field.label.toLowerCase()}`);
      return;
    }
    values[name] = value;
  };
  const dates = GB.parse(
    text.slice(0, 2000),
    { instant: now, timezone: 600 },
    { forwardDate: true },
  );
  const parsed =
    dates.find((item) => item.start.isCertain("day") || item.start.isCertain("weekday")) ||
    dates.find((item) => item.start.isCertain("hour"));
  if (parsed) {
    const date = parsed.start.date();
    const dated = parsed.start.isCertain("day") || parsed.start.isCertain("weekday");
    if (event) {
      if (dated) put("event.date", localInput(date.toISOString()).slice(0, 10));
      if (parsed.start.isCertain("hour"))
        put("schedule.event_start", localInput(date.toISOString()).slice(11, 16));
      if (parsed.end?.isCertain("hour"))
        put("schedule.event_end", localInput(parsed.end.date().toISOString()).slice(11, 16));
    } else if (fields.some((field) => field.name === "due")) {
      const prior = current.due || "";
      const hasPrevious =
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(prior) &&
        Number.isFinite(Date.parse(`${prior}:00+10:00`));
      if ((dated && parsed.start.isCertain("hour")) || hasPrevious) {
        let due = localInput(date.toISOString());
        if (!dated) due = `${prior.slice(0, 10)}${due.slice(10)}`;
        if (!parsed.start.isCertain("hour")) due = `${due.slice(0, 11)}${prior.slice(11)}`;
        put("due", due);
      } else notes.push(dated ? "Add a deadline time below" : "Add a deadline date below");
    }
  }
  const weight = text.match(
    /(?:worth|weight(?:ed)?(?:\s+(?:is|of|to))?|make\s+(?:it|that)|set\s+(?:it|that)\s+to)\s*(\d+(?:\.\d+)?)\s*%/i,
  );
  put("weight", weight?.[1]);
  const guests = text.match(/\b(\d+)\s*(?:people|persons?|guests?|attendees?|seats?)\b/i);
  put("attendance", guests?.[1]);
  const course = text
    .match(/\b[A-Z]{4}\s*\d{4}[A-Z]?\b/i)?.[0]
    .replace(/\s/g, "")
    .toUpperCase();
  const choice = fields
    .find((field) => field.name === "course")
    ?.options?.find(([, label]) => String(label).toUpperCase() === course);
  if (choice) put("course", String(choice[0]));
  else if (course && fields.some((field) => field.name === "course"))
    notes.push(`${course} isn't in your selected courses`);
  const renamed = text.match(
    /\b(?:rename\s+(?:it\s+)?to|call\s+it|name\s+it)\s+["“]?([^"”]+)["”]?$/i,
  )?.[1];
  if (renamed) put(event ? "event.title" : "title", renamed.trim());
  // Follow-up edits change only the named details, never an existing title or brief
  if (
    !renamed &&
    !/^(?:please\s+)?(?:change|make|set|move|actually|instead|update|also|and)\b/i.test(text)
  ) {
    const quote = text.match(/["“]([^"”]+)["”]/)?.[1];
    let title = text
      .slice(0, parsed?.index ?? text.length)
      .replace(/^(?:please\s+)?(?:add|create|plan|prepare|organise)\s+(?:an?\s+)?/i, "")
      .replace(/\b[A-Z]{4}\s*\d{4}[A-Z]?\b/gi, "")
      .split(/\b(?:worth|weight(?:ed)?|due|for\s+\d|on|at|from)\b/i)[0]
      .trim();
    title = title.replace(/\b(?:due|on|at|from)\s*$/i, "").trim();
    put(event ? "event.title" : "title", quote || title);
    if (event) {
      put("input", "new");
      put("event.summary", text);
    }
  }
  const query = fields.find((field) => field.name === "query");
  if (query) put(query.name, text);
  return { values, notes };
}
