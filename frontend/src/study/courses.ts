import type { Assessment, Course, Plan, Profile, Selection } from "./model.ts";

const profileUrl = /^https:\/\/(?:archive\.)?course-profiles\.uq\.edu\.au\//;

/** Identify assessment records owned by a published UQ profile */
export const published = (item: Pick<Assessment, "source" | "url">) =>
  item.source === "profile" || profileUrl.test(item.url || "");

/** Replace one profile's official fields while retaining marks and personal planning */
export function syncProfile(plan: Plan, course: Course, profile: Profile) {
  const previous = new Map(
    plan.assessments
      .filter((item) => item.course === course.id && published(item))
      .map((item) => [item.title, item]),
  );
  plan.assessments = plan.assessments.filter(
    (item) => item.course !== course.id || !published(item),
  );
  for (const item of profile.assessments) {
    const saved = previous.get(item.title);
    plan.assessments.push({
      ...saved,
      id: saved?.id || crypto.randomUUID(),
      course: course.id,
      title: item.title,
      weight: item.weight,
      due: item.due,
      due_text: item.due_text,
      notes: item.notes || "",
      url: course.profile,
      source: "profile",
      maximum: saved?.maximum ?? 100,
      team: saved?.team ?? (saved?.factor ?? 1) !== 1,
      factor: saved?.factor ?? 1,
      penalty: saved?.penalty ?? 0,
      done: saved?.done ?? false,
    });
  }
}

/** Prefer the newest published profile while keeping other editions reachable */
export function years<T extends { period: string; profile?: string }>(offerings: T[]) {
  const year = (item: T) => Number(item.period.match(/\b20\d{2}\b/)?.[0] || 0);
  const published = offerings.filter((item) => item.profile);
  const latest = Math.max(0, ...(published.length ? published : offerings).map(year));
  return {
    latest: offerings.filter((item) => !year(item) || year(item) === latest),
    more: offerings.filter((item) => year(item) > 0 && year(item) !== latest),
  };
}

export function enrol(plan: Plan, row: Selection) {
  const code = row.course_code || row.code || "";
  if (plan.courses.some((course) => course.code === code))
    throw new Error(`${code} is already selected`);
  const course = {
    id: crypto.randomUUID(),
    code,
    name: row.course_name || row.name || code,
    profile: "",
    prerequisites: row.readiness?.wording || "",
    notes: "",
    verified: false,
  };
  plan.courses.push(course);
  return course;
}

export function badges(offered = "") {
  const parts = [
    ...new Set(
      offered
        .split(/\s+[·/]\s+/)
        .map((part) => part.trim())
        .filter(Boolean),
    ),
  ];
  return parts
    .filter(
      (part) =>
        !/^Semester 2, (20\d{2})$/.test(part) ||
        !parts.includes(part.replace("Semester 2", "Semester 1")),
    )
    .map((part) => {
      if (
        /^Semester 1, (20\d{2})$/.test(part) &&
        parts.includes(part.replace("Semester 1", "Semester 2"))
      )
        return "Sem 1 & 2";
      return part
        .replace(/^Semester ([12]), 20\d{2}$/, "Sem $1")
        .replace(/^Summer Semester, 20\d{2}$/, "Summer");
    });
}
