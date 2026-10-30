/** Student-data schemas own both runtime validation and the types used by study pages */
import * as z from "zod/mini";
import type { ReactNode } from "react";
export { miniSchema } from "../shared/schema.ts";
export type { MiniResult } from "../shared/schema.ts";

// Preserve additional saved fields so a newer backend's data survives an edit in this client
export const courseSchema = z.looseObject({
  id: z.string(),
  code: z.string(),
  name: z.string(),
  profile: z.string(),
  prerequisites: z.string(),
  notes: z.string(),
  verified: z.boolean(),
  pass_mark: z.optional(z.number()),
  hurdle_cap: z.optional(z.number()),
  drop_count: z.optional(z.number()),
  drop_group: z.optional(z.string()),
});
export const assessmentSchema = z.looseObject({
  id: z.string(),
  course: z.string(),
  title: z.string(),
  weight: z.number(),
  due: z.optional(z.string()),
  start: z.optional(z.string()),
  done: z.optional(z.boolean()),
  maximum: z.optional(z.number()),
  score: z.optional(z.nullable(z.number())),
  team: z.optional(z.boolean()),
  factor: z.optional(z.number()),
  penalty: z.optional(z.number()),
  hurdle: z.optional(z.nullable(z.number())),
  buffer: z.optional(z.nullable(z.number())),
  group: z.optional(z.string()),
  url: z.optional(z.string()),
  notes: z.optional(z.string()),
  source: z.optional(z.string()),
  due_text: z.optional(z.string()),
});
export const announcementSchema = z.looseObject({
  id: z.string(),
  title: z.string(),
  notes: z.string(),
  club: z.optional(z.string()),
  club_url: z.optional(z.string()),
  source: z.optional(z.string()),
  url: z.optional(z.string()),
  start: z.optional(z.string()),
  end: z.optional(z.string()),
  saved: z.optional(z.boolean()),
  status: z.optional(z.string()),
  banner: z.optional(z.string()),
  logo: z.optional(z.string()),
});
export const planSchema = z.looseObject({
  revision: z.int().check(z.nonnegative()),
  courses: z.array(courseSchema),
  assessments: z.array(assessmentSchema),
  announcements: z.array(announcementSchema),
  settings: z.looseObject({
    buffer: z.number(),
    target: z.number(),
    following: z.optional(z.array(z.string())),
    completed: z.optional(z.array(z.string())),
    skills: z.optional(z.string()),
  }),
});
export const toolsSchema = z.record(z.string(), z.object({ title: z.string(), about: z.string() }));
export const sourceSchema = z.union([planSchema, z.object({ count: z.number() })]);
export const clubSchema = z.object({
  name: z.string(),
  directory_url: z.string(),
  description: z.optional(z.string()),
  interests: z.optional(z.string()),
  banner: z.optional(z.string()),
  logo: z.optional(z.string()),
  contact: z.optional(z.string()),
  website: z.optional(z.string()),
  instagram: z.optional(z.string()),
  facebook: z.optional(z.string()),
  discord: z.optional(z.string()),
  linkedin: z.optional(z.string()),
  membership: z.optional(z.string()),
});
export const clubResultSchema = z.object({
  rows: z.array(clubSchema),
  total: z.number(),
  categories: z._default(z.array(z.string()), []),
  warning: z.optional(z.string()),
});
export const clubProfileSchema = z.object({
  club: clubSchema,
  events: z.array(z.object({ url: z.string(), title: z.string(), when: z.string() })),
});
export const feedSchema = z.object({ rows: z.array(announcementSchema), warning: z.string() });
export const readinessSchema = z.object({
  status: z.enum(["ready", "missing", "review", "incompatible"]),
  missing: z.array(z.string()),
  incompatible: z.array(z.string()),
  restrictions: z.optional(z.string()),
  wording: z.string(),
  assumed: z.optional(z.string()),
  topics: z.optional(z.array(z.string())),
  skills: z.array(z.string()),
  required: z.array(z.string()),
  known: z.optional(z.array(z.string())),
  completed: z.optional(z.array(z.string())),
});
export const metricSchema = z.object({
  mean: z.nullable(z.number()),
  count: z.number(),
  confidence: z.optional(z.string()),
});
const metricsSchema = z.record(z.string(), metricSchema);
const reviewSchema = z.object({
  id: z.string(),
  date: z.optional(z.string()),
  professor: z.optional(z.string()),
  text: z.optional(z.string()),
  target: z.optional(z.string()),
  usefulness: z.nullable(z.number()),
  difficulty: z.nullable(z.number()),
  fun: z.nullable(z.number()),
  url: z.string(),
});
export const subjectSchema = z.object({
  code: z.string(),
  name: z.string(),
  faculty: z.string(),
  description: z.optional(z.string()),
  offered: z.optional(z.string()),
  year: z.optional(z.number()),
  metrics: metricsSchema,
  readiness: z.optional(readinessSchema),
});
const searchSchema = z.object({
  rows: z.array(subjectSchema),
  total: z.number(),
  faculties: z.array(z.string()),
  semester: z.optional(z.string()),
  study_year: z.number(),
  updated: z.optional(z.string()),
});
export const researchSchema = z.extend(searchSchema, {
  rows: z.array(z.extend(subjectSchema, { readiness: readinessSchema })),
});
export const teachersSchema = z.extend(searchSchema, {
  rows: z.array(z.omit(subjectSchema, { readiness: true })),
});
export const courseInfoSchema = z.object({
  course: z.nullish(
    z.object({ code: z.string(), name: z.string(), description: z.optional(z.string()) }),
  ),
  details: z.record(z.string(), z.string()),
  readiness: readinessSchema,
  url: z.string(),
  official_error: z.optional(z.string()),
  reviews: z.array(reviewSchema),
  secat: z.array(
    z.object({ period: z.string(), question: z.string(), mean: z.number(), count: z.number() }),
  ),
  feedback: z.optional(z.partial(metricSchema)),
  offerings: z.array(
    z.object({ period: z.string(), campus: z.string(), profile: z.optional(z.string()) }),
  ),
});
export const teacherSchema = z.object({
  name: z.string(),
  faculty: z.string(),
  metrics: metricsSchema,
  reviews: z.array(reviewSchema),
});
const trailNodeSchema = z.object({
  code: z.string(),
  name: z.string(),
  required: z.array(z.string()),
  wording: z.optional(z.string()),
  loaded: z.optional(z.boolean()),
  depth: z.number(),
});
export const trailSchema = z.object({
  nodes: z.array(trailNodeSchema),
  limited: z.optional(z.boolean()),
});
export const profileSchema = z.object({
  assessments: z.array(
    z.object({
      title: z.string(),
      weight: z.number(),
      due: z.string(),
      due_text: z.string(),
      notes: z.optional(z.string()),
    }),
  ),
  rules: z.string(),
  notice: z.string(),
});
const markSchema = z.object({
  completed: z.number(),
  count: z.number(),
  projection: z.nullable(z.number()),
  high: z.nullable(z.number()),
  low: z.nullable(z.number()),
  required: z.nullable(z.number()),
  warnings: z.array(z.string()),
});
export const marksSchema = z.record(z.string(), markSchema);

