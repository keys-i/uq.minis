import type { Assessment, Announcement, Plan } from "./model.ts";

type Moment = string | Date | number | null | undefined;
export type CalendarEvent =
  | (Assessment & { kind: "official" | "personal"; when: string; label: string })
  | (Announcement & { kind: "club"; when: string; label: string });

export const DAY = 86400000;
const BRISBANE = 10 * 60 * 60 * 1000;
export const format = (value: Moment, options: Intl.DateTimeFormatOptions = {}) =>
  value
    ? new Intl.DateTimeFormat("en-AU", {
        day: "numeric",
        month: "short",
        ...options,
        timeZone: "Australia/Brisbane",
      }).format(new Date(value))
    : "Date needs review";
export const localInput = (value: string | null | undefined) =>
  value ? new Date(new Date(value).getTime() + BRISBANE).toISOString().slice(0, 16) : "";
export const timestamp = (value: FormDataEntryValue | null | undefined) => {
  const local = String(value || "");
  return local ? new Date(`${local}${local.length === 16 ? ":00" : ""}+10:00`).toISOString() : "";
};
export const deadline = (
  item: Pick<Assessment, "due" | "due_text">,
  options: Intl.DateTimeFormatOptions = {},
) => (item.due ? format(item.due, options) : item.due_text || "Date not published");
export const personal = (item: Assessment, buffer: number) =>
  item.due
    ? new Date(new Date(item.due).getTime() - (item.buffer ?? buffer) * DAY).toISOString()
    : "";
export const included = (item: Announcement, following: string[] = []) =>
  item.saved || following.includes(item.club_url || "");
export const upcoming = (item: Announcement, now = Date.now()) =>
  !item.start || (item.status !== "cancelled" && new Date(item.end || item.start).getTime() >= now);
export function calendarEvents(plan: Plan, announcements = plan.announcements): CalendarEvent[] {
  const events: CalendarEvent[] = [];
  for (const item of plan.assessments)
    if (item.due) {
      events.push({ ...item, when: item.due, kind: "official", label: "Official deadline" });
      const target = personal(item, plan.settings.buffer);
      if (!item.done && Date.parse(target) !== Date.parse(item.due))
        events.push({ ...item, when: target, kind: "personal", label: "Your target" });
    }
  for (const item of announcements)
    if (item.start && included(item, plan.settings.following || []) && item.status !== "cancelled")
      events.push({ ...item, when: item.start, kind: "club", label: item.club || "Society event" });
  return events.sort((a, b) => Date.parse(a.when) - Date.parse(b.when));
}
export function onDay(item: { when: string; end?: string }, day: Date) {
  const start = Date.parse(item.when),
    end = Date.parse(item.end || "");
  return (
    start < day.getTime() + DAY && (end > start ? end > day.getTime() : start >= day.getTime())
  );
}
export function weekStart(offset = 0, now = new Date()) {
  const date = new Date(now);
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7) + offset * 7);
  return date;
}