export type Course = z.infer<typeof courseSchema>;
export type Assessment = z.infer<typeof assessmentSchema>;
export type Announcement = z.infer<typeof announcementSchema>;
export type Club = z.infer<typeof clubSchema>;
export type Plan = z.infer<typeof planSchema>;
export type Tools = z.infer<typeof toolsSchema>;
export type SourceResult = z.infer<typeof sourceSchema>;
export type Mini = Tools[string];
export type Readiness = z.infer<typeof readinessSchema>;
export type Metric = z.infer<typeof metricSchema>;
export type Subject = z.infer<typeof subjectSchema>;
export type Review = z.infer<typeof reviewSchema>;
export type CourseInfo = z.infer<typeof courseInfoSchema>;
export type TrailNode = z.infer<typeof trailNodeSchema>;
export type Trail = z.infer<typeof trailSchema>;
export type ResearchResult = z.infer<typeof searchSchema>;
export type ClubResult = z.infer<typeof clubResultSchema>;
export type Profile = z.infer<typeof profileSchema>;
export type Mark = z.infer<typeof markSchema>;
export type Change = (edit: (plan: Plan) => void) => Promise<void>;
export type Modal = (value: { title: string; body: ReactNode } | null) => void;
export type Source = (path: string, body?: object) => Promise<unknown>;
export interface Selection {
  code?: string;
  course_code?: string;
  name?: string;
  course_name?: string;
  readiness?: Readiness;
}
export interface PlanProps {
  plan: Plan;
  change: Change;
}
export interface SheetProps {
  close: () => void;
}
export interface Feed {
  rows: Announcement[];
  loading: boolean;
  error: string;
  retry: () => void;
}
